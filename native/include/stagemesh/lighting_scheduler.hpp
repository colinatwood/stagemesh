#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

struct LightingEvent {
    std::uint64_t event_id{0};
    std::uint64_t show_time_ns{0};
    std::uint16_t universe{0};
    std::uint16_t channel{1}; // DMX channel 1..512
    std::uint8_t value{0};
};

// Fixed-capacity scheduler for show-accurate lighting state changes. Scheduling
// happens on a control thread; a lighting dispatch thread drains due events.
template <std::size_t Capacity>
class LightingScheduler {
public:
    [[nodiscard]] bool schedule(const LightingEvent& event) noexcept {
        if (size_ >= Capacity || event.channel < 1 || event.channel > 512) {
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

    [[nodiscard]] bool pop_due(std::uint64_t show_time_ns, LightingEvent& out) noexcept {
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
    [[nodiscard]] static bool later(const LightingEvent& lhs, const LightingEvent& rhs) noexcept {
        return lhs.show_time_ns > rhs.show_time_ns ||
            (lhs.show_time_ns == rhs.show_time_ns && lhs.event_id > rhs.event_id);
    }

    std::array<LightingEvent, Capacity> events_{};
    std::size_t size_{0};
};

class DmxUniverseState {
public:
    void set(std::uint16_t channel, std::uint8_t value) noexcept {
        if (channel >= 1 && channel <= values_.size()) {
            values_[channel - 1] = value;
            dirty_ = true;
        }
    }

    [[nodiscard]] std::uint8_t get(std::uint16_t channel) const noexcept {
        return channel >= 1 && channel <= values_.size() ? values_[channel - 1] : 0;
    }

    [[nodiscard]] const std::array<std::uint8_t, 512>& values() const noexcept { return values_; }
    [[nodiscard]] bool dirty() const noexcept { return dirty_; }
    void clear_dirty() noexcept { dirty_ = false; }

private:
    std::array<std::uint8_t, 512> values_{};
    bool dirty_{false};
};

} // namespace stagemesh
