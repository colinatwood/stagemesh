#pragma once

#include "stagemesh/show_event.hpp"

#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <thread>

namespace stagemesh {

enum class AutomationApplyStatus : std::uint8_t {
    applied = 0,
    owner_conflict = 1,
    capacity = 2,
    invalid = 3,
    not_found = 4,
};

struct AutomationParameterSnapshot {
    bool registered{false};
    bool ramping{false};
    std::uint64_t target_id{0};
    std::uint64_t parameter_id{0};
    std::uint64_t owner_id{0};
    std::uint64_t revision{0};
    std::uint64_t last_event_id{0};
    std::uint64_t ramp_start_show_ns{0};
    std::uint64_t ramp_end_show_ns{0};
    float start_value{0.0F};
    float target_value{0.0F};
    float current_value{0.0F};
    std::uint64_t updates{0};
};

struct AutomationStateMetrics {
    std::uint64_t revision{0};
    std::uint64_t registered{0};
    std::uint64_t applied{0};
    std::uint64_t owner_conflicts{0};
    std::uint64_t capacity_rejections{0};
    std::uint64_t invalid{0};
    std::uint64_t owner_releases{0};
};

struct AutomationApplyResult {
    AutomationApplyStatus status{AutomationApplyStatus::invalid};
    std::uint64_t revision{0};
    std::uint64_t owner_id{0};

    [[nodiscard]] bool applied() const noexcept { return status == AutomationApplyStatus::applied; }
};

[[nodiscard]] inline float automation_value_at(const AutomationParameterSnapshot& state, std::uint64_t show_time_ns) noexcept {
    if (!state.registered) return 0.0F;
    if (state.ramp_end_show_ns <= state.ramp_start_show_ns || show_time_ns >= state.ramp_end_show_ns) {
        return state.target_value;
    }
    if (show_time_ns <= state.ramp_start_show_ns) return state.start_value;
    const auto elapsed = static_cast<double>(show_time_ns - state.ramp_start_show_ns);
    const auto duration = static_cast<double>(state.ramp_end_show_ns - state.ramp_start_show_ns);
    const auto t = duration > 0.0 ? elapsed / duration : 1.0;
    return static_cast<float>(static_cast<double>(state.start_value) +
                              (static_cast<double>(state.target_value) - static_cast<double>(state.start_value)) * t);
}

template <std::size_t MaxParameters = 256>
class CoreAutomationState final {
    static_assert(MaxParameters > 0, "automation state must have parameter capacity");

public:
    [[nodiscard]] AutomationApplyResult apply(const ShowEvent& event) noexcept {
        if (event.type != ShowEventType::automation || !show_event_is_valid(event) ||
            !std::isfinite(event.payload.automation.value)) {
            invalid_.fetch_add(1, std::memory_order_relaxed);
            return {AutomationApplyStatus::invalid, revision_.load(std::memory_order_acquire), 0};
        }

        auto* entry = find(event.payload.automation.target_id, event.payload.automation.parameter_id);
        if (!entry) entry = create(event.payload.automation.target_id, event.payload.automation.parameter_id);
        if (!entry) {
            capacity_rejections_.fetch_add(1, std::memory_order_relaxed);
            return {AutomationApplyStatus::capacity, revision_.load(std::memory_order_acquire), 0};
        }

        auto current = read(*entry);
        const bool release_owner = (event.flags & show_event_automation_release_owner) != 0;
        if (release_owner) {
            if (event.owner_id == 0 || current.owner_id == 0 || current.owner_id != event.owner_id) {
                owner_conflicts_.fetch_add(1, std::memory_order_relaxed);
                return {AutomationApplyStatus::owner_conflict, current.revision, current.owner_id};
            }
            current.owner_id = 0;
            current.last_event_id = event.event_id;
            current.revision = revision_.fetch_add(1, std::memory_order_acq_rel) + 1;
            current.updates += 1;
            publish(*entry, current);
            applied_.fetch_add(1, std::memory_order_relaxed);
            owner_releases_.fetch_add(1, std::memory_order_relaxed);
            return {AutomationApplyStatus::applied, current.revision, 0};
        }

        if (current.owner_id != 0 && current.owner_id != event.owner_id) {
            owner_conflicts_.fetch_add(1, std::memory_order_relaxed);
            return {AutomationApplyStatus::owner_conflict, current.revision, current.owner_id};
        }
        if (current.owner_id == 0 && event.owner_id != 0) current.owner_id = event.owner_id;

        const float start_value = automation_value_at(current, event.show_time_ns);
        const auto duration_ns = static_cast<std::uint64_t>(event.payload.automation.duration_ms) * 1'000'000ULL;
        current.start_value = duration_ns == 0 ? event.payload.automation.value : start_value;
        current.target_value = event.payload.automation.value;
        current.ramp_start_show_ns = event.show_time_ns;
        current.ramp_end_show_ns = event.show_time_ns + duration_ns;
        current.ramping = duration_ns != 0;
        current.current_value = duration_ns == 0 ? current.target_value : current.start_value;
        current.last_event_id = event.event_id;
        current.revision = revision_.fetch_add(1, std::memory_order_acq_rel) + 1;
        current.updates += 1;
        publish(*entry, current);
        applied_.fetch_add(1, std::memory_order_relaxed);
        return {AutomationApplyStatus::applied, current.revision, current.owner_id};
    }

    // Establishes the physical/current baseline before the first automation
    // event. This prevents a first ramp from implicitly starting at numeric zero.
    // Existing parameters that have already received automation are never overwritten.
    [[nodiscard]] bool seed(std::uint64_t target_id, std::uint64_t parameter_id, float value) noexcept {
        if (target_id == 0 || parameter_id == 0 || !std::isfinite(value)) return false;
        auto* entry = find(target_id, parameter_id);
        if (!entry) entry = create(target_id, parameter_id);
        if (!entry) return false;
        auto current = read(*entry);
        if (current.updates != 0 || current.last_event_id != 0) return false;
        current.start_value = value;
        current.target_value = value;
        current.current_value = value;
        current.ramp_start_show_ns = 0;
        current.ramp_end_show_ns = 0;
        current.ramping = false;
        publish(*entry, current);
        return true;
    }

    [[nodiscard]] bool snapshot(std::uint64_t target_id, std::uint64_t parameter_id,
                                std::uint64_t show_time_ns, AutomationParameterSnapshot& out) const noexcept {
        const auto* entry = find_const(target_id, parameter_id);
        if (!entry) return false;
        out = read(*entry);
        out.current_value = automation_value_at(out, show_time_ns);
        out.ramping = out.ramp_end_show_ns > out.ramp_start_show_ns && show_time_ns < out.ramp_end_show_ns;
        return true;
    }

    [[nodiscard]] bool render_block(std::uint64_t target_id, std::uint64_t parameter_id,
                                    std::uint64_t start_show_ns, std::uint64_t step_ns,
                                    float* output, std::size_t frames) const noexcept {
        if (!output || frames == 0) return false;
        const auto* entry = find_const(target_id, parameter_id);
        if (!entry) return false;
        const auto state = read(*entry);
        std::uint64_t show_ns = start_show_ns;
        for (std::size_t index = 0; index < frames; ++index) {
            output[index] = automation_value_at(state, show_ns);
            show_ns += step_ns;
        }
        return true;
    }

    [[nodiscard]] AutomationStateMetrics metrics() const noexcept {
        return AutomationStateMetrics{
            revision_.load(std::memory_order_acquire),
            registered_.load(std::memory_order_acquire),
            applied_.load(std::memory_order_relaxed),
            owner_conflicts_.load(std::memory_order_relaxed),
            capacity_rejections_.load(std::memory_order_relaxed),
            invalid_.load(std::memory_order_relaxed),
            owner_releases_.load(std::memory_order_relaxed)};
    }

private:
    struct PublishedState {
        std::uint64_t owner_id{0};
        std::uint64_t revision{0};
        std::uint64_t last_event_id{0};
        std::uint64_t ramp_start_show_ns{0};
        std::uint64_t ramp_end_show_ns{0};
        float start_value{0.0F};
        float target_value{0.0F};
        std::uint64_t updates{0};
    };

    struct Entry {
        std::atomic<bool> registered{false};
        std::uint64_t target_id{0};
        std::uint64_t parameter_id{0};
        std::array<PublishedState, 2> slots{};
        mutable std::array<std::atomic<std::uint32_t>, 2> readers{};
        std::atomic<std::uint8_t> active_slot{0};
    };

    [[nodiscard]] static AutomationParameterSnapshot to_snapshot(const Entry& entry, const PublishedState& state) noexcept {
        AutomationParameterSnapshot result{};
        result.registered = true;
        result.target_id = entry.target_id;
        result.parameter_id = entry.parameter_id;
        result.owner_id = state.owner_id;
        result.revision = state.revision;
        result.last_event_id = state.last_event_id;
        result.ramp_start_show_ns = state.ramp_start_show_ns;
        result.ramp_end_show_ns = state.ramp_end_show_ns;
        result.start_value = state.start_value;
        result.target_value = state.target_value;
        result.current_value = state.target_value;
        result.ramping = state.ramp_end_show_ns > state.ramp_start_show_ns;
        result.updates = state.updates;
        return result;
    }

    [[nodiscard]] static AutomationParameterSnapshot read(const Entry& entry) noexcept {
        for (;;) {
            const auto slot = entry.active_slot.load(std::memory_order_acquire);
            entry.readers[slot].fetch_add(1, std::memory_order_acquire);
            if (entry.active_slot.load(std::memory_order_acquire) != slot) {
                entry.readers[slot].fetch_sub(1, std::memory_order_release);
                continue;
            }
            const auto state = entry.slots[slot];
            entry.readers[slot].fetch_sub(1, std::memory_order_release);
            return to_snapshot(entry, state);
        }
    }

    static void publish(Entry& entry, const AutomationParameterSnapshot& snapshot) noexcept {
        PublishedState state{};
        state.owner_id = snapshot.owner_id;
        state.revision = snapshot.revision;
        state.last_event_id = snapshot.last_event_id;
        state.ramp_start_show_ns = snapshot.ramp_start_show_ns;
        state.ramp_end_show_ns = snapshot.ramp_end_show_ns;
        state.start_value = snapshot.start_value;
        state.target_value = snapshot.target_value;
        state.updates = snapshot.updates;

        const auto current = entry.active_slot.load(std::memory_order_acquire);
        const auto next = static_cast<std::uint8_t>(1U - current);
        while (entry.readers[next].load(std::memory_order_acquire) != 0) std::this_thread::yield();
        entry.slots[next] = state;
        entry.active_slot.store(next, std::memory_order_release);
    }

    [[nodiscard]] Entry* find(std::uint64_t target_id, std::uint64_t parameter_id) noexcept {
        for (auto& entry : entries_) {
            if (!entry.registered.load(std::memory_order_acquire)) continue;
            if (entry.target_id == target_id && entry.parameter_id == parameter_id) return &entry;
        }
        return nullptr;
    }

    [[nodiscard]] const Entry* find_const(std::uint64_t target_id, std::uint64_t parameter_id) const noexcept {
        for (const auto& entry : entries_) {
            if (!entry.registered.load(std::memory_order_acquire)) continue;
            if (entry.target_id == target_id && entry.parameter_id == parameter_id) return &entry;
        }
        return nullptr;
    }

    [[nodiscard]] Entry* create(std::uint64_t target_id, std::uint64_t parameter_id) noexcept {
        for (auto& entry : entries_) {
            if (entry.registered.load(std::memory_order_acquire)) continue;
            entry.target_id = target_id;
            entry.parameter_id = parameter_id;
            PublishedState initial{};
            entry.slots[0] = initial;
            entry.slots[1] = initial;
            entry.active_slot.store(0, std::memory_order_relaxed);
            entry.registered.store(true, std::memory_order_release);
            registered_.fetch_add(1, std::memory_order_release);
            return &entry;
        }
        return nullptr;
    }

    std::array<Entry, MaxParameters> entries_{};
    std::atomic<std::uint64_t> revision_{0};
    std::atomic<std::uint64_t> registered_{0};
    std::atomic<std::uint64_t> applied_{0};
    std::atomic<std::uint64_t> owner_conflicts_{0};
    std::atomic<std::uint64_t> capacity_rejections_{0};
    std::atomic<std::uint64_t> invalid_{0};
    std::atomic<std::uint64_t> owner_releases_{0};
};

} // namespace stagemesh
