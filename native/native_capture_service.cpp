#include "native_capture_service.h"

namespace stageforge {

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

    fence_ = std::move(candidate);
    stream_ = std::move(candidate_stream);
    active_ = true;
    return true;
}

void NativeCaptureService::service(std::uint32_t wait_ms) {
    if (!active_) return;
    const auto observation = fence_->reconcile(monitor_.snapshot().devices);
    if (!observation.execution_allowed) {
        deactivate();
        return;
    }
    try {
        stream_->service(*fence_, wait_ms);
        if (!stream_->stats().native_running) deactivate();
    } catch (...) {
        deactivate();
    }
}

void NativeCaptureService::deactivate() noexcept {
    if (stream_) {
        try { stream_->close(); } catch (...) {}
    }
    stream_.reset();
    fence_.reset();
    active_ = false;
}

FenceObservation NativeCaptureService::fence() const noexcept {
    return fence_ ? fence_->observation() : FenceObservation{};
}

EndpointStreamStats NativeCaptureService::stats() const {
    return stream_ ? stream_->stats() : EndpointStreamStats{};
}

} // namespace stageforge
