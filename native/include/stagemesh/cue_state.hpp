#pragma once

#include "stagemesh/show_event.hpp"

#include <atomic>
#include <cstdint>

namespace stagemesh {

struct CueStateSnapshot {
    std::uint64_t current_cue_id{0};
    std::uint64_t previous_cue_id{0};
    std::uint64_t last_event_id{0};
    std::uint64_t last_show_time_ns{0};
    std::uint64_t transitions{0};
};

// Single writer (Core execution loop), many control readers. The writer never
// waits. Readers may retry briefly if they race a transition.
class CoreCueState final {
public:
    void apply(const ShowEvent& event) noexcept {
        if (event.type != ShowEventType::cue) return;
        sequence_.fetch_add(1, std::memory_order_acq_rel);
        previous_cue_id_.store(current_cue_id_.load(std::memory_order_relaxed), std::memory_order_relaxed);
        current_cue_id_.store(event.payload.cue.cue_id, std::memory_order_relaxed);
        last_event_id_.store(event.event_id, std::memory_order_relaxed);
        last_show_time_ns_.store(event.show_time_ns, std::memory_order_relaxed);
        transitions_.fetch_add(1, std::memory_order_relaxed);
        sequence_.fetch_add(1, std::memory_order_release);
    }

    [[nodiscard]] CueStateSnapshot snapshot() const noexcept {
        CueStateSnapshot result{};
        for (;;) {
            const auto begin = sequence_.load(std::memory_order_acquire);
            if ((begin & 1U) != 0U) continue;
            result.current_cue_id = current_cue_id_.load(std::memory_order_relaxed);
            result.previous_cue_id = previous_cue_id_.load(std::memory_order_relaxed);
            result.last_event_id = last_event_id_.load(std::memory_order_relaxed);
            result.last_show_time_ns = last_show_time_ns_.load(std::memory_order_relaxed);
            result.transitions = transitions_.load(std::memory_order_relaxed);
            if (sequence_.load(std::memory_order_acquire) == begin) return result;
        }
    }

private:
    mutable std::atomic<std::uint64_t> sequence_{0};
    std::atomic<std::uint64_t> current_cue_id_{0};
    std::atomic<std::uint64_t> previous_cue_id_{0};
    std::atomic<std::uint64_t> last_event_id_{0};
    std::atomic<std::uint64_t> last_show_time_ns_{0};
    std::atomic<std::uint64_t> transitions_{0};
};

} // namespace stagemesh
