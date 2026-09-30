#pragma once
#include <chrono>
#include <condition_variable>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <type_traits>

namespace stageforge {
// Control-plane calls only. One pending command bounds the queue. The backend,
// including its monitor and native stream, lives entirely on the worker thread.
// Never return backend pointers/references or invoke execute from a callback.
template<class Service> class CaptureServiceOwner final {
public:
    explicit CaptureServiceOwner(std::function<std::unique_ptr<Service>()> factory) {
        std::promise<void> ready;
        auto started = ready.get_future();
        worker_ = std::thread([this, factory = std::move(factory), ready = std::move(ready)]() mutable {
            std::unique_ptr<Service> service;
            try { service = factory(); if (!service) throw std::runtime_error("capture service factory returned null"); }
            catch (...) { ready.set_exception(std::current_exception()); return; }
            ready.set_value();
            for (;;) {
                std::function<void(Service&)> command;
                {
                    std::unique_lock<std::mutex> lock(mutex_);
                    wake_.wait_for(lock, std::chrono::milliseconds(2), [this] { return stopping_ || pending_; });
                    if (stopping_) break;
                    command = std::move(pending_);
                    pending_ = {};
                }
                if (command) command(*service);
                try { service->service(0); }
                catch (...) { service->deactivate(); }
            }
            service->deactivate();
            // Destruction here preserves native API thread affinity and drains
            // callbacks before the caller can release its receive context.
        });
        try { started.get(); }
        catch (...) { worker_.join(); throw; }
    }
    ~CaptureServiceOwner() { shutdown(); }
    CaptureServiceOwner(const CaptureServiceOwner&) = delete;
    CaptureServiceOwner& operator=(const CaptureServiceOwner&) = delete;

    template<class Function> auto execute(Function function) -> std::invoke_result_t<Function, Service&> {
        using Result = std::invoke_result_t<Function, Service&>;
        static_assert(!std::is_reference_v<Result> && !std::is_pointer_v<Result>, "return a value snapshot");
        std::lock_guard<std::mutex> serial(serial_);
        auto task = std::make_shared<std::packaged_task<Result(Service&)>>(std::move(function));
        auto result = task->get_future();
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (stopping_) throw std::runtime_error("capture owner is stopped");
            pending_ = [task](Service& service) { (*task)(service); };
        }
        wake_.notify_one();
        return result.get();
    }
    void shutdown() noexcept {
        std::lock_guard<std::mutex> serial(serial_);
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopping_ = true;
        }
        wake_.notify_one();
        if (worker_.joinable()) worker_.join();
    }
private:
    std::mutex serial_, mutex_;
    std::condition_variable wake_;
    std::function<void(Service&)> pending_;
    bool stopping_{false};
    std::thread worker_;
};
}
