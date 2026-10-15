#include "native_capture_service.h"
#include "native_playback_service.h"
#include <iostream>
#include <stdexcept>

// Link the production service controllers and real identity/fence logic against
// deterministic monitor/stream doubles. No platform device or output is opened.
namespace fixture {
std::vector<stagemesh::DeviceRecord> audio;
bool audio_failed = false;
unsigned combined_reads = 0, audio_reads = 0, services = 0, stops = 0;
void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
}

namespace stagemesh {
struct DeviceMonitor::Impl { bool active = false; };
DeviceMonitor::DeviceMonitor() : impl_(std::make_unique<Impl>()) {}
DeviceMonitor::~DeviceMonitor() = default;
void DeviceMonitor::start() { impl_->active = true; }
void DeviceMonitor::stop() { impl_->active = false; }
std::uint64_t DeviceMonitor::revision() const { return 0; }
DeviceSnapshot DeviceMonitor::snapshot() const {
    ++fixture::combined_reads;
    throw std::runtime_error("MIDI topology changed during snapshot; refresh required");
}
DeviceSnapshot DeviceMonitor::audio_snapshot() const {
    ++fixture::audio_reads;
    fixture::require(impl_->active && !fixture::audio_failed, "audio enumeration failed");
    DeviceSnapshot result;
    result.devices = fixture::audio;
    result.device_count = static_cast<unsigned>(result.devices.size());
    return result;
}

struct NativeEndpointStream::Impl { EndpointStreamStats stats; };
NativeEndpointStream::NativeEndpointStream(AudioDirection, PlaybackRender, CaptureReceive, void*)
    : impl_(std::make_unique<Impl>()) {}
NativeEndpointStream::~NativeEndpointStream() { close(); }
bool NativeEndpointStream::prepare(const AudioRequest&, const DeviceExecutionFence& fence) {
    return fence.observation().execution_allowed;
}
bool NativeEndpointStream::start(const DeviceExecutionFence& fence) {
    impl_->stats.native_running = fence.observation().execution_allowed;
    impl_->stats.lifecycle.callback_execution_allowed = impl_->stats.native_running;
    return impl_->stats.native_running;
}
void NativeEndpointStream::service(const DeviceExecutionFence& fence, std::uint32_t) {
    fixture::require(fence.observation().execution_allowed, "service bypassed disarmed fence");
    ++fixture::services;
}
void NativeEndpointStream::close() {
    if (impl_->stats.native_running) ++fixture::stops;
    impl_->stats.native_running = false;
    impl_->stats.lifecycle.callback_execution_allowed = false;
}
EndpointStreamStats NativeEndpointStream::stats() const { return impl_->stats; }
}

template<class Service>
void exercise(stagemesh::AudioDirection direction) {
    using namespace stagemesh;
    using fixture::require;
    const DeviceRecord selected{DeviceKind::Audio, "sha256:selected", "sha256:stable",
                               IdentityStrength::OsStableEndpoint, true, true, true};
    fixture::audio = {selected};
    fixture::audio_failed = false;
    fixture::combined_reads = fixture::audio_reads = fixture::services = fixture::stops = 0;
    Service service;
    AudioRequest request;
    request.direction = direction;
    const auto selection = pin_device(selected, direction == AudioDirection::Capture,
                                     direction == AudioDirection::Playback);
    const auto token = "native=" + selected.native_hash + ";persistent=" + selected.persistent_hash +
        ";strength=" + identity_strength_name(selected.identity_strength) + ";auto=1";
    require(service.activate_endpoint(request, token), "activation depended on failing MIDI enumeration");
    for (unsigned i = 0; i < 3; ++i) service.service();
    require(service.active() && fixture::services == 3 && fixture::combined_reads == 0,
            "audio servicing depended on combined MIDI snapshot");

    fixture::audio_failed = true;
    service.service();
    require(!service.active() && !service.fence().execution_allowed &&
            !service.stats().native_running && fixture::stops == 1,
            "audio enumeration failure did not stop and disarm");
    fixture::audio_failed = false;
    service.service();
    require(!service.active(), "enumeration recovery automatically restarted stream");
    require(service.activate(request, selection), "explicit activation failed");
    fixture::audio.clear();
    service.service();
    require(!service.active() && !service.stats().native_running && fixture::stops == 2,
            "selected audio loss did not stop stream");
    fixture::audio = {selected};
    service.service();
    require(!service.active(), "selected audio return automatically restarted stream");
    auto duplicate = selected;
    duplicate.native_hash = "sha256:duplicate";
    fixture::audio.push_back(duplicate);
    require(!service.activate(request, selection), "ambiguous audio identity activated");
    require(fixture::combined_reads == 0 && fixture::audio_reads >= 7,
            "expected audio inventory checks missing");
}

int main() {
    try {
        exercise<stagemesh::NativeCaptureService>(stagemesh::AudioDirection::Capture);
        exercise<stagemesh::NativePlaybackService>(stagemesh::AudioDirection::Playback);
        std::cout << "Audio service snapshot isolation passed; no physical endpoints opened\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
