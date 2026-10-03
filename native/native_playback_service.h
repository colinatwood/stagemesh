#pragma once

#include "device_execution_fence.h"
#include "device_monitor.h"
#include "native_playback.h"

#include <cstdint>
#include <memory>
#include <string>
#include <thread>

namespace stageforge {

// Owner-thread controller for one target-OS playback stream. The monitor,
// selection fence and native stream share one owner thread so an endpoint
// notification cannot race stream teardown or the render context.
class NativePlaybackService final {
public:
    NativePlaybackService(PlaybackRender render = nullptr, void* context = nullptr);
    ~NativePlaybackService();

    NativePlaybackService(const NativePlaybackService&) = delete;
    NativePlaybackService& operator=(const NativePlaybackService&) = delete;

    [[nodiscard]] bool activate(const AudioRequest& request, DeviceSelection selection);
    [[nodiscard]] bool activate_endpoint(const AudioRequest& request, const std::string& identity_token);
    void service(std::uint32_t wait_ms = 0);
    void deactivate() noexcept;

    [[nodiscard]] bool active() const noexcept { return active_; }
    [[nodiscard]] FenceObservation fence() const noexcept;
    [[nodiscard]] EndpointStreamStats stats() const;

private:
    void require_owner() const;

    DeviceMonitor monitor_;
    std::unique_ptr<DeviceExecutionFence> fence_;
    std::unique_ptr<NativePlaybackStream> stream_;
    PlaybackRender render_;
    void* context_;
    std::thread::id owner_thread_;
    bool active_{false};
    EndpointStreamStats last_stats_{};
    FenceObservation last_fence_{};
};

} // namespace stageforge
