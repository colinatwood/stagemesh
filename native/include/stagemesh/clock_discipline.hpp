#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>

namespace stagemesh {

enum class ClockDisciplineState : std::uint8_t {
    free_running = 0,
    locked = 1,
    holdover = 2,
};

struct ClockDisciplineSnapshot {
    ClockDisciplineState state{ClockDisciplineState::free_running};
    std::int64_t offset_ns{0};
    double drift_ppm{0.0};
    std::uint64_t source_age_ns{0};
    std::uint64_t projected_time_ns{0};
    std::uint64_t observations{0};
};

// Lightweight clock disciplining primitive for PTP/MTC/Link/etc. adapters.
// Adapters submit paired local/source timestamps. The core estimates rate and
// gently corrects phase rather than jumping the timeline. When observations
// stop it enters holdover and keeps projecting with the last learned rate.
class ClockDiscipline {
public:
    explicit ClockDiscipline(std::uint64_t holdover_timeout_ns = 1'000'000'000ULL) noexcept
        : holdover_timeout_ns_(holdover_timeout_ns) {}

    void reset() noexcept {
        state_ = ClockDisciplineState::free_running;
        anchor_local_ns_ = 0;
        anchor_source_ns_ = 0;
        last_observation_local_ns_ = 0;
        previous_local_ns_ = 0;
        previous_source_ns_ = 0;
        drift_ppm_ = 0.0;
        observations_ = 0;
    }

    void set_holdover_timeout(std::uint64_t timeout_ns) noexcept {
        holdover_timeout_ns_ = std::max<std::uint64_t>(1, timeout_ns);
    }

    void observe(std::uint64_t local_ns, std::uint64_t source_ns) noexcept {
        if (observations_ == 0) {
            anchor_local_ns_ = local_ns;
            anchor_source_ns_ = source_ns;
            previous_local_ns_ = local_ns;
            previous_source_ns_ = source_ns;
            last_observation_local_ns_ = local_ns;
            observations_ = 1;
            state_ = ClockDisciplineState::locked;
            return;
        }

        const auto predicted = project_unchecked(local_ns);
        const auto error = signed_difference(source_ns, predicted);

        // Correct only 20% of phase error on each observation. This keeps a
        // recovered source from abruptly jumping downstream show timestamps.

        const auto local_delta = local_ns > previous_local_ns_ ? local_ns - previous_local_ns_ : 0;
        if (local_delta > 0 && source_ns >= previous_source_ns_) {
            const auto source_delta = source_ns - previous_source_ns_;
            const auto measured_ppm = (static_cast<double>(source_delta) - static_cast<double>(local_delta)) /
                                      static_cast<double>(local_delta) * 1'000'000.0;
            const auto clamped = std::clamp(measured_ppm, -500.0, 500.0);
            drift_ppm_ = observations_ < 2 ? clamped : (drift_ppm_ * 0.90 + clamped * 0.10);
        }

        // Re-anchor around the softly corrected prediction plus residual phase.
        const auto corrected = add_signed(predicted, static_cast<std::int64_t>(std::llround(static_cast<double>(error) * 0.20)));
        anchor_local_ns_ = local_ns;
        anchor_source_ns_ = corrected;
        previous_local_ns_ = local_ns;
        previous_source_ns_ = source_ns;
        last_observation_local_ns_ = local_ns;
        ++observations_;
        state_ = ClockDisciplineState::locked;
    }

    [[nodiscard]] std::uint64_t project(std::uint64_t local_ns) noexcept {
        update_state(local_ns);
        return project_unchecked(local_ns);
    }

    [[nodiscard]] ClockDisciplineSnapshot snapshot(std::uint64_t local_ns) noexcept {
        update_state(local_ns);
        const auto projected = project_unchecked(local_ns);
        return ClockDisciplineSnapshot{
            state_,
            signed_difference(projected, local_ns),
            drift_ppm_,
            last_observation_local_ns_ == 0 || local_ns < last_observation_local_ns_ ? 0 : local_ns - last_observation_local_ns_,
            projected,
            observations_,
        };
    }

private:
    void update_state(std::uint64_t local_ns) noexcept {
        if (observations_ == 0) {
            state_ = ClockDisciplineState::free_running;
            return;
        }
        const auto age = local_ns >= last_observation_local_ns_ ? local_ns - last_observation_local_ns_ : 0;
        state_ = age > holdover_timeout_ns_ ? ClockDisciplineState::holdover : ClockDisciplineState::locked;
    }

    [[nodiscard]] std::uint64_t project_unchecked(std::uint64_t local_ns) const noexcept {
        if (observations_ == 0) {
            return local_ns;
        }
        const auto delta = signed_difference(local_ns, anchor_local_ns_);
        const auto scaled = static_cast<double>(delta) * (1.0 + drift_ppm_ / 1'000'000.0);
        return add_signed(anchor_source_ns_, static_cast<std::int64_t>(std::llround(scaled)));
    }

    [[nodiscard]] static std::int64_t signed_difference(std::uint64_t a, std::uint64_t b) noexcept {
        if (a >= b) {
            const auto delta = a - b;
            return delta > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())
                ? std::numeric_limits<std::int64_t>::max()
                : static_cast<std::int64_t>(delta);
        }
        const auto delta = b - a;
        return delta > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())
            ? std::numeric_limits<std::int64_t>::min()
            : -static_cast<std::int64_t>(delta);
    }

    [[nodiscard]] static std::uint64_t add_signed(std::uint64_t base, std::int64_t delta) noexcept {
        if (delta >= 0) {
            const auto amount = static_cast<std::uint64_t>(delta);
            return amount > std::numeric_limits<std::uint64_t>::max() - base
                ? std::numeric_limits<std::uint64_t>::max()
                : base + amount;
        }
        // Avoid negating INT64_MIN directly.
        const auto amount = static_cast<std::uint64_t>(-(delta + 1)) + 1;
        return amount > base ? 0 : base - amount;
    }

    ClockDisciplineState state_{ClockDisciplineState::free_running};
    std::uint64_t holdover_timeout_ns_{1'000'000'000ULL};
    std::uint64_t anchor_local_ns_{0};
    std::uint64_t anchor_source_ns_{0};
    std::uint64_t last_observation_local_ns_{0};
    std::uint64_t previous_local_ns_{0};
    std::uint64_t previous_source_ns_{0};
    double drift_ppm_{0.0};
    std::uint64_t observations_{0};
};

} // namespace stagemesh
