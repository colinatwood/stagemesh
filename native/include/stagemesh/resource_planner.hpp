#pragma once

#include "stagemesh/core_api.h"

#include <algorithm>
#include <cstddef>
#include <span>

namespace stagemesh {

enum class CoreOperatingMode : std::uint8_t {
    full = 0,
    reduced,
    safe_show,
    audio_only,
};

enum class CoreResourceAction : std::uint8_t {
    full = 0,
    degraded,
    suspended,
    unavailable,
};

enum class CoreResourceReason : std::uint8_t {
    within_budget = 0,
    unhealthy,
    disabled_by_mode,
    protected_under_pressure,
    suspended_for_headroom,
    cannot_fit,
};

struct CoreResourceRequest {
    sf_priority priority{SF_PRIORITY_BACKGROUND};
    float estimated_cpu_percent{0.0F};
    bool healthy{true};
    bool can_degrade{false};
    bool can_suspend{true};
    float degraded_cpu_fraction{0.35F};
};

struct CoreResourceDecision {
    CoreResourceAction action{CoreResourceAction::suspended};
    CoreResourceReason reason{CoreResourceReason::cannot_fit};
    float allocated_cpu_percent{0.0F};
};

struct CoreResourcePlanSummary {
    float capacity_percent{0.0F};
    float used_percent{0.0F};
    float headroom_percent{0.0F};
    std::size_t full_count{0};
    std::size_t degraded_count{0};
    std::size_t suspended_count{0};
    std::size_t unavailable_count{0};
};

class CoreResourcePlanner final {
public:
    [[nodiscard]] static CoreResourcePlanSummary plan(
        float capacity_percent,
        CoreOperatingMode mode,
        std::span<const CoreResourceRequest> requests,
        std::span<CoreResourceDecision> decisions) noexcept {
        CoreResourcePlanSummary summary{};
        summary.capacity_percent = std::clamp(capacity_percent, 0.0F, 100.0F);
        const auto count = std::min(requests.size(), decisions.size());
        const auto maximum_priority = max_priority(mode);

        for (std::size_t index = 0; index < count; ++index) {
            const auto& request = requests[index];
            auto& decision = decisions[index];
            const float requested_cpu = std::clamp(request.estimated_cpu_percent, 0.0F, 100.0F);

            if (!request.healthy) {
                decision = {CoreResourceAction::unavailable, CoreResourceReason::unhealthy, 0.0F};
                ++summary.unavailable_count;
                continue;
            }

            if (request.priority > maximum_priority) {
                if (request.can_suspend) {
                    decision = {CoreResourceAction::suspended, CoreResourceReason::disabled_by_mode, 0.0F};
                    ++summary.suspended_count;
                } else if (request.can_degrade) {
                    const float allocation = degraded_allocation(request, requested_cpu, summary.capacity_percent - summary.used_percent);
                    decision = {CoreResourceAction::degraded, CoreResourceReason::disabled_by_mode, allocation};
                    summary.used_percent += allocation;
                    ++summary.degraded_count;
                } else {
                    decision = {CoreResourceAction::unavailable, CoreResourceReason::disabled_by_mode, 0.0F};
                    ++summary.unavailable_count;
                }
                continue;
            }

            if (summary.used_percent + requested_cpu <= summary.capacity_percent) {
                decision = {CoreResourceAction::full, CoreResourceReason::within_budget, requested_cpu};
                summary.used_percent += requested_cpu;
                ++summary.full_count;
                continue;
            }

            const bool protected_priority = request.priority <= SF_PRIORITY_SHOW;
            if (protected_priority && request.can_degrade) {
                const float allocation = degraded_allocation(request, requested_cpu, summary.capacity_percent - summary.used_percent);
                decision = {CoreResourceAction::degraded, CoreResourceReason::protected_under_pressure, allocation};
                summary.used_percent += allocation;
                ++summary.degraded_count;
            } else if (request.can_suspend) {
                decision = {CoreResourceAction::suspended, CoreResourceReason::suspended_for_headroom, 0.0F};
                ++summary.suspended_count;
            } else if (request.can_degrade) {
                const float allocation = degraded_allocation(request, requested_cpu, summary.capacity_percent - summary.used_percent);
                decision = {CoreResourceAction::degraded, CoreResourceReason::protected_under_pressure, allocation};
                summary.used_percent += allocation;
                ++summary.degraded_count;
            } else {
                decision = {CoreResourceAction::unavailable, CoreResourceReason::cannot_fit, 0.0F};
                ++summary.unavailable_count;
            }
        }

        summary.used_percent = std::clamp(summary.used_percent, 0.0F, summary.capacity_percent);
        summary.headroom_percent = std::max(0.0F, summary.capacity_percent - summary.used_percent);
        return summary;
    }

private:
    [[nodiscard]] static sf_priority max_priority(CoreOperatingMode mode) noexcept {
        switch (mode) {
            case CoreOperatingMode::full: return SF_PRIORITY_BACKGROUND;
            case CoreOperatingMode::reduced: return SF_PRIORITY_VISUAL;
            case CoreOperatingMode::safe_show: return SF_PRIORITY_PRODUCTION;
            case CoreOperatingMode::audio_only: return SF_PRIORITY_CRITICAL;
        }
        return SF_PRIORITY_PRODUCTION;
    }

    [[nodiscard]] static float degraded_allocation(const CoreResourceRequest& request, float requested_cpu, float remaining) noexcept {
        const float fraction = std::clamp(request.degraded_cpu_fraction, 0.05F, 1.0F);
        const float desired = std::max(1.0F, requested_cpu * fraction);
        return std::clamp(desired, 0.0F, std::max(0.0F, remaining));
    }
};

} // namespace stagemesh
