#pragma once
#include "audio_stream_lifecycle.h"
#include "stageforge/capture_packet_info.hpp"
#include <memory>

namespace stageforge {
// Interleaved float32 borrowed for this call only; do not retain this pointer.
// A consumer may copy samples into its own preallocated storage. A null consumer
// discards input. Both callbacks must be bounded, allocation-free and noexcept;
// their context must outlive close(). A null playback callback renders silence.
using CaptureReceive = void (*)(const float*, std::uint32_t, std::uint32_t, const CapturePacketInfo&, void*) noexcept;
using PlaybackRender = void (*)(float*, std::uint32_t, std::uint32_t, void*) noexcept;
struct EndpointStreamStats {
    std::uint64_t callbacks = 0;
    std::uint64_t frames = 0;
    bool native_running = false;
    bool callback_fault = false;
    AudioStreamObservation lifecycle;
    // Last successful OS readback, retained for evidence after close().
    // native_running/lifecycle describe whether it is currently executing.
    AudioPreflightDecision last_verified_configuration;
    std::uint64_t discontinuities = 0;
};

// Owner-thread API, tied to one DeviceExecutionFence lifetime. Owns an exact,
// pinned float32 input or output stream. No automatic endpoint substitution, rate or
// channel conversion. Existing device rate/period must match the request; this
// adapter does not change global device settings. Windows uses an owner-thread
// event pump; macOS uses an asynchronous HAL callback with atomic permission.
// Call service() regularly for native stopping after notification revocation.
// In-flight rendering may finish during revocation; stop/close drains native I/O
// before returning. No callback can access the user context after close().
class NativeEndpointStream {
public:
    virtual ~NativeEndpointStream();
    NativeEndpointStream(const NativeEndpointStream&) = delete;
    NativeEndpointStream& operator=(const NativeEndpointStream&) = delete;
    bool prepare(const AudioRequest&, const DeviceExecutionFence&);
    bool start(const DeviceExecutionFence&);
    void service(const DeviceExecutionFence&, std::uint32_t wait_ms = 0);
    void close();
    EndpointStreamStats stats() const;
protected:
    NativeEndpointStream(AudioDirection, PlaybackRender, CaptureReceive, void*);
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
