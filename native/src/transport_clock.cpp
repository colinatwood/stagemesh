#include "stagemesh/transport_clock.hpp"

#include <cmath>
#include <thread>

namespace stagemesh {

TransportClock::TransportClock(double sample_rate, double bpm) {
    PublishedState initial{};
    initial.bpm = clamp(bpm, 30.0, 300.0);
    initial.sample_rate = clamp(sample_rate, 8000.0, 768000.0);
    initial.started_at_ns = now_ns();
    slots_[0] = initial;
    slots_[1] = initial;
}

double TransportClock::clamp(double value, double low, double high) noexcept {
    if (!std::isfinite(value)) return low;
    return value < low ? low : (value > high ? high : value);
}

std::int64_t TransportClock::now_ns() noexcept {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(clock::now().time_since_epoch()).count();
}

double TransportClock::show_seconds(const PublishedState& state, std::int64_t at_ns) noexcept {
    if (!state.running) return state.elapsed_seconds;
    const auto delta_ns = at_ns > state.started_at_ns ? at_ns - state.started_at_ns : 0;
    return state.elapsed_seconds + (static_cast<double>(delta_ns) / 1'000'000'000.0) * state.clock_rate;
}

TransportClock::PublishedState TransportClock::read_published() const noexcept {
    for (;;) {
        const auto slot = active_slot_.load(std::memory_order_acquire);
        readers_[slot].fetch_add(1, std::memory_order_acquire);
        if (active_slot_.load(std::memory_order_acquire) != slot) {
            readers_[slot].fetch_sub(1, std::memory_order_release);
            continue;
        }
        const PublishedState state = slots_[slot];
        readers_[slot].fetch_sub(1, std::memory_order_release);
        return state;
    }
}

void TransportClock::publish(const PublishedState& state) noexcept {
    const auto current = active_slot_.load(std::memory_order_acquire);
    const auto next = static_cast<std::uint8_t>(1U - current);
    while (readers_[next].load(std::memory_order_acquire) != 0) {
        // Control writers may yield. Real-time readers never wait on this path.
        std::this_thread::yield();
    }
    slots_[next] = state;
    active_slot_.store(next, std::memory_order_release);
}

void TransportClock::play() {
    std::scoped_lock lock(writer_mutex_);
    auto state = read_published();
    if (!state.running) {
        state.started_at_ns = now_ns();
        state.running = true;
        publish(state);
    }
}

void TransportClock::pause() {
    std::scoped_lock lock(writer_mutex_);
    auto state = read_published();
    if (state.running) {
        const auto now = now_ns();
        state.elapsed_seconds = show_seconds(state, now);
        state.started_at_ns = now;
        state.running = false;
        publish(state);
    }
}

void TransportClock::stop() {
    std::scoped_lock lock(writer_mutex_);
    auto state = read_published();
    state.running = false;
    state.elapsed_seconds = 0.0;
    state.started_at_ns = now_ns();
    publish(state);
}

void TransportClock::rewind() {
    std::scoped_lock lock(writer_mutex_);
    auto state = read_published();
    state.elapsed_seconds = 0.0;
    state.started_at_ns = now_ns();
    publish(state);
}

void TransportClock::set_bpm(double bpm) {
    std::scoped_lock lock(writer_mutex_);
    auto state = read_published();
    state.bpm = clamp(bpm, 30.0, 300.0);
    publish(state);
}

void TransportClock::set_sample_rate(double sample_rate) {
    std::scoped_lock lock(writer_mutex_);
    auto state = read_published();
    state.sample_rate = clamp(sample_rate, 8000.0, 768000.0);
    publish(state);
}

void TransportClock::set_clock_rate(double rate) {
    std::scoped_lock lock(writer_mutex_);
    auto state = read_published();
    const auto now = now_ns();
    if (state.running) {
        state.elapsed_seconds = show_seconds(state, now);
        state.started_at_ns = now;
    }
    state.clock_rate = clamp(std::isfinite(rate) ? rate : 1.0, 0.9995, 1.0005);
    publish(state);
}

void TransportClock::seek_seconds(double seconds) {
    std::scoped_lock lock(writer_mutex_);
    auto state = read_published();
    state.elapsed_seconds = clamp(seconds, 0.0, 7.0 * 24.0 * 3600.0);
    state.started_at_ns = now_ns();
    publish(state);
}

bool TransportClock::running() const noexcept {
    return read_published().running;
}

sf_time TransportClock::snapshot() const noexcept {
    const auto state = read_published();
    const auto now = now_ns();
    const auto seconds = show_seconds(state, now);
    return sf_time{
        static_cast<std::uint64_t>(now),
        static_cast<std::uint64_t>(seconds * state.sample_rate),
        seconds,
        state.bpm,
    };
}

} // namespace stagemesh
