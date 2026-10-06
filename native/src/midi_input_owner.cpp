#include "stagemesh/midi_input_owner.hpp"

#include <chrono>

namespace stagemesh {

MidiInputOwner::MidiInputOwner() : worker_([this] { run(); }) {
    // The worker performs the initial scan before accepting commands. This
    // keeps platform enumeration and handle creation off the command thread.
    execute([](MidiInputManager&) {});
}

MidiInputOwner::~MidiInputOwner() {
    std::lock_guard<std::mutex> serial(serial_);
    {
        std::lock_guard<std::mutex> lock(command_mutex_);
        stopping_ = true;
    }
    wake_.notify_one();
    if (worker_.joinable()) worker_.join();
}

void MidiInputOwner::run() {
    manager_.scan();
    auto next_reconcile = std::chrono::steady_clock::now();
    for (;;) {
        std::function<void(MidiInputManager&)> command;
        {
            std::unique_lock<std::mutex> lock(command_mutex_);
            wake_.wait_for(lock, std::chrono::milliseconds(2), [this] { return stopping_ || pending_; });
            if (stopping_) break;
            command = std::move(pending_);
            pending_ = {};
        }
        if (command) command(manager_);
        const auto now = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
        manager_.poll(now);
        const auto wall_now = std::chrono::steady_clock::now();
        if (wall_now >= next_reconcile) {
            manager_.reconcile();
            next_reconcile = wall_now + std::chrono::milliseconds(250);
        }
    }
    manager_.deactivate();
}

template<class Function>
auto MidiInputOwner::execute(Function function) -> std::invoke_result_t<Function, MidiInputManager&> {
    using Result = std::invoke_result_t<Function, MidiInputManager&>;
    std::lock_guard<std::mutex> serial(serial_);
    auto task = std::make_shared<std::packaged_task<Result(MidiInputManager&)>>(std::move(function));
    auto result = task->get_future();
    {
        std::lock_guard<std::mutex> lock(command_mutex_);
        if (stopping_) throw std::runtime_error("MIDI input owner is stopped");
        pending_ = [task](MidiInputManager& manager) { (*task)(manager); };
    }
    wake_.notify_one();
    return result.get();
}

std::size_t MidiInputOwner::scan() { return execute([](auto& manager) { return manager.scan(); }); }
bool MidiInputOwner::device(std::size_t index, MidiDeviceDescriptor& out) {
    return execute([&out, index](auto& manager) {
        const auto* value = manager.device(index);
        if (!value) return false;
        out = *value;
        return true;
    });
}
bool MidiInputOwner::attached(std::string_view id) { return execute([id](auto& manager) { return manager.attached(id); }); }
std::size_t MidiInputOwner::device_count() { return execute([](auto& manager) { return manager.device_count(); }); }
std::size_t MidiInputOwner::attached_count() { return execute([](auto& manager) { return manager.attached_count(); }); }
bool MidiInputOwner::attach(std::string_view id, std::string_view player) { return execute([id, player](auto& manager) { return manager.attach(id, player); }); }
bool MidiInputOwner::detach(std::string_view id) { return execute([id](auto& manager) { return manager.detach(id); }); }
std::size_t MidiInputOwner::poll(std::uint64_t show_time_ns) { return execute([show_time_ns](auto& manager) { return manager.poll(show_time_ns); }); }
bool MidiInputOwner::pop(CapturedMidiInput& out) noexcept { return manager_.pop(out); }
bool MidiInputOwner::inject(std::string_view id, std::string_view player, const MidiInputMessage& message) noexcept {
    try { return execute([id, player, message](auto& manager) { return manager.inject(id, player, message); }); }
    catch (...) { return false; }
}

} // namespace stagemesh
