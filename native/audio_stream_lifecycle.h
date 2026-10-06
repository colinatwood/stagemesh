#pragma once
#include "audio_preflight.h"
#include "device_execution_fence.h"
#include <cstdint>

namespace stagemesh {

enum class AudioStreamState {
    Closed,
    Prepared,
    Running,
    Stopped,
    Fenced,
};

struct AudioStreamObservation {
    AudioStreamState state = AudioStreamState::Closed;
    bool callback_execution_allowed = false;
    bool stop_required = false;
    bool explicit_rearm_required = true;
    std::uint64_t generation = 0;
};

// Single control-thread lifecycle contract between audio preflight and ONE device
// execution fence. This object owns no OS audio resources. A platform adapter
// must synchronously stop its native stream whenever reconcile() reports
// stop_required=true.
// observation() is not an atomic cross-thread callback gate. An asynchronous
// adapter must publish permission safely to its callback and acknowledge a
// completed native stop with mark_stopped(). close() retains a pending stop.
class GuardedAudioStreamLifecycle {
public:
    AudioStreamObservation observation() const noexcept;

    bool prepare(const AudioPreflightDecision& decision, const FenceObservation& fence);
    bool start(const FenceObservation& fence);
    AudioStreamObservation reconcile(const FenceObservation& fence) noexcept;
    void mark_stopped() noexcept;
    void close() noexcept;

private:
    void transition(AudioStreamState next) noexcept;

    AudioStreamState state_ = AudioStreamState::Closed;
    bool stop_required_ = false;
    bool closing_ = false;
    bool revoked_ = false;
    bool seen_fence_ = false;
    std::uint64_t fence_generation_ = 0;
    std::uint64_t highest_fence_generation_ = 0;
    std::uint64_t revoked_generation_ = 0;
    std::uint64_t generation_ = 0;
    void revoke(const FenceObservation& fence) noexcept;
};

struct SoftwareAudioRenderResult {
    bool available = false;
    bool started = false;
    bool stopped = false;
    bool hardware_output_used = false;
    std::uint64_t callback_count = 0;
    std::uint64_t rendered_frames = 0;
    bool samples_verified = false;
    bool fenced_render_silent = false;
    bool restart_verified = false;
    bool manually_driven = true;
};

// macOS-only MANUAL AudioUnitRender test using Generic Output, without an audio
// device or device clock. Never a hardware-stream or real-time timing claim.
// Other platforms return available=false.
SoftwareAudioRenderResult run_software_audio_render(std::uint32_t sample_rate_hz,
                                                    std::uint32_t frames_per_slice,
                                                    std::uint32_t slices);

const char* audio_stream_state_name(AudioStreamState state);

}
