#include "native_capture_service.h"

namespace stagemesh {

NativeCaptureService::NativeCaptureService(CaptureReceive receive, void* context)
    : receive_(receive), context_(context) {
    monitor_.start();
}

NativeCaptureService::~NativeCaptureService() {
    deactivate();
    monitor_.stop();
}

bool NativeCaptureService::activate(const AudioRequest& request, DeviceSelection selection) {
    deactivate();
    if (selection.kind != DeviceKind::Audio || !selection.require_input) return false;

    auto candidate = std::make_unique<DeviceExecutionFence>(std::move(selection));
    const auto snapshot = monitor_.snapshot();
    if (!candidate->arm_initial(snapshot.devices)) return false;

    auto candidate_stream = std::make_unique<NativeCaptureStream>(receive_, context_);
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

bool NativeCaptureService::activate_endpoint(const AudioRequest& request, const std::string& token) {
    deactivate();
    const auto snapshot = monitor_.snapshot();
    DeviceSelection selection;
    unsigned matches = 0;
    for (const auto& record : snapshot.devices) {
        if (record.kind != DeviceKind::Audio || !record.input) continue;
        const auto identity = std::string("native=") + record.native_hash +
            ";persistent=" + record.persistent_hash +
            ";strength=" + identity_strength_name(record.identity_strength) +
            ";auto=" + (record.automatic_reconnect ? "1" : "0");
        if (identity == token) { selection = pin_device(record, true, false); ++matches; }
    }
    return matches == 1 && activate(request, std::move(selection));
}

void NativeCaptureService::service(std::uint32_t wait_ms) {
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

void NativeCaptureService::deactivate() noexcept {
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

FenceObservation NativeCaptureService::fence() const noexcept {
    return fence_ ? fence_->observation() : last_fence_;
}

EndpointStreamStats NativeCaptureService::stats() const {
    return stream_ ? stream_->stats() : last_stats_;
}

} // namespace stagemesh
