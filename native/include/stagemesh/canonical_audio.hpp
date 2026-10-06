#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string_view>

namespace stagemesh {

inline constexpr double canonical_audio_sample_rate = 192000.0;
inline constexpr std::uint32_t canonical_audio_bits = 32;

enum class CanonicalAudioSampleFormat : std::uint8_t { float32=0, signed16=1, signed24=2, signed32=3 };

inline constexpr std::string_view canonical_audio_sample_format_name(CanonicalAudioSampleFormat format) noexcept {
    switch (format) {
    case CanonicalAudioSampleFormat::float32: return "FLOAT_LE";
    case CanonicalAudioSampleFormat::signed16: return "S16_LE";
    case CanonicalAudioSampleFormat::signed24: return "S24_3LE";
    case CanonicalAudioSampleFormat::signed32: return "S32_LE";
    }
    return "unknown";
}

inline bool canonical_audio_sample_format_from_name(std::string_view name, CanonicalAudioSampleFormat& format) noexcept {
    if (name == "FLOAT_LE") { format = CanonicalAudioSampleFormat::float32; return true; }
    if (name == "S16_LE") { format = CanonicalAudioSampleFormat::signed16; return true; }
    if (name == "S24_3LE") { format = CanonicalAudioSampleFormat::signed24; return true; }
    if (name == "S32_LE") { format = CanonicalAudioSampleFormat::signed32; return true; }
    return false;
}

inline constexpr std::size_t canonical_audio_sample_bytes(CanonicalAudioSampleFormat format) noexcept {
    switch (format) {
    case CanonicalAudioSampleFormat::float32: return sizeof(float);
    case CanonicalAudioSampleFormat::signed16: return sizeof(std::int16_t);
    case CanonicalAudioSampleFormat::signed24: return 3U;
    case CanonicalAudioSampleFormat::signed32: return sizeof(std::int32_t);
    }
    return 0U;
}

struct CanonicalAudioFormat {
    double sample_rate{canonical_audio_sample_rate};
    std::uint32_t bits_per_sample{canonical_audio_bits};
    std::uint32_t channels{2};
    CanonicalAudioSampleFormat sample_format{CanonicalAudioSampleFormat::float32};
    bool planar{true};
};
struct CanonicalRateConversionStatus {
    double source_rate{0.0};
    double destination_rate{canonical_audio_sample_rate};
    std::uint64_t input_frames{0}, output_frames{0}, converted_blocks{0}, rejected_blocks{0};
};

// Convert common interleaved device PCM to/from the float32 execution domain.
// These helpers are bounded and allocation-free. Channel layout policy is kept
// separate: callers may retain every device channel, or normalize the first
// stereo pair into the canonical two-channel graph.
inline float decode_interleaved_pcm_sample(
    const std::uint8_t* bytes,
    CanonicalAudioSampleFormat format,
    std::size_t sample) noexcept {
    switch (format) {
    case CanonicalAudioSampleFormat::float32: {
        float value{};
        std::memcpy(&value, bytes + sample * sizeof(float), sizeof(value));
        return std::isfinite(value) ? value : 0.0F;
    }
    case CanonicalAudioSampleFormat::signed16: {
        std::int16_t value{};
        std::memcpy(&value, bytes + sample * sizeof(value), sizeof(value));
        return static_cast<float>(value) / 32768.0F;
    }
    case CanonicalAudioSampleFormat::signed24: {
        const auto* p = bytes + sample * 3U;
        std::int32_t value = static_cast<std::int32_t>(p[0]) |
                             (static_cast<std::int32_t>(p[1]) << 8U) |
                             (static_cast<std::int32_t>(p[2]) << 16U);
        if ((value & 0x00800000) != 0) value |= static_cast<std::int32_t>(0xff000000);
        return static_cast<float>(value) / 8388608.0F;
    }
    case CanonicalAudioSampleFormat::signed32: {
        std::int32_t value{};
        std::memcpy(&value, bytes + sample * sizeof(value), sizeof(value));
        return static_cast<float>(static_cast<double>(value) / 2147483648.0);
    }
    }
    return 0.0F;
}

inline bool decode_interleaved_pcm(
    const void* input,
    CanonicalAudioSampleFormat format,
    std::uint32_t frames,
    std::uint32_t channels,
    float* output_interleaved) noexcept {
    if (!input || !output_interleaved || frames == 0 || channels == 0) return false;
    const auto* bytes = static_cast<const std::uint8_t*>(input);
    const auto samples = static_cast<std::size_t>(frames) * channels;
    for (std::size_t sample = 0; sample < samples; ++sample) {
        output_interleaved[sample] = decode_interleaved_pcm_sample(bytes, format, sample);
    }
    return true;
}

inline std::int64_t quantize_signed_pcm(float raw, std::int64_t minimum, std::int64_t maximum, double scale) noexcept {
    const double value = std::isfinite(raw) ? std::clamp(static_cast<double>(raw), -1.0, 1.0) : 0.0;
    if (value <= -1.0) return minimum;
    if (value >= 1.0) return maximum;
    return std::clamp<std::int64_t>(static_cast<std::int64_t>(std::llround(value * scale)), minimum, maximum);
}

inline bool encode_interleaved_pcm(
    const float* input_interleaved,
    CanonicalAudioSampleFormat format,
    std::uint32_t frames,
    std::uint32_t channels,
    void* output) noexcept {
    if (!input_interleaved || !output || frames == 0 || channels == 0) return false;
    auto* bytes = static_cast<std::uint8_t*>(output);
    const auto samples = static_cast<std::size_t>(frames) * channels;
    for (std::size_t sample = 0; sample < samples; ++sample) {
        const float raw = std::isfinite(input_interleaved[sample]) ? input_interleaved[sample] : 0.0F;
        switch (format) {
        case CanonicalAudioSampleFormat::float32:
            std::memcpy(bytes + sample * sizeof(float), &raw, sizeof(raw));
            break;
        case CanonicalAudioSampleFormat::signed16: {
            const auto value = static_cast<std::int16_t>(quantize_signed_pcm(raw, -32768, 32767, 32768.0));
            std::memcpy(bytes + sample * sizeof(value), &value, sizeof(value));
            break;
        }
        case CanonicalAudioSampleFormat::signed24: {
            const auto value = static_cast<std::int32_t>(quantize_signed_pcm(raw, -8388608, 8388607, 8388608.0));
            auto* p = bytes + sample * 3U;
            p[0] = static_cast<std::uint8_t>(value & 0xff);
            p[1] = static_cast<std::uint8_t>((value >> 8U) & 0xff);
            p[2] = static_cast<std::uint8_t>((value >> 16U) & 0xff);
            break;
        }
        case CanonicalAudioSampleFormat::signed32: {
            const auto value = static_cast<std::int32_t>(quantize_signed_pcm(
                raw,
                static_cast<std::int64_t>(std::numeric_limits<std::int32_t>::min()),
                static_cast<std::int64_t>(std::numeric_limits<std::int32_t>::max()),
                2147483648.0));
            std::memcpy(bytes + sample * sizeof(value), &value, sizeof(value));
            break;
        }
        }
    }
    return true;
}

// Decode device PCM into the canonical stereo pair. Mono is duplicated. For a
// multichannel device the v1 explicit matrix is deterministic: device channels
// 0/1 map to canonical L/R and additional channels are intentionally ignored.
inline bool normalize_interleaved_pcm(const void* input, CanonicalAudioSampleFormat format,
                                      std::uint32_t frames, std::uint32_t channels,
                                      float* output_left, float* output_right) noexcept {
    if (!input || !output_left || !output_right || frames == 0 || channels == 0) return false;
    const auto* bytes = static_cast<const std::uint8_t*>(input);
    const std::uint32_t right_channel = channels > 1 ? 1U : 0U;
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
        const std::size_t base = static_cast<std::size_t>(frame) * channels;
        output_left[frame] = decode_interleaved_pcm_sample(bytes, format, base);
        output_right[frame] = decode_interleaved_pcm_sample(bytes, format, base + right_channel);
    }
    return true;
}

// Fixed 16-tap windowed-sinc conversion. This is a bounded, allocation-free
// rate-domain primitive; clock drift remains a separate small ratio correction.
inline void resample_planar_sinc(const float* input_left,const float* input_right,std::uint32_t input_frames,
                                 float* output_left,float* output_right,std::uint32_t output_frames) noexcept {
    if(!output_left||!output_right||output_frames==0)return;
    if(!input_left||!input_right||input_frames==0){std::fill_n(output_left,output_frames,0.0F);std::fill_n(output_right,output_frames,0.0F);return;}
    if(input_frames==output_frames){std::copy_n(input_left,output_frames,output_left);std::copy_n(input_right,output_frames,output_right);return;}
    constexpr int radius=8; constexpr double pi=3.14159265358979323846;
    const double step=static_cast<double>(input_frames)/static_cast<double>(output_frames);
    const double cutoff=std::min(1.0,static_cast<double>(output_frames)/static_cast<double>(input_frames));
    for(std::uint32_t out=0;out<output_frames;++out){
        const double position=(static_cast<double>(out)+0.5)*step-0.5;const int center=static_cast<int>(std::floor(position));
        double sum_l=0.0,sum_r=0.0,sum_w=0.0;
        for(int tap=-radius+1;tap<=radius;++tap){const double distance=position-static_cast<double>(center+tap);const double x=distance*cutoff;
            const double sinc=std::abs(x)<1.0e-12?1.0:std::sin(pi*x)/(pi*x);const double window=0.5+0.5*std::cos(pi*distance/static_cast<double>(radius));const double weight=cutoff*sinc*window;
            const auto index=static_cast<std::uint32_t>(std::clamp(center+tap,0,static_cast<int>(input_frames)-1));sum_l+=input_left[index]*weight;sum_r+=input_right[index]*weight;sum_w+=weight;}
        if(std::abs(sum_w)<1.0e-12){output_left[out]=0.0F;output_right[out]=0.0F;}else{output_left[out]=static_cast<float>(sum_l/sum_w);output_right[out]=static_cast<float>(sum_r/sum_w);}
    }
}

class CanonicalAudioRateConverter final {
public:
    [[nodiscard]] bool configure(double source_rate,double destination_rate=canonical_audio_sample_rate) noexcept {
        if(!std::isfinite(source_rate)||!std::isfinite(destination_rate)||source_rate<8000.0||source_rate>768000.0||destination_rate<8000.0||destination_rate>768000.0)return false;
        status_={source_rate,destination_rate,0,0,0,0};fraction_=0.0;return true;
    }
    [[nodiscard]] std::uint32_t output_frames_for(std::uint32_t input_frames) noexcept {
        if (status_.source_rate <= 0.0 || input_frames == 0) return 0;
        const double exact = static_cast<double>(input_frames) * status_.destination_rate / status_.source_rate + fraction_;
        const auto frames = static_cast<std::uint32_t>(std::floor(exact));
        fraction_ = exact - static_cast<double>(frames);
        return frames;
    }
    [[nodiscard]] bool process(const float* left,const float* right,std::uint32_t input_frames,float* out_left,float* out_right,std::uint32_t output_frames) noexcept {
        if(status_.source_rate<=0.0||!left||!right||!out_left||!out_right||input_frames==0||output_frames==0){++status_.rejected_blocks;return false;}
        resample_planar_sinc(left,right,input_frames,out_left,out_right,output_frames);status_.input_frames+=input_frames;status_.output_frames+=output_frames;++status_.converted_blocks;return true;
    }
    [[nodiscard]] CanonicalRateConversionStatus status()const noexcept{return status_;}
private:CanonicalRateConversionStatus status_{};double fraction_{0.0};
};
} // namespace stagemesh
