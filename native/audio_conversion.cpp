#include "audio_conversion.h"
#include <algorithm>
#include <cmath>
#include <cstring>

namespace stageforge {
namespace {
float clamp_sample(float value) noexcept { return std::clamp(value, -1.0F, 1.0F); }
float read_sample(const std::uint8_t* p, AudioSampleFormat format) noexcept {
    switch (format) {
    case AudioSampleFormat::Float32: { float v; std::memcpy(&v, p, sizeof(v)); return std::isfinite(v) ? v : 0.0F; }
    case AudioSampleFormat::Int16: { std::int16_t v; std::memcpy(&v, p, sizeof(v)); return static_cast<float>(v) / 32768.0F; }
    case AudioSampleFormat::Int24Packed: {
        std::int32_t v = static_cast<std::int32_t>(p[0]) | (static_cast<std::int32_t>(p[1]) << 8) | (static_cast<std::int32_t>(p[2]) << 16);
        if (v & 0x800000) v |= ~0xFFFFFF;
        return static_cast<float>(v) / 8388608.0F;
    }
    case AudioSampleFormat::Int32: { std::int32_t v; std::memcpy(&v, p, sizeof(v)); return static_cast<float>(static_cast<double>(v) / 2147483648.0); }
    default: return 0.0F;
    }
}
std::uint32_t bytes_per_sample(AudioSampleFormat format) noexcept {
    switch (format) { case AudioSampleFormat::Float32: case AudioSampleFormat::Int32: return 4; case AudioSampleFormat::Int24Packed: return 3; case AudioSampleFormat::Int16: return 2; default: return 0; }
}
}

bool validate_audio_conversion_plan(const AudioConversionPlan& plan) noexcept {
    return plan.input_rate_hz && plan.output_rate_hz && plan.input_channels && plan.output_channels &&
        plan.max_input_frames && plan.max_output_frames && bytes_per_sample(plan.input_format) && bytes_per_sample(plan.output_format);
}

bool decode_audio_float(const void* input, AudioSampleFormat format, std::uint32_t frames,
                        std::uint32_t channels, float* output) noexcept {
    const auto width = bytes_per_sample(format);
    if (!input || !output || !width || !channels) return false;
    const auto* bytes = static_cast<const std::uint8_t*>(input);
    for (std::uint64_t i = 0; i < static_cast<std::uint64_t>(frames) * channels; ++i) output[i] = read_sample(bytes + i * width, format);
    return true;
}

bool encode_audio_float(const float* input, AudioSampleFormat format, std::uint32_t frames,
                        std::uint32_t channels, void* output) noexcept {
    const auto width = bytes_per_sample(format);
    if (!input || !output || !width || !channels) return false;
    auto* bytes = static_cast<std::uint8_t*>(output);
    for (std::uint64_t i = 0; i < static_cast<std::uint64_t>(frames) * channels; ++i) {
        const auto v = clamp_sample(input[i]); auto* p = bytes + i * width;
        if (format == AudioSampleFormat::Float32) std::memcpy(p, &v, sizeof(v));
        else if (format == AudioSampleFormat::Int16) { const auto x = static_cast<std::int16_t>(std::lrint(v * 32767.0F)); std::memcpy(p, &x, sizeof(x)); }
        else if (format == AudioSampleFormat::Int24Packed) { const auto x = static_cast<std::int32_t>(std::lrint(v * 8388607.0F)); p[0] = static_cast<std::uint8_t>(x); p[1] = static_cast<std::uint8_t>(x >> 8); p[2] = static_cast<std::uint8_t>(x >> 16); }
        else if (format == AudioSampleFormat::Int32) { const auto x = static_cast<std::int32_t>(std::llround(static_cast<double>(v) * 2147483647.0)); std::memcpy(p, &x, sizeof(x)); }
    }
    return true;
}

bool convert_audio_float(const float* input, std::uint32_t input_frames, std::uint32_t input_channels,
                         std::uint32_t input_rate_hz, float* output, std::uint32_t output_frames,
                         std::uint32_t output_channels, std::uint32_t output_rate_hz) noexcept {
    if (!input || !output || !input_frames || !output_frames || !input_channels || !output_channels || !input_rate_hz || !output_rate_hz) return false;
    for (std::uint32_t frame = 0; frame < output_frames; ++frame) {
        const double source = static_cast<double>(frame) * input_rate_hz / output_rate_hz;
        const auto left = static_cast<std::uint32_t>(std::min<double>(std::floor(source), input_frames - 1));
        const auto right = std::min(left + 1, input_frames - 1u);
        const float mix = static_cast<float>(source - left);
        for (std::uint32_t channel = 0; channel < output_channels; ++channel) {
            const auto source_channel = std::min(channel, input_channels - 1u);
            const float a = input[left * input_channels + source_channel];
            const float b = input[right * input_channels + source_channel];
            output[frame * output_channels + channel] = a + (b - a) * mix;
        }
    }
    return true;
}
} // namespace stageforge
