#include "audio_conversion.h"
#include <cmath>
#include <cstdint>
#include <iostream>
#include <stdexcept>

using namespace stagemesh;
namespace { void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); } }

int main() {
    try {
        AudioConversionPlan plan{48000, 44100, 2, 2, AudioSampleFormat::Int16, AudioSampleFormat::Float32, 256, 256};
        require(validate_audio_conversion_plan(plan), "valid conversion plan rejected");
        std::int16_t pcm[] = {-32768, 0, 32767, 16384}; float decoded[4]{};
        require(decode_audio_float(pcm, AudioSampleFormat::Int16, 2, 2, decoded), "PCM decode failed");
        require(decoded[0] <= -0.99F && decoded[2] > 0.99F, "PCM decode values incorrect");
        float converted[4]{}; require(convert_audio_float(decoded, 2, 2, 48000, converted, 2, 2, 44100), "float conversion failed");
        std::int16_t encoded[4]{}; require(encode_audio_float(converted, AudioSampleFormat::Int16, 2, 2, encoded), "PCM encode failed");
        require(std::abs(encoded[0] - pcm[0]) < 2, "PCM roundtrip failed");
        std::cout << "{\"conversionPlanValidated\":true,\"pcmRoundtrip\":true,\"physicalOutputsArmed\":false}\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
