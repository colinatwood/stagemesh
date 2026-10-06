#pragma once

#include <algorithm>
#include <cstdint>
#include <limits>

namespace stagemesh {

struct EndpointTimingProfile {
    std::uint64_t fixed_latency_ns{0};
    std::uint64_t jitter_ns{0};
    std::uint64_t minimum_lookahead_ns{0};
    std::uint8_t jitter_margin_multiplier{2};
    bool supports_timestamped_execution{true};
};

struct TimingPlan {
    std::uint64_t target_time_ns{0};
    std::uint64_t dispatch_time_ns{0};
    std::uint64_t reserve_ns{0};
    bool late{false};
    bool timestamped{false};
};

class LatencyResolver {
public:
    [[nodiscard]] static TimingPlan plan(
        std::uint64_t now_ns,
        std::uint64_t target_time_ns,
        const EndpointTimingProfile& profile) noexcept {
        const auto jitter_margin = saturating_multiply(profile.jitter_ns, profile.jitter_margin_multiplier);
        const auto path_requirement = saturating_add(profile.fixed_latency_ns, jitter_margin);
        const auto reserve = std::max(path_requirement, profile.minimum_lookahead_ns);
        const auto dispatch = target_time_ns > reserve ? target_time_ns - reserve : 0;
        return TimingPlan{
            target_time_ns,
            dispatch,
            reserve,
            now_ns > dispatch,
            profile.supports_timestamped_execution,
        };
    }

private:
    [[nodiscard]] static std::uint64_t saturating_add(std::uint64_t a, std::uint64_t b) noexcept {
        const auto max = std::numeric_limits<std::uint64_t>::max();
        return b > max - a ? max : a + b;
    }

    [[nodiscard]] static std::uint64_t saturating_multiply(std::uint64_t value, std::uint8_t multiplier) noexcept {
        if (multiplier == 0 || value == 0) {
            return 0;
        }
        const auto max = std::numeric_limits<std::uint64_t>::max();
        return value > max / multiplier ? max : value * multiplier;
    }
};

} // namespace stagemesh
