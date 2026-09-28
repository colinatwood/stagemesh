#pragma once

#include "audio_preflight.h"
#include <cstdint>

namespace stageforge {

// Bounded, allocation-free conversion primitives. Callers own the buffers;
// these functions never resize or retain memory and are suitable for a
// preallocated callback adapter.
struct AudioConversionPlan {
    std::uint32_t input_rate_hz = 0;
    std::uint32_t output_rate_hz = 0;
    std::uint32_t input_channels = 0;
    std::uint32_t output_channels = 0;
    AudioSampleFormat input_format = AudioSampleFormat::Unknown;
    AudioSampleFormat output_format = AudioSampleFormat::Unknown;
    std::uint32_t max_input_frames = 0;
    std::uint32_t max_output_frames = 0;
};

bool validate_audio_conversion_plan(const AudioConversionPlan& plan) noexcept;

// Decode interleaved PCM into float32. output must have at least
// input_frames * input_channels elements.
bool decode_audio_float(const void* input, AudioSampleFormat format,
                        std::uint32_t frames, std::uint32_t channels,
                        float* output) noexcept;

// Encode float32 into interleaved PCM. output must have at least
// frames * channels elements in the selected format.
bool encode_audio_float(const float* input, AudioSampleFormat format,
                        std::uint32_t frames, std::uint32_t channels,
                        void* output) noexcept;

// Resample and map channels in one bounded operation. The input and output
// buffers are float32 and must be preallocated by the caller.
bool convert_audio_float(const float* input, std::uint32_t input_frames,
                         std::uint32_t input_channels, std::uint32_t input_rate_hz,
                         float* output, std::uint32_t output_frames,
                         std::uint32_t output_channels, std::uint32_t output_rate_hz) noexcept;

} // namespace stageforge
