#include "native_playback_service.h"

#include <stdexcept>
#include <thread>

namespace stageforge {

NativePlaybackService::NativePlaybackService(PlaybackRender render, void* context)
    : render_(render), context_(context), owner_thread_(std::this_thread::get_id()) {
    monitor_.start();
}

NativePlaybackService::~NativePlaybackService() {
    deactivate();
    monitor_.stop();
}

bool NativePlaybackService::activate(const AudioRequest& request, DeviceSelection selection) {
    require_owner();
    deactivate();
    if (selection.kind != DeviceKind::Audio || !selection.require_output) return false;

    auto candidate = std::make_unique<DeviceExecutionFence>(std::move(selection));
    const auto snapshot = monitor_.snapshot();
    if (!candidate->arm_initial(snapshot.devices)) return false;

    auto candidate_stream = std::make_unique<NativePlaybackStream>(render_, context_);
    try {
        if (!candidate_stream->prepare(request, *candidate) ||
            !candidate_stream->start(*candidate)) {
            candidate_stream->close();
            return false;
        }
    } catch (...) {
        try { candidate_stream->close(); } catch (...) {}
        return false;
    }

    last_stats_ = {};
    last_fence_ = {};
    fence_ = std::move(candidate);
    stream_ = std::move(candidate_stream);
    active_ = true;
    return true;
}

bool NativePlaybackService::activate_endpoint(const AudioRequest& request, const std::string& token) {
    require_owner();
    deactivate();
    const auto snapshot = monitor_.snapshot();
    DeviceSelection selection;
    unsigned matches = 0;
    for (const auto& record : snapshot.devices) {
        if (record.kind != DeviceKind::Audio || !record.output) continue;
        const auto identity = std::string("native=") + record.native_hash +
            ";persistent=" + record.persistent_hash +
            ";strength=" + identity_strength_name(record.identity_strength) +
            ";auto=" + (record.automatic_reconnect ? "1" : "0");
        if (identity == token) { selection = pin_device(record, false, true); ++matches; }
    }
    return matches == 1 && activate(request, std::move(selection));
}

void NativePlaybackService::service(std::uint32_t wait_ms) {
    require_owner();
    if (!active_) return;
    try {
        const auto observation = fence_->reconcile(monitor_.snapshot().devices);
        last_fence_ = observation;
        if (!observation.execution_allowed) {
            deactivate();
            return;
        }
        stream_->service(*fence_, wait_ms);
        if (!stream_->stats().native_running) deactivate();
    } catch (...) {
        deactivate();
    }
}

void NativePlaybackService::deactivate() noexcept {
    if (stream_) {
        try {
            stream_->close();
            last_stats_ = stream_->stats();
        } catch (...) {}
    }
    last_stats_.native_running = false;
    last_stats_.lifecycle.callback_execution_allowed = false;
    last_stats_.lifecycle.explicit_rearm_required = true;
    last_fence_.execution_allowed = false;
    last_fence_.explicit_rearm_required = true;
    stream_.reset();
    fence_.reset();
    active_ = false;
}

FenceObservation NativePlaybackService::fence() const noexcept {
    if (std::this_thread::get_id() != owner_thread_) return last_fence_;
    return fence_ ? fence_->observation() : last_fence_;
}

EndpointStreamStats NativePlaybackService::stats() const {
    require_owner();
    return stream_ ? stream_->stats() : last_stats_;
}

void NativePlaybackService::require_owner() const {
    if (std::this_thread::get_id() != owner_thread_) {
        throw std::logic_error("NativePlaybackService control thread changed");
    }
}

} // namespace stageforge
