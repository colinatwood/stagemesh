#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <type_traits>

namespace stagemesh {

template <typename T, std::size_t Capacity>
class SpscQueue {
    static_assert(Capacity >= 2, "SPSC capacity must be at least 2");
    static_assert(std::is_trivially_copyable_v<T>, "SPSC items must be trivially copyable");

public:
    [[nodiscard]] bool try_push(const T& value) noexcept {
        const auto head = head_.load(std::memory_order_relaxed);
        const auto next = increment(head);
        if (next == tail_.load(std::memory_order_acquire)) {
            return false;
        }
        storage_[head] = value;
        head_.store(next, std::memory_order_release);
        return true;
    }

    [[nodiscard]] bool try_pop(T& value) noexcept {
        const auto tail = tail_.load(std::memory_order_relaxed);
        if (tail == head_.load(std::memory_order_acquire)) {
            return false;
        }
        value = storage_[tail];
        tail_.store(increment(tail), std::memory_order_release);
        return true;
    }

    [[nodiscard]] constexpr std::size_t usable_capacity() const noexcept {
        return Capacity - 1;
    }

    // Observation only. Safe for producer/consumer telemetry; the value may be
    // stale immediately after return but never mutates queue ownership.
    [[nodiscard]] std::size_t size_approx() const noexcept {
        const auto head = head_.load(std::memory_order_acquire);
        const auto tail = tail_.load(std::memory_order_acquire);
        return head >= tail ? head - tail : Capacity - tail + head;
    }

private:
    [[nodiscard]] static constexpr std::size_t increment(std::size_t value) noexcept {
        return (value + 1) % Capacity;
    }

    std::array<T, Capacity> storage_{};
    alignas(64) std::atomic<std::size_t> head_{0};
    alignas(64) std::atomic<std::size_t> tail_{0};
};

} // namespace stagemesh
