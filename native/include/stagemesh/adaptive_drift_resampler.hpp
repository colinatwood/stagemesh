#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

struct AdaptiveDriftConfig {
    double max_correction_ppm{2000.0};
    double queue_gain_ppm{1000.0};
    double smoothing{0.05};
};

// Per-sink controller. It never changes show time. It only adjusts how many
// source frames a physical sink consumes for each hardware output block.
class AdaptiveDriftController final {
public:
    explicit AdaptiveDriftController(AdaptiveDriftConfig config = {}) noexcept : config_(config) {}

    void configure(AdaptiveDriftConfig config) noexcept {
        config_ = config;
        reset();
    }

    void reset() noexcept {
        correction_ppm_ = 0.0;
        frame_fraction_ = 0.0;
        compensated_blocks_ = 0;
    }

    double update(double measured_rate_ppm, bool rate_valid, std::size_t queued_frames, std::size_t target_frames) noexcept {
        const double target = static_cast<double>(std::max<std::size_t>(1, target_frames));
        const double queue_error = std::clamp((static_cast<double>(queued_frames) - target) / target, -2.0, 2.0);
        const double rate_term = rate_valid && std::isfinite(measured_rate_ppm) ? -measured_rate_ppm : 0.0;
        const double desired = std::clamp(
            rate_term + queue_error * config_.queue_gain_ppm,
            -std::abs(config_.max_correction_ppm),
            std::abs(config_.max_correction_ppm));
        const double alpha = std::clamp(config_.smoothing, 0.001, 1.0);
        correction_ppm_ += (desired - correction_ppm_) * alpha;
        return correction_ppm_;
    }

    [[nodiscard]] std::uint32_t source_frames_for(std::uint32_t output_frames) noexcept {
        if (output_frames == 0) return 0;
        const double ratio = std::max(0.5, 1.0 + correction_ppm_ / 1'000'000.0);
        const double exact = static_cast<double>(output_frames) * ratio + frame_fraction_;
        auto source_frames = static_cast<std::uint32_t>(std::floor(exact));
        frame_fraction_ = exact - static_cast<double>(source_frames);
        const auto low = output_frames > 8 ? output_frames - 8 : 1U;
        const auto high = output_frames + 8;
        source_frames = std::clamp(source_frames, low, high);
        if (source_frames != output_frames) ++compensated_blocks_;
        return source_frames;
    }

    [[nodiscard]] double correction_ppm() const noexcept { return correction_ppm_; }
    [[nodiscard]] std::uint64_t compensated_blocks() const noexcept { return compensated_blocks_; }

private:
    AdaptiveDriftConfig config_{};
    double correction_ppm_{0.0};
    double frame_fraction_{0.0};
    std::uint64_t compensated_blocks_{0};
};

inline void resample_planar_linear(
    const float* input_left,
    const float* input_right,
    std::uint32_t input_frames,
    float* output_left,
    float* output_right,
    std::uint32_t output_frames) noexcept {
    if (!output_left || !output_right || output_frames == 0) return;
    if (!input_left || !input_right || input_frames == 0) {
        std::fill_n(output_left, output_frames, 0.0F);
        std::fill_n(output_right, output_frames, 0.0F);
        return;
    }
    if (input_frames == output_frames) {
        std::copy_n(input_left, output_frames, output_left);
        std::copy_n(input_right, output_frames, output_right);
        return;
    }
    if (input_frames == 1 || output_frames == 1) {
        std::fill_n(output_left, output_frames, input_left[0]);
        std::fill_n(output_right, output_frames, input_right[0]);
        return;
    }
    const double step = static_cast<double>(input_frames - 1) / static_cast<double>(output_frames - 1);
    for (std::uint32_t out = 0; out < output_frames; ++out) {
        const double position = step * static_cast<double>(out);
        const auto index = static_cast<std::uint32_t>(position);
        const auto next = std::min<std::uint32_t>(index + 1, input_frames - 1);
        const float fraction = static_cast<float>(position - static_cast<double>(index));
        output_left[out] = input_left[index] + (input_left[next] - input_left[index]) * fraction;
        output_right[out] = input_right[index] + (input_right[next] - input_right[index]) * fraction;
    }
}

} // namespace stagemesh
