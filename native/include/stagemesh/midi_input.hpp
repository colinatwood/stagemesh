#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace stagemesh {

struct MidiInputMessage {
    std::uint64_t show_time_ns{0};
    std::uint8_t status{0};
    std::uint8_t data1{0};
    std::uint8_t data2{0};
};

// Allocation-free MIDI 1 byte-stream parser. It supports channel voice
// messages, running status, realtime bytes interleaved with messages, and
// skips SysEx payloads. System-common messages are consumed but not emitted in
// this first input slice because StageMesh currently routes three-byte channel
// events through its public control contract.
class MidiByteParser {
public:
    [[nodiscard]] bool feed(std::uint8_t byte, std::uint64_t show_time_ns, MidiInputMessage& out) noexcept;
    void reset() noexcept;

private:
    [[nodiscard]] static std::uint8_t data_length(std::uint8_t status) noexcept;

    std::uint8_t running_status_{0};
    std::uint8_t message_status_{0};
    std::array<std::uint8_t, 2> data_{};
    std::uint8_t expected_{0};
    std::uint8_t received_{0};
    bool in_sysex_{false};
};

struct MidiDeviceDescriptor {
    std::array<char, 64> id{};
    std::array<char, 128> name{};
    // Linux stores the /dev/snd path. Windows/macOS store a bounded hash-only
    // identity token until the native event-input backend is wired here.
    std::array<char, 256> path{};
    bool input{true};
    bool connected{true};
};

struct CapturedMidiInput {
    std::array<char, 64> device_id{};
    std::array<char, 64> player_id{};
    MidiInputMessage message{};
};

struct MidiIngressAuditStatus {
    std::uint64_t polls{0}, bytes{0}, messages{0}, queue_drops{0}, injected_messages{0}, max_poll_duration_ns{0};
    bool physical_outputs_armed{false};
    std::uint64_t topology_detaches{0};
};

// Bounded multi-producer/multi-consumer ingress. Native MIDI APIs may invoke
// callbacks concurrently for different endpoints while the engine drains
// events on its control thread. Sequence numbers serialize slot ownership
// without callback locks.
template <typename T, std::size_t Capacity>
class BoundedMpmcQueue {
    static_assert(Capacity >= 2 && (Capacity & (Capacity - 1)) == 0,
                  "queue capacity must be a power of two");
    struct Cell {
        std::atomic<std::size_t> sequence{0};
        T value{};
    };

public:
    BoundedMpmcQueue() noexcept {
        for (std::size_t i = 0; i < Capacity; ++i) cells_[i].sequence.store(i, std::memory_order_relaxed);
    }
    BoundedMpmcQueue(const BoundedMpmcQueue&) = delete;
    BoundedMpmcQueue& operator=(const BoundedMpmcQueue&) = delete;

    [[nodiscard]] bool try_push(const T& value) noexcept {
        auto position = enqueue_.load(std::memory_order_relaxed);
        Cell* cell = nullptr;
        for (;;) {
            cell = &cells_[position & (Capacity - 1)];
            const auto sequence = cell->sequence.load(std::memory_order_acquire);
            const auto difference = static_cast<std::intptr_t>(sequence) - static_cast<std::intptr_t>(position);
            if (difference == 0) {
                if (enqueue_.compare_exchange_weak(position, position + 1, std::memory_order_relaxed)) break;
            } else if (difference < 0) {
                return false;
            } else {
                position = enqueue_.load(std::memory_order_relaxed);
            }
        }
        cell->value = value;
        cell->sequence.store(position + 1, std::memory_order_release);
        return true;
    }

    [[nodiscard]] bool try_pop(T& value) noexcept {
        auto position = dequeue_.load(std::memory_order_relaxed);
        Cell* cell = nullptr;
        for (;;) {
            cell = &cells_[position & (Capacity - 1)];
            const auto sequence = cell->sequence.load(std::memory_order_acquire);
            const auto difference = static_cast<std::intptr_t>(sequence) - static_cast<std::intptr_t>(position + 1);
            if (difference == 0) {
                if (dequeue_.compare_exchange_weak(position, position + 1, std::memory_order_relaxed)) break;
            } else if (difference < 0) {
                return false;
            } else {
                position = dequeue_.load(std::memory_order_relaxed);
            }
        }
        value = cell->value;
        cell->sequence.store(position + Capacity, std::memory_order_release);
        return true;
    }

    [[nodiscard]] std::size_t size_approx() const noexcept {
        const auto enqueued = enqueue_.load(std::memory_order_acquire);
        const auto dequeued = dequeue_.load(std::memory_order_acquire);
        const auto count = enqueued - dequeued;
        return count > Capacity ? Capacity : count;
    }

private:
    alignas(64) std::array<Cell, Capacity> cells_{};
    alignas(64) std::atomic<std::size_t> enqueue_{0};
    alignas(64) std::atomic<std::size_t> dequeue_{0};
};

// Small platform-facing input registry. Registry/open/close operations belong
// on the control thread. poll() is non-blocking. Linux uses raw /dev/snd MIDI
// character devices. Windows/macOS enumerate hash-only native input identities;
// attach/poll use the native callback backend and remain fail-closed when an
// endpoint identity cannot be resolved.
class MidiInputManager {
public:
    MidiInputManager() noexcept;
    ~MidiInputManager();

    MidiInputManager(const MidiInputManager&) = delete;
    MidiInputManager& operator=(const MidiInputManager&) = delete;

    std::size_t scan() noexcept;
    [[nodiscard]] std::size_t device_count() const noexcept { return device_count_; }
    [[nodiscard]] const MidiDeviceDescriptor* device(std::size_t index) const noexcept;
    [[nodiscard]] bool attached(std::string_view device_id) const noexcept;

    [[nodiscard]] bool attach(std::string_view device_id, std::string_view player_id) noexcept;
    [[nodiscard]] bool detach(std::string_view device_id) noexcept;
    [[nodiscard]] std::size_t attached_count() const noexcept;

    // Reads all currently available bytes from attached devices and appends
    // parsed events to a bounded queue. Returns newly captured event count.
    std::size_t poll(std::uint64_t show_time_ns) noexcept;
    // Reconcile attached target endpoints against a fresh identity snapshot.
    // Missing or changed identities are detached; no automatic rebind occurs.
    void reconcile() noexcept;
    // Owner-thread shutdown. No callback context is released until all native
    // handles have been closed.
    void deactivate() noexcept;
    [[nodiscard]] bool pop(CapturedMidiInput& out) noexcept;
    // Safe for concurrent native MIDI callbacks. Performs only bounded copies,
    // atomic queue operations and atomic audit updates; it never takes the
    // registry lock or allocates.
    [[nodiscard]] bool capture_callback(std::string_view device_id, std::string_view player_id,
                                       const MidiInputMessage& message) noexcept;
    [[nodiscard]] bool inject(std::string_view device_id, std::string_view player_id, const MidiInputMessage& message) noexcept;
    [[nodiscard]] std::size_t queued() const noexcept { return queue_.size_approx(); }
    [[nodiscard]] MidiIngressAuditStatus audit_status() const noexcept;

public:
    struct DeviceSlot {
        MidiDeviceDescriptor descriptor{};
        std::array<char, 64> player_id{};
        MidiByteParser parser{};
        int handle{-1};
        std::array<char, 128> native_hash{};
        std::uint32_t native_index{0xffffffffu};
        std::uintptr_t native_source{0};
        MidiInputManager* owner{nullptr};
        bool attached{false};
    };

private:

    [[nodiscard]] DeviceSlot* find_slot(std::string_view device_id) noexcept;
    [[nodiscard]] const DeviceSlot* find_slot(std::string_view device_id) const noexcept;
    void close_slot(DeviceSlot& slot) noexcept;
    [[nodiscard]] bool queue(const CapturedMidiInput& event) noexcept;

    static constexpr std::size_t max_devices = 32;
    static constexpr std::size_t queue_capacity = 2048;
    std::array<DeviceSlot, max_devices> devices_{};
    std::size_t device_count_{0};
    BoundedMpmcQueue<CapturedMidiInput, queue_capacity> queue_{};
    std::atomic<std::uint64_t> audit_polls_{0},audit_bytes_{0},audit_messages_{0},audit_queue_drops_{0},audit_injected_{0},audit_max_poll_ns_{0},audit_topology_detaches_{0};
    std::uintptr_t native_client_{0}, native_port_{0};
};

} // namespace stagemesh
