#include "stagemesh/monitor_mixer.hpp"

#include <algorithm>

namespace stagemesh {

float MonitorMixer::gain(float percent) noexcept {
    return std::clamp(percent, 0.0F, 100.0F) * 0.01F;
}

void MonitorMixer::mix(
    const MonitorBus& bus,
    std::span<const MonitorSourceBlock> sources,
    float* output_left,
    float* output_right,
    std::size_t frames) noexcept {
    if (!output_left || !output_right || frames == 0) {
        return;
    }

    std::fill_n(output_left, frames, 0.0F);
    std::fill_n(output_right, frames, 0.0F);
    if (bus.muted()) {
        return;
    }

    const float master = gain(bus.master());
    for (const auto& source : sources) {
        if (!source.samples) {
            continue;
        }
        const float source_gain = gain(bus.level(source.channel)) * master;
        for (std::size_t frame = 0; frame < frames; ++frame) {
            const float sample = source.samples[frame] * source_gain;
            output_left[frame] += sample;
            output_right[frame] += sample;
        }
    }
}

} // namespace stagemesh
