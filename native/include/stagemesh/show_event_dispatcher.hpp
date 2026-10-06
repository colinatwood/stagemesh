#pragma once

#include "stagemesh/show_event.hpp"
#include "stagemesh/spsc_queue.hpp"

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <span>
#include <utility>

namespace stagemesh {

template <std::size_t Capacity>
class ShowTimeline final {
    static_assert(Capacity > 0, "show timeline capacity must be non-zero");

public:
    [[nodiscard]] bool schedule(const ShowEvent& event) noexcept {
        if (size_ >= Capacity || !show_event_is_valid(event)) return false;
        std::size_t index = size_;
        while (index > 0 && later(events_[index - 1], event)) {
            events_[index] = events_[index - 1];
            --index;
        }
        events_[index] = event;
        ++size_;
        return true;
    }

    [[nodiscard]] bool pop_due(std::uint64_t show_time_ns, ShowEvent& out) noexcept {
        if (size_ == 0 || events_[0].show_time_ns > show_time_ns) return false;
        out = events_[0];
        for (std::size_t index = 1; index < size_; ++index) events_[index - 1] = events_[index];
        --size_;
        return true;
    }

    [[nodiscard]] bool cancel(ShowEventType type, std::uint64_t event_id) noexcept {
        for (std::size_t index = 0; index < size_; ++index) {
            if (events_[index].type != type || events_[index].event_id != event_id) continue;
            for (std::size_t move = index + 1; move < size_; ++move) events_[move - 1] = events_[move];
            --size_;
            return true;
        }
        return false;
    }

    [[nodiscard]] std::size_t size() const noexcept { return size_; }
    [[nodiscard]] constexpr std::size_t capacity() const noexcept { return Capacity; }
    [[nodiscard]] std::uint64_t next_show_time_ns() const noexcept { return size_ ? events_[0].show_time_ns : 0; }
    void clear() noexcept { size_ = 0; }

private:
    [[nodiscard]] static bool later(const ShowEvent& lhs, const ShowEvent& rhs) noexcept {
        if (lhs.show_time_ns != rhs.show_time_ns) return lhs.show_time_ns > rhs.show_time_ns;
        if (lhs.priority != rhs.priority) return lhs.priority > rhs.priority;
        if (lhs.type != rhs.type) return static_cast<std::uint8_t>(lhs.type) > static_cast<std::uint8_t>(rhs.type);
        return lhs.event_id > rhs.event_id;
    }

    std::array<ShowEvent, Capacity> events_{};
    std::size_t size_{0};
};

struct ShowEventDispatchMetrics {
    std::uint64_t submitted{0};
    std::uint64_t accepted{0};
    std::uint64_t dispatched{0};
    std::uint64_t duplicates{0};
    std::uint64_t invalid{0};
    std::uint64_t ingress_overflow{0};
    std::uint64_t timeline_overflow{0};
    std::uint64_t late{0};
    std::uint64_t dropped_late{0};
    std::uint64_t dispatch_failures{0};
    std::uint64_t cancelled{0};
    std::uint64_t pending{0};
    std::uint64_t next_show_time_ns{0};
};

template <std::size_t IngressCapacity, std::size_t TimelineCapacity, std::size_t ReplayCapacity = 512>
class ShowEventDispatcher final {
    static_assert(IngressCapacity >= 2, "dispatcher ingress capacity must be at least 2");
    static_assert(ReplayCapacity > 0, "dispatcher replay capacity must be non-zero");

public:
    [[nodiscard]] bool submit(const ShowEvent& event) noexcept {
        submitted_.fetch_add(1, std::memory_order_relaxed);
        if (!show_event_is_valid(event)) {
            invalid_.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        if (!ingress_.try_push(event)) {
            ingress_overflow_.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        ingress_pending_.fetch_add(1, std::memory_order_release);
        return true;
    }

    // Called only by the timeline/dispatch owner thread for events derived
    // from an event currently being dispatched (for example cue actions).
    // Bypasses the producer ingress while retaining validation, replay, ordering,
    // and metrics.
    [[nodiscard]] bool schedule_owned(const ShowEvent& event) noexcept {
        submitted_.fetch_add(1, std::memory_order_relaxed);
        if (!show_event_is_valid(event)) { invalid_.fetch_add(1, std::memory_order_relaxed); return false; }
        if (seen(event.type, event.event_id)) { duplicates_.fetch_add(1, std::memory_order_relaxed); return false; }
        if (!timeline_.schedule(event)) { timeline_overflow_.fetch_add(1, std::memory_order_relaxed); return false; }
        timeline_pending_.fetch_add(1, std::memory_order_release);
        next_show_time_ns_.store(timeline_.next_show_time_ns(), std::memory_order_release);
        remember(event.type, event.event_id);
        accepted_.fetch_add(1, std::memory_order_relaxed);
        return true;
    }

    // Called only by the timeline/dispatch owner thread.
    std::size_t ingest_pending() noexcept {
        std::size_t accepted_now = 0;
        ShowEvent event{};
        while (ingress_.try_pop(event)) {
            ingress_pending_.fetch_sub(1, std::memory_order_release);
            if (seen(event.type, event.event_id)) {
                duplicates_.fetch_add(1, std::memory_order_relaxed);
                continue;
            }
            if (!timeline_.schedule(event)) {
                timeline_overflow_.fetch_add(1, std::memory_order_relaxed);
                continue;
            }
            timeline_pending_.fetch_add(1, std::memory_order_release);
            next_show_time_ns_.store(timeline_.next_show_time_ns(), std::memory_order_release);
            remember(event.type, event.event_id);
            accepted_.fetch_add(1, std::memory_order_relaxed);
            ++accepted_now;
        }
        return accepted_now;
    }

    template <typename Sink>
    std::size_t dispatch_due(std::uint64_t show_time_ns, Sink&& sink) noexcept(noexcept(sink(std::declval<const ShowEvent&>(), bool{}))) {
        ingest_pending();
        std::size_t count = 0;
        ShowEvent event{};
        while (timeline_.pop_due(show_time_ns, event)) {
            timeline_pending_.fetch_sub(1, std::memory_order_release);
            const bool is_late = show_time_ns > event.show_time_ns;
            if (is_late) late_.fetch_add(1, std::memory_order_relaxed);
            if (is_late && (event.flags & show_event_drop_if_late) != 0) {
                dropped_late_.fetch_add(1, std::memory_order_relaxed);
                continue;
            }
            if (sink(event, is_late)) {
                dispatched_.fetch_add(1, std::memory_order_relaxed);
                ++count;
            } else {
                dispatch_failures_.fetch_add(1, std::memory_order_relaxed);
            }
        }
        next_show_time_ns_.store(timeline_.next_show_time_ns(), std::memory_order_release);
        return count;
    }

    // Cancellation is performed by the dispatch owner. Replay memory remains so
    // the same event cannot be reintroduced after cancellation accidentally.
    [[nodiscard]] bool cancel(ShowEventType type, std::uint64_t event_id) noexcept {
        ingest_pending();
        if (!timeline_.cancel(type, event_id)) return false;
        timeline_pending_.fetch_sub(1, std::memory_order_release);
        next_show_time_ns_.store(timeline_.next_show_time_ns(), std::memory_order_release);
        cancelled_.fetch_add(1, std::memory_order_relaxed);
        return true;
    }

    [[nodiscard]] ShowEventDispatchMetrics metrics() const noexcept {
        ShowEventDispatchMetrics result{};
        result.submitted = submitted_.load(std::memory_order_relaxed);
        result.accepted = accepted_.load(std::memory_order_relaxed);
        result.dispatched = dispatched_.load(std::memory_order_relaxed);
        result.duplicates = duplicates_.load(std::memory_order_relaxed);
        result.invalid = invalid_.load(std::memory_order_relaxed);
        result.ingress_overflow = ingress_overflow_.load(std::memory_order_relaxed);
        result.timeline_overflow = timeline_overflow_.load(std::memory_order_relaxed);
        result.late = late_.load(std::memory_order_relaxed);
        result.dropped_late = dropped_late_.load(std::memory_order_relaxed);
        result.dispatch_failures = dispatch_failures_.load(std::memory_order_relaxed);
        result.cancelled = cancelled_.load(std::memory_order_relaxed);
        result.pending = timeline_pending_.load(std::memory_order_acquire) + ingress_pending_.load(std::memory_order_acquire);
        result.next_show_time_ns = next_show_time_ns_.load(std::memory_order_acquire);
        return result;
    }

private:
    struct ReplayKey {
        ShowEventType type{ShowEventType::cue};
        std::uint64_t event_id{0};
        bool active{false};
    };

    [[nodiscard]] bool seen(ShowEventType type, std::uint64_t event_id) const noexcept {
        for (const auto& entry : replay_) {
            if (entry.active && entry.type == type && entry.event_id == event_id) return true;
        }
        return false;
    }

    void remember(ShowEventType type, std::uint64_t event_id) noexcept {
        replay_[replay_cursor_] = ReplayKey{type, event_id, true};
        replay_cursor_ = (replay_cursor_ + 1) % ReplayCapacity;
    }

    SpscQueue<ShowEvent, IngressCapacity> ingress_{};
    ShowTimeline<TimelineCapacity> timeline_{};
    std::array<ReplayKey, ReplayCapacity> replay_{};
    std::size_t replay_cursor_{0};
    std::atomic<std::uint64_t> ingress_pending_{0};
    std::atomic<std::uint64_t> timeline_pending_{0};
    std::atomic<std::uint64_t> next_show_time_ns_{0};
    std::atomic<std::uint64_t> submitted_{0};
    std::atomic<std::uint64_t> accepted_{0};
    std::atomic<std::uint64_t> dispatched_{0};
    std::atomic<std::uint64_t> duplicates_{0};
    std::atomic<std::uint64_t> invalid_{0};
    std::atomic<std::uint64_t> ingress_overflow_{0};
    std::atomic<std::uint64_t> timeline_overflow_{0};
    std::atomic<std::uint64_t> late_{0};
    std::atomic<std::uint64_t> dropped_late_{0};
    std::atomic<std::uint64_t> dispatch_failures_{0};
    std::atomic<std::uint64_t> cancelled_{0};
};

} // namespace stagemesh
