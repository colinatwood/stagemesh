#pragma once

#include "stageforge/midi_input.hpp"

#include <condition_variable>
#include <future>
#include <mutex>
#include <thread>

namespace stageforge {

// Owns the MIDI registry and its platform handles on one thread. The command
// thread receives value snapshots only; native callbacks enqueue directly into
// MidiInputManager's bounded MPMC queue and never touch this mutex.
class MidiInputOwner final {
public:
    MidiInputOwner();
    ~MidiInputOwner();
    MidiInputOwner(const MidiInputOwner&) = delete;
    MidiInputOwner& operator=(const MidiInputOwner&) = delete;

    std::size_t scan();
    bool device(std::size_t index, MidiDeviceDescriptor& out);
    bool attached(std::string_view id);
    std::size_t device_count();
    std::size_t attached_count();
    bool attach(std::string_view id, std::string_view player);
    bool detach(std::string_view id);
    std::size_t poll(std::uint64_t show_time_ns);
    bool pop(CapturedMidiInput& out) noexcept;
    bool inject(std::string_view id, std::string_view player, const MidiInputMessage& message) noexcept;
    std::size_t queued() const noexcept { return manager_.queued(); }
    MidiIngressAuditStatus audit_status() const noexcept { return manager_.audit_status(); }

private:
    template<class Function>
    auto execute(Function function) -> std::invoke_result_t<Function, MidiInputManager&>;
    void run();

    mutable std::mutex manager_mutex_;
    MidiInputManager manager_;
    std::mutex serial_;
    std::mutex command_mutex_;
    std::condition_variable wake_;
    std::function<void(MidiInputManager&)> pending_;
    bool stopping_{false};
    std::thread worker_;
};

} // namespace stageforge
