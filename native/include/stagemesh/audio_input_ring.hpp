#pragma once

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

struct StereoInputFrame {
    float left{0.0F};
    float right{0.0F};
};

template <std::size_t Capacity>
class AudioInputRing {
    static_assert(Capacity >= 2, "AudioInputRing needs at least two slots");
public:
    std::size_t push_interleaved(const float* data, std::size_t frames, std::uint32_t channels) noexcept {
        if (!data || channels == 0) return 0;
        std::size_t pushed = 0;
        auto head = head_.load(std::memory_order_relaxed);
        const auto tail = tail_.load(std::memory_order_acquire);
        for (; pushed < frames; ++pushed) {
            const auto next = increment(head);
            if (next == tail) break;
            const auto base = pushed * channels;
            frames_[head].left = data[base];
            frames_[head].right = channels > 1 ? data[base + 1] : data[base];
            head = next;
        }
        head_.store(head, std::memory_order_release);
        if (pushed < frames) dropped_.fetch_add(frames - pushed, std::memory_order_relaxed);
        return pushed;
    }

    std::size_t pop_planar(float* left, float* right, std::size_t frames) noexcept {
        if (!left || !right) return 0;
        std::size_t popped = 0;
        auto tail = tail_.load(std::memory_order_relaxed);
        const auto head = head_.load(std::memory_order_acquire);
        while (popped < frames && tail != head) {
            left[popped] = frames_[tail].left;
            right[popped] = frames_[tail].right;
            tail = increment(tail);
            ++popped;
        }
        tail_.store(tail, std::memory_order_release);
        if (popped < frames) {
            std::fill(left + popped, left + frames, 0.0F);
            std::fill(right + popped, right + frames, 0.0F);
            underruns_.fetch_add(frames - popped, std::memory_order_relaxed);
        }
        return popped;
    }

    [[nodiscard]] std::size_t queued() const noexcept {
        const auto head = head_.load(std::memory_order_acquire);
        const auto tail = tail_.load(std::memory_order_acquire);
        return head >= tail ? head - tail : Capacity - (tail - head);
    }
    [[nodiscard]] std::uint64_t dropped() const noexcept { return dropped_.load(std::memory_order_acquire); }
    [[nodiscard]] std::uint64_t underruns() const noexcept { return underruns_.load(std::memory_order_acquire); }
    void reset() noexcept {
        tail_.store(head_.load(std::memory_order_acquire), std::memory_order_release);
        dropped_.store(0, std::memory_order_release);
        underruns_.store(0, std::memory_order_release);
    }

private:
    static constexpr std::size_t increment(std::size_t value) noexcept { return (value + 1) % Capacity; }
    std::array<StereoInputFrame, Capacity> frames_{};
    std::atomic<std::size_t> head_{0};
    std::atomic<std::size_t> tail_{0};
    std::atomic<std::uint64_t> dropped_{0};
    std::atomic<std::uint64_t> underruns_{0};
};

} // namespace stagemesh
