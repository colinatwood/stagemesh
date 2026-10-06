#include "audio_stream_lifecycle.h"
#include <algorithm>

namespace stagemesh {
namespace {
bool armed(const FenceObservation& fence) {
    return fence.state == ExecutionFenceState::Armed && fence.execution_allowed &&
        !fence.explicit_rearm_required && fence.resolution == ResolutionStatus::Attached;
}
bool executable(const AudioPreflightDecision& plan) {
    // Conversion execution does not exist in this module. A proposed explicit
    // adaptation is not permission to silently render the unconverted input.
    return plan.status == AudioPreflightStatus::Exact && plan.configured_sample_rate_hz &&
        plan.configured_period_frames && plan.configured_channels &&
        (plan.configured_format == AudioSampleFormat::Float32 ||
         plan.configured_format == AudioSampleFormat::Int16 ||
         plan.configured_format == AudioSampleFormat::Int24Packed ||
         plan.configured_format == AudioSampleFormat::Int32) &&
        !plan.rate_conversion && !plan.period_adaptation &&
        !plan.channel_conversion && !plan.format_conversion;
}
}
AudioStreamObservation GuardedAudioStreamLifecycle::observation() const noexcept {
    return {state_, state_ == AudioStreamState::Running && !stop_required_, stop_required_,
        revoked_ || state_ == AudioStreamState::Closed || state_ == AudioStreamState::Fenced, generation_};
}
void GuardedAudioStreamLifecycle::transition(AudioStreamState next) noexcept {
    if (state_ != next) { state_ = next; ++generation_; }
}
void GuardedAudioStreamLifecycle::revoke(const FenceObservation& fence) noexcept {
    stop_required_ = stop_required_ || state_ == AudioStreamState::Running;
    highest_fence_generation_ = std::max(highest_fence_generation_, fence.generation);
    revoked_generation_ = highest_fence_generation_;
    seen_fence_ = revoked_ = true;
    transition(AudioStreamState::Fenced);
}
bool GuardedAudioStreamLifecycle::prepare(const AudioPreflightDecision& plan, const FenceObservation& fence) {
    if (state_ == AudioStreamState::Running || stop_required_ || closing_) return false;
    if (!executable(plan) || !armed(fence)) return false;
    if ((seen_fence_ && fence.generation < highest_fence_generation_) ||
        (revoked_ && fence.generation <= revoked_generation_)) return false;
    seen_fence_ = true;
    highest_fence_generation_ = fence_generation_ = fence.generation;
    revoked_ = false;
    transition(AudioStreamState::Prepared);
    return true;
}
bool GuardedAudioStreamLifecycle::start(const FenceObservation& fence) {
    if (state_ != AudioStreamState::Prepared || stop_required_ || closing_) return false;
    if (!armed(fence) || fence.generation != fence_generation_) { revoke(fence); return false; }
    transition(AudioStreamState::Running);
    return true;
}
AudioStreamObservation GuardedAudioStreamLifecycle::reconcile(const FenceObservation& fence) noexcept {
    if (state_ == AudioStreamState::Running || state_ == AudioStreamState::Prepared) {
        if (!armed(fence) || fence.generation != fence_generation_) revoke(fence);
    } else if (revoked_) {
        // Observations alone never clear a revocation or a pending native stop.
        highest_fence_generation_ = std::max(highest_fence_generation_, fence.generation);
    }
    return observation();
}
void GuardedAudioStreamLifecycle::mark_stopped() noexcept {
    stop_required_ = false;
    if (closing_) { closing_ = false; transition(AudioStreamState::Closed); }
    else if (state_ == AudioStreamState::Running || state_ == AudioStreamState::Prepared)
        transition(AudioStreamState::Stopped);
    // Fenced stays fenced until a newer explicit fence rearm plus prepare.
}
void GuardedAudioStreamLifecycle::close() noexcept {
    if (state_ == AudioStreamState::Running || stop_required_) {
        stop_required_ = closing_ = true;
        transition(AudioStreamState::Fenced);
    } else { closing_ = false; transition(AudioStreamState::Closed); }
}
const char* audio_stream_state_name(AudioStreamState state) {
    switch (state) {
        case AudioStreamState::Closed: return "closed";
        case AudioStreamState::Prepared: return "prepared";
        case AudioStreamState::Running: return "running";
        case AudioStreamState::Stopped: return "stopped";
        case AudioStreamState::Fenced: return "fenced";
    }
    return "unknown";
}
}
