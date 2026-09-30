#pragma once

#include "device_execution_fence.h"
#include "device_monitor.h"
#include "native_capture.h"

#include <memory>

namespace stageforge {

// Owner-thread controller for one target-OS capture stream. All methods must
// be called from the thread that constructs this object. It owns the monitor,
// selection fence and stream together so callback context remains alive until
// close() has drained native I/O.
class NativeCaptureService final {
public:
    NativeCaptureService(CaptureReceive receive = nullptr, void* context = nullptr);
    ~NativeCaptureService();

    NativeCaptureService(const NativeCaptureService&) = delete;
    NativeCaptureService& operator=(const NativeCaptureService&) = delete;

    [[nodiscard]] bool activate(const AudioRequest& request, DeviceSelection selection);
    bool activate_endpoint(const AudioRequest&, const std::string& identity_token);
    void service(std::uint32_t wait_ms = 0);
    void deactivate() noexcept;

    [[nodiscard]] bool active() const noexcept { return active_; }
    [[nodiscard]] FenceObservation fence() const noexcept;
    [[nodiscard]] EndpointStreamStats stats() const;

private:
    DeviceMonitor monitor_;
    std::unique_ptr<DeviceExecutionFence> fence_;
    std::unique_ptr<NativeCaptureStream> stream_;
    CaptureReceive receive_;
    void* context_;
    bool active_{false};
    EndpointStreamStats last_stats_{};
    FenceObservation last_fence_{};
};

} // namespace stageforge
