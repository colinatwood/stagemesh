#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace stagemesh {
struct DeviceSelection;

enum class AudioDirection { Playback, Capture };
enum class AudioSampleFormat { Unknown, Float32, Int16, Int24Packed, Int32 };
enum class AudioPreflightStatus { Exact, ExplicitAdaptation, Unsupported, NoEndpoint };

struct AudioRateRange {
    double minimum_hz = 0.0;
    double maximum_hz = 0.0;
};

struct AudioRequest {
    AudioDirection direction = AudioDirection::Playback;
    std::uint32_t sample_rate_hz = 48000;
    std::uint32_t period_frames = 256;
    std::uint32_t channels = 2;
    AudioSampleFormat format = AudioSampleFormat::Float32;
    bool allow_rate_conversion = false;
    bool allow_period_adaptation = false;
    bool allow_channel_conversion = false;
    bool allow_format_conversion = false;
};

struct AudioHostCapabilities {
    std::string backend;
    bool endpoint_present = false;
    std::string endpoint_identity_hash;
    bool endpoint_identity_strong = false;
    std::uint32_t native_sample_rate_hz = 0;
    std::uint32_t default_period_frames = 0;
    std::uint32_t minimum_period_frames = 0;
    std::uint32_t maximum_period_frames = 0;
    std::uint32_t input_channels = 0;
    std::uint32_t output_channels = 0;
    AudioSampleFormat client_format = AudioSampleFormat::Unknown;
    std::vector<AudioRateRange> supported_sample_rates;
};

struct AudioPreflightDecision {
    AudioPreflightStatus status = AudioPreflightStatus::Unsupported;
    std::uint32_t configured_sample_rate_hz = 0;
    std::uint32_t configured_period_frames = 0;
    std::uint32_t configured_channels = 0;
    AudioSampleFormat configured_format = AudioSampleFormat::Unknown;
    bool rate_conversion = false;
    bool period_adaptation = false;
    bool channel_conversion = false;
    bool format_conversion = false;
    std::string reason;
};

AudioHostCapabilities probe_default_audio_endpoint(AudioDirection direction);
// Read capabilities for the exact selected native object on the control thread.
// No fallback to default or rebound, no device setting changes and no I/O start.
// Missing, ambiguous or weakened identity returns no endpoint. Concurrent changes
// return no endpoint or propagate an OS read error; callers must refresh/retry.
// A successful probe is a snapshot, not permission to execute; streams still
// require a current fence and verify the actual native configuration at start.
AudioHostCapabilities probe_audio_endpoint(const DeviceSelection& selection, AudioDirection direction);
AudioPreflightDecision evaluate_audio_preflight(const AudioRequest& request, const AudioHostCapabilities& capabilities);
const char* audio_direction_name(AudioDirection value);
const char* audio_sample_format_name(AudioSampleFormat value);
const char* audio_preflight_status_name(AudioPreflightStatus value);

}
