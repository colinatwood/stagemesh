#pragma once

#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <mutex>

#include "stagemesh/core_api.h"

namespace stagemesh {

// Transport intent has one control-writer at a time, while audio/render readers
// require a non-blocking coherent snapshot. Two immutable publication slots are
// used with reader pins. The real-time reader never waits for the control
// writer; a writer may briefly wait before reusing an old slot.
class TransportClock {
public:
    explicit TransportClock(double sample_rate = 48000.0, double bpm = 120.0);

    void play();
    void pause();
    void stop();
    void rewind();

    void set_bpm(double bpm);
    void set_sample_rate(double sample_rate);
    void set_clock_rate(double rate);
    void seek_seconds(double seconds);

    [[nodiscard]] bool running() const noexcept;
    [[nodiscard]] sf_time snapshot() const noexcept;

private:
    using clock = std::chrono::steady_clock;

    struct PublishedState {
        bool running{false};
        double elapsed_seconds{0.0};
        double bpm{120.0};
        double sample_rate{48000.0};
        double clock_rate{1.0};
        std::int64_t started_at_ns{0};
    };

    [[nodiscard]] static double clamp(double value, double low, double high) noexcept;
    [[nodiscard]] static std::int64_t now_ns() noexcept;
    [[nodiscard]] static double show_seconds(const PublishedState& state, std::int64_t at_ns) noexcept;
    [[nodiscard]] PublishedState read_published() const noexcept;
    void publish(const PublishedState& state) noexcept;

    mutable std::mutex writer_mutex_{};
    std::array<PublishedState, 2> slots_{};
    mutable std::array<std::atomic<std::uint32_t>, 2> readers_{};
    std::atomic<std::uint8_t> active_slot_{0};
};

} // namespace stagemesh
