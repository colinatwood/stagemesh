#pragma once

#include "stagemesh/show_event_dispatcher.hpp"
#include "stagemesh/transport_clock.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <thread>

namespace stagemesh {

using ShowEventSinkFn = bool (*)(void* context, const ShowEvent& event, bool late) noexcept;
using ShowLoopTickFn = void (*)(void* context, std::uint64_t show_time_ns) noexcept;

struct ShowExecutionLoopMetrics {
    bool running{false};
    std::uint64_t cycles{0};
    std::uint64_t wakeups{0};
    std::uint64_t timed_waits{0};
    std::uint64_t dispatched{0};
    std::uint64_t manual_drains{0};
    std::uint64_t cancel_requests{0};
    std::uint64_t last_show_time_ns{0};
};

// Owns all timeline mutation/dispatch after start(). The control producer may
// submit events lock-free through the dispatcher's SPSC ingress. Synchronous
// drain/cancel compatibility calls are serialized as owner-thread requests.
// The loop is show-critical but not an audio callback: it may sleep/wake and
// use control-path synchronization, while the audio thread remains isolated.
template <std::size_t IngressCapacity, std::size_t TimelineCapacity, std::size_t ReplayCapacity = 512>
class ShowExecutionLoop final {
public:
    using Dispatcher = ShowEventDispatcher<IngressCapacity, TimelineCapacity, ReplayCapacity>;

    ShowExecutionLoop(TransportClock& clock, ShowEventSinkFn sink, void* sink_context,
                      ShowLoopTickFn tick = nullptr, void* tick_context = nullptr) noexcept
        : clock_(clock), sink_(sink), sink_context_(sink_context), tick_(tick), tick_context_(tick_context) {}

    ~ShowExecutionLoop() { stop(); }

    ShowExecutionLoop(const ShowExecutionLoop&) = delete;
    ShowExecutionLoop& operator=(const ShowExecutionLoop&) = delete;

    [[nodiscard]] bool start() noexcept {
        bool expected = false;
        if (!running_.compare_exchange_strong(expected, true, std::memory_order_acq_rel)) return true;
        try {
            worker_ = std::thread([this] { run(); });
        } catch (...) {
            running_.store(false, std::memory_order_release);
            return false;
        }
        return true;
    }

    void stop() noexcept {
        if (!running_.exchange(false, std::memory_order_acq_rel)) return;
        wake();
        request_cv_.notify_all();
        if (worker_.joinable()) worker_.join();
    }

    [[nodiscard]] bool submit(const ShowEvent& event) noexcept {
        if (!dispatcher_.submit(event)) return false;
        wake();
        return true;
    }

    // Owner-thread only. Intended for events derived while dispatching another
    // Core event, such as the deterministic action bundle attached to a cue.
    [[nodiscard]] bool schedule_derived(const ShowEvent& event) noexcept {
        return dispatcher_.schedule_owned(event);
    }

    // Compatibility/testing path. The owner thread performs the drain.
    [[nodiscard]] std::size_t drain_until(std::uint64_t show_time_ns) noexcept {
        if (!running_.load(std::memory_order_acquire)) return dispatch_at(show_time_ns);
        ControlRequest request{};
        request.kind = ControlKind::drain;
        request.show_time_ns = show_time_ns;
        if (!execute_request(request)) return 0;
        manual_drains_.fetch_add(1, std::memory_order_relaxed);
        return static_cast<std::size_t>(request_result_count_.load(std::memory_order_acquire));
    }

    [[nodiscard]] bool cancel(ShowEventType type, std::uint64_t event_id) noexcept {
        if (!running_.load(std::memory_order_acquire)) return dispatcher_.cancel(type, event_id);
        ControlRequest request{};
        request.kind = ControlKind::cancel;
        request.type = type;
        request.event_id = event_id;
        if (!execute_request(request)) return false;
        cancel_requests_.fetch_add(1, std::memory_order_relaxed);
        return request_result_success_.load(std::memory_order_acquire);
    }

    void wake() noexcept {
        wake_generation_.fetch_add(1, std::memory_order_release);
        wake_cv_.notify_one();
    }

    [[nodiscard]] ShowEventDispatchMetrics dispatch_metrics() const noexcept { return dispatcher_.metrics(); }

    [[nodiscard]] ShowExecutionLoopMetrics loop_metrics() const noexcept {
        return ShowExecutionLoopMetrics{
            running_.load(std::memory_order_acquire),
            cycles_.load(std::memory_order_relaxed),
            wakeups_.load(std::memory_order_relaxed),
            timed_waits_.load(std::memory_order_relaxed),
            dispatched_.load(std::memory_order_relaxed),
            manual_drains_.load(std::memory_order_relaxed),
            cancel_requests_.load(std::memory_order_relaxed),
            last_show_time_ns_.load(std::memory_order_acquire)};
    }

private:
    enum class ControlKind : std::uint8_t { none = 0, drain = 1, cancel = 2 };
    struct ControlRequest {
        ControlKind kind{ControlKind::none};
        std::uint64_t show_time_ns{0};
        ShowEventType type{ShowEventType::cue};
        std::uint64_t event_id{0};
    };

    [[nodiscard]] std::size_t dispatch_at(std::uint64_t show_time_ns) noexcept {
        const auto count = dispatcher_.dispatch_due(show_time_ns, [&](const ShowEvent& event, bool late) noexcept {
            return sink_ ? sink_(sink_context_, event, late) : false;
        });
        dispatched_.fetch_add(count, std::memory_order_relaxed);
        if (tick_) tick_(tick_context_, show_time_ns);
        last_show_time_ns_.store(show_time_ns, std::memory_order_release);
        return count;
    }

    [[nodiscard]] bool execute_request(const ControlRequest& request) noexcept {
        std::unique_lock lock(request_mutex_);
        request_cv_.wait(lock, [&] { return !request_pending_ || !running_.load(std::memory_order_acquire); });
        if (!running_.load(std::memory_order_acquire)) return false;
        request_ = request;
        request_pending_ = true;
        request_completed_ = false;
        lock.unlock();
        wake();
        lock.lock();
        request_cv_.wait(lock, [&] { return request_completed_ || !running_.load(std::memory_order_acquire); });
        return request_completed_;
    }

    void process_request() noexcept {
        ControlRequest request{};
        {
            std::lock_guard lock(request_mutex_);
            if (!request_pending_) return;
            request = request_;
        }
        bool success = false;
        std::uint64_t count = 0;
        switch (request.kind) {
            case ControlKind::drain:
                count = static_cast<std::uint64_t>(dispatch_at(request.show_time_ns));
                success = true;
                break;
            case ControlKind::cancel:
                success = dispatcher_.cancel(request.type, request.event_id);
                break;
            case ControlKind::none:
                break;
        }
        {
            std::lock_guard lock(request_mutex_);
            request_result_count_.store(count, std::memory_order_release);
            request_result_success_.store(success, std::memory_order_release);
            request_completed_ = true;
            request_pending_ = false;
        }
        request_cv_.notify_all();
    }

    void run() noexcept {
        while (running_.load(std::memory_order_acquire)) {
            cycles_.fetch_add(1, std::memory_order_relaxed);
            process_request();
            if (!running_.load(std::memory_order_acquire)) break;

            const auto snapshot = clock_.snapshot();
            const auto now_ns = static_cast<std::uint64_t>(std::max(0.0, snapshot.show_seconds) * 1'000'000'000.0);
            (void)dispatch_at(now_ns);

            const auto metrics = dispatcher_.metrics();
            std::chrono::nanoseconds wait_for{5'000'000};
            if (metrics.next_show_time_ns != 0 && metrics.next_show_time_ns > now_ns && clock_.running()) {
                const auto delta = metrics.next_show_time_ns - now_ns;
                wait_for = std::chrono::nanoseconds{static_cast<std::int64_t>(std::min<std::uint64_t>(delta, 5'000'000ULL))};
            } else if (metrics.pending != 0 && metrics.next_show_time_ns <= now_ns) {
                wait_for = std::chrono::nanoseconds{0};
            }

            if (wait_for.count() <= 0) continue;
            const auto generation = wake_generation_.load(std::memory_order_acquire);
            std::unique_lock lock(wake_mutex_);
            timed_waits_.fetch_add(1, std::memory_order_relaxed);
            const bool signalled = wake_cv_.wait_for(lock, wait_for, [&] {
                return !running_.load(std::memory_order_acquire) ||
                       wake_generation_.load(std::memory_order_acquire) != generation ||
                       request_pending_relaxed();
            });
            if (signalled) wakeups_.fetch_add(1, std::memory_order_relaxed);
        }
        {
            std::lock_guard lock(request_mutex_);
            if (request_pending_) {
                request_result_count_.store(0, std::memory_order_release);
                request_result_success_.store(false, std::memory_order_release);
                request_completed_ = true;
                request_pending_ = false;
            }
        }
        request_cv_.notify_all();
    }

    [[nodiscard]] bool request_pending_relaxed() noexcept {
        std::lock_guard lock(request_mutex_);
        return request_pending_;
    }

    TransportClock& clock_;
    ShowEventSinkFn sink_{nullptr};
    void* sink_context_{nullptr};
    ShowLoopTickFn tick_{nullptr};
    void* tick_context_{nullptr};
    Dispatcher dispatcher_{};

    std::atomic<bool> running_{false};
    std::thread worker_{};
    std::mutex wake_mutex_{};
    std::condition_variable wake_cv_{};
    std::atomic<std::uint64_t> wake_generation_{0};

    std::mutex request_mutex_{};
    std::condition_variable request_cv_{};
    ControlRequest request_{};
    bool request_pending_{false};
    bool request_completed_{false};
    std::atomic<std::uint64_t> request_result_count_{0};
    std::atomic<bool> request_result_success_{false};

    std::atomic<std::uint64_t> cycles_{0};
    std::atomic<std::uint64_t> wakeups_{0};
    std::atomic<std::uint64_t> timed_waits_{0};
    std::atomic<std::uint64_t> dispatched_{0};
    std::atomic<std::uint64_t> manual_drains_{0};
    std::atomic<std::uint64_t> cancel_requests_{0};
    std::atomic<std::uint64_t> last_show_time_ns_{0};
};

} // namespace stagemesh
