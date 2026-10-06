#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

struct MidiEvent {
    std::uint64_t event_id{0};
    std::uint64_t show_time_ns{0};
    std::uint8_t status{0};
    std::uint8_t data1{0};
    std::uint8_t data2{0};
};

// Fixed-capacity timestamp scheduler. schedule() is intended for the control
// thread; pop_due() can be called by the MIDI dispatch thread without heap
// allocation. Events are stable-ordered by timestamp then event id.
template <std::size_t Capacity>
class MidiScheduler {
    static_assert(Capacity > 0, "MIDI scheduler capacity must be non-zero");

public:
    [[nodiscard]] bool schedule(const MidiEvent& event) noexcept {
        if (size_ >= Capacity) {
            return false;
        }
        std::size_t index = size_;
        while (index > 0 && later(events_[index - 1], event)) {
            events_[index] = events_[index - 1];
            --index;
        }
        events_[index] = event;
        ++size_;
        return true;
    }

    [[nodiscard]] bool pop_due(std::uint64_t show_time_ns, MidiEvent& out) noexcept {
        if (size_ == 0 || events_[0].show_time_ns > show_time_ns) {
            return false;
        }
        out = events_[0];
        for (std::size_t index = 1; index < size_; ++index) {
            events_[index - 1] = events_[index];
        }
        --size_;
        return true;
    }

    [[nodiscard]] std::size_t size() const noexcept { return size_; }
    [[nodiscard]] constexpr std::size_t capacity() const noexcept { return Capacity; }
    void clear() noexcept { size_ = 0; }

private:
    [[nodiscard]] static bool later(const MidiEvent& lhs, const MidiEvent& rhs) noexcept {
        return lhs.show_time_ns > rhs.show_time_ns ||
               (lhs.show_time_ns == rhs.show_time_ns && lhs.event_id > rhs.event_id);
    }

    std::array<MidiEvent, Capacity> events_{};
    std::size_t size_{0};
};

} // namespace stagemesh
