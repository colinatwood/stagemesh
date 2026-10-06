#pragma once

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cmath>

namespace stagemesh {

struct StereoFanoutFrame {
    float left{0.0F};
    float right{0.0F};
};

// Single-producer / multi-reader real-time ring. The capture thread writes once;
// each physical output owns an independent reader tail. Inactive readers do not
// apply backpressure. Slow active readers may be advanced when the producer
// needs room, and that loss is reported per reader rather than blocking capture.
template <std::size_t Capacity, std::size_t Readers>
class AudioFanoutRing {
    static_assert(Capacity >= 4, "AudioFanoutRing needs at least four slots");
    static_assert(Readers >= 1, "AudioFanoutRing needs at least one reader");
public:
    AudioFanoutRing() noexcept {
        for (auto& active : reader_active_) active.store(false, std::memory_order_relaxed);
        for (auto& tail : tails_) tail.store(0, std::memory_order_relaxed);
        for (auto& value : dropped_) value.store(0, std::memory_order_relaxed);
        for (auto& value : underruns_) value.store(0, std::memory_order_relaxed);
    }

    void set_reader_active(std::size_t reader, bool active) noexcept {
        if (reader >= Readers) return;
        if (active) {
            tails_[reader].store(head_.load(std::memory_order_acquire), std::memory_order_release);
            dropped_[reader].store(0, std::memory_order_release);
            underruns_[reader].store(0, std::memory_order_release);
        }
        reader_active_[reader].store(active, std::memory_order_release);
    }

    [[nodiscard]] bool reader_active(std::size_t reader) const noexcept {
        return reader < Readers && reader_active_[reader].load(std::memory_order_acquire);
    }

    std::size_t push_interleaved(const float* data, std::size_t frames, std::uint32_t channels) noexcept {
        if (!data || channels == 0 || frames == 0) return 0;
        bool any_reader = false;
        for (const auto& active : reader_active_) {
            if (active.load(std::memory_order_acquire)) { any_reader = true; break; }
        }
        if (!any_reader) return frames; // capture remains non-blocking until a sink is armed.

        std::size_t pushed = 0;
        auto head = head_.load(std::memory_order_relaxed);
        for (; pushed < frames; ++pushed) {
            const auto next = increment(head);
            for (std::size_t reader = 0; reader < Readers; ++reader) {
                if (!reader_active_[reader].load(std::memory_order_acquire)) continue;
                auto tail = tails_[reader].load(std::memory_order_acquire);
                if (next == tail) {
                    tails_[reader].store(increment(tail), std::memory_order_release);
                    dropped_[reader].fetch_add(1, std::memory_order_relaxed);
                }
            }
            const auto base = pushed * channels;
            const float left=std::isfinite(data[base])?data[base]:0.0F;
            const float raw_right=channels > 1 ? data[base + 1] : data[base];
            frames_[head].left = left;
            frames_[head].right = std::isfinite(raw_right)?raw_right:0.0F;
            head = next;
        }
        head_.store(head, std::memory_order_release);
        return pushed;
    }

    std::size_t pop_planar(std::size_t reader, float* left, float* right, std::size_t frames) noexcept {
        if (reader >= Readers || !left || !right || frames == 0) return 0;
        if (!reader_active_[reader].load(std::memory_order_acquire)) {
            std::fill_n(left, frames, 0.0F);
            std::fill_n(right, frames, 0.0F);
            return 0;
        }
        std::size_t popped = 0;
        auto tail = tails_[reader].load(std::memory_order_relaxed);
        const auto head = head_.load(std::memory_order_acquire);
        while (popped < frames && tail != head) {
            left[popped] = frames_[tail].left;
            right[popped] = frames_[tail].right;
            tail = increment(tail);
            ++popped;
        }
        tails_[reader].store(tail, std::memory_order_release);
        if (popped < frames) {
            std::fill(left + popped, left + frames, 0.0F);
            std::fill(right + popped, right + frames, 0.0F);
            underruns_[reader].fetch_add(frames - popped, std::memory_order_relaxed);
        }
        return popped;
    }

    [[nodiscard]] std::size_t queued(std::size_t reader) const noexcept {
        if (reader >= Readers || !reader_active_[reader].load(std::memory_order_acquire)) return 0;
        const auto head = head_.load(std::memory_order_acquire);
        const auto tail = tails_[reader].load(std::memory_order_acquire);
        return head >= tail ? head - tail : Capacity - (tail - head);
    }
    [[nodiscard]] std::uint64_t dropped(std::size_t reader) const noexcept {
        return reader < Readers ? dropped_[reader].load(std::memory_order_acquire) : 0;
    }
    [[nodiscard]] std::uint64_t underruns(std::size_t reader) const noexcept {
        return reader < Readers ? underruns_[reader].load(std::memory_order_acquire) : 0;
    }

    void reset() noexcept {
        const auto head = head_.load(std::memory_order_acquire);
        for (std::size_t reader = 0; reader < Readers; ++reader) {
            tails_[reader].store(head, std::memory_order_release);
            dropped_[reader].store(0, std::memory_order_release);
            underruns_[reader].store(0, std::memory_order_release);
        }
    }

private:
    static constexpr std::size_t increment(std::size_t value) noexcept { return (value + 1) % Capacity; }
    std::array<StereoFanoutFrame, Capacity> frames_{};
    std::atomic<std::size_t> head_{0};
    std::array<std::atomic<std::size_t>, Readers> tails_{};
    std::array<std::atomic<bool>, Readers> reader_active_{};
    std::array<std::atomic<std::uint64_t>, Readers> dropped_{};
    std::array<std::atomic<std::uint64_t>, Readers> underruns_{};
};

} // namespace stagemesh
