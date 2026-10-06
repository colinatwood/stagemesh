#include "native_playback.h"
#include "native_capture.h"
#include "device_monitor.h"
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <thread>
#ifdef __APPLE__
#include <CoreAudio/CoreAudio.h>
#include <unistd.h>
#endif
using namespace stagemesh;
namespace {
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
#ifdef __APPLE__
template<class T> T property(AudioObjectID object, AudioObjectPropertySelector selector) {
    AudioObjectPropertyAddress address{selector, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    T result{}; UInt32 size = sizeof(result);
    require(AudioObjectGetPropertyData(object, &address, 0, nullptr, &size, &result) == noErr && size == sizeof(result), "fixture property read failed");
    return result;
}
struct Aggregate {
    AudioDeviceID device = kAudioObjectUnknown;
    CFStringRef uid = nullptr, parent_uid = nullptr;
    explicit Aggregate(AudioDirection direction) {
        const auto parent = property<AudioDeviceID>(kAudioObjectSystemObject, direction == AudioDirection::Playback ?
            kAudioHardwarePropertyDefaultOutputDevice : kAudioHardwarePropertyDefaultInputDevice);
        require(parent != kAudioObjectUnknown, "selected-loss fixture needs an endpoint");
        parent_uid = property<CFStringRef>(parent, kAudioDevicePropertyDeviceUID);
        uid = CFStringCreateWithFormat(nullptr, nullptr, CFSTR("org.stagemesh.selected-loss.%d.%d"), getpid(), int(direction));
    }
    void create() {
        auto description = CFDictionaryCreateMutable(nullptr, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
        auto subdevice = CFDictionaryCreateMutable(nullptr, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
        CFDictionarySetValue(subdevice, CFSTR(kAudioSubDeviceUIDKey), parent_uid);
        const void* values[] = {subdevice};
        auto list = CFArrayCreate(nullptr, values, 1, &kCFTypeArrayCallBacks);
        CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceNameKey), CFSTR("StageMesh Selected Loss Fixture"));
        CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceUIDKey), uid);
        CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceSubDeviceListKey), list);
        CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceMainSubDeviceKey), parent_uid);
        auto status = AudioHardwareCreateAggregateDevice(description, &device);
        CFRelease(description); CFRelease(subdevice); CFRelease(list);
        require(status == noErr && device != kAudioObjectUnknown, "create selected endpoint fixture failed");
    }
    void destroy() {
        if (device != kAudioObjectUnknown) {
            require(AudioHardwareDestroyAggregateDevice(device) == noErr, "destroy selected endpoint fixture failed");
            device = kAudioObjectUnknown;
        }
    }
    ~Aggregate() {
        try { destroy(); } catch (...) { std::terminate(); }
        if (uid) CFRelease(uid); if (parent_uid) CFRelease(parent_uid);
    }
};
DeviceRecord await_record(DeviceMonitor& monitor, AudioDeviceID device, AudioDirection direction) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (std::chrono::steady_clock::now() < deadline) {
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.02, true);
        for (const auto& record : monitor.snapshot().devices) {
            if (record.kind == DeviceKind::Audio && record.native_hash == sha256_token("coreaudio-native:" + std::to_string(device)) &&
                (direction == AudioDirection::Playback ? record.output : record.input)) {
                // Allow creation notifications to finish before arming. This is
                // fixture setup, not a latency or callback timing measurement.
                for (int i = 0; i < 10; ++i) CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, false);
                return record;
            }
        }
    }
    throw std::runtime_error("selected fixture never became a directional endpoint");
}
void collect(NativeEndpointStream& stream, const DeviceExecutionFence& fence) {
    const auto before = stream.stats().callbacks;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (stream.stats().callbacks < before + 8 && std::chrono::steady_clock::now() < deadline) {
        stream.service(fence, 10);
        require(stream.stats().native_running, "selected fixture stopped before removal");
    }
    require(stream.stats().callbacks >= before + 8, "selected fixture did not deliver native callbacks");
}
std::uint64_t exercise(AudioDirection direction) {
    std::cerr << "selected-loss " << audio_direction_name(direction) << ": creating endpoint\n";
    DeviceMonitor monitor; monitor.start();
    Aggregate aggregate(direction); aggregate.create();
    auto record = await_record(monitor, aggregate.device, direction);
    auto selection = pin_device(record, direction == AudioDirection::Capture, direction == AudioDirection::Playback);
    const auto capabilities = probe_audio_endpoint(selection, direction);
    require(capabilities.endpoint_present && capabilities.endpoint_identity_hash == selection.persistent_hash,
            "selected aggregate capability probe did not return pinned identity");
    require(probe_default_audio_endpoint(direction).endpoint_identity_hash != capabilities.endpoint_identity_hash,
            "selected aggregate fixture unexpectedly became default");
    DeviceExecutionFence fence(selection);
    require(fence.arm_initial(monitor.snapshot().devices), "selected fixture initial arm failed");
    AudioRequest request;
    request.direction = direction;
    request.sample_rate_hz = capabilities.native_sample_rate_hz;
    request.period_frames = capabilities.default_period_frames;
    request.channels = direction == AudioDirection::Playback ? capabilities.output_channels : capabilities.input_channels;
    std::unique_ptr<NativeEndpointStream> stream;
    // Null playback writes silence; null capture discards every input buffer.
    if (direction == AudioDirection::Playback) stream = std::make_unique<NativePlaybackStream>();
    else stream = std::make_unique<NativeCaptureStream>();
    require(stream->prepare(request, fence) && stream->start(fence), "selected fixture stream start failed");
    collect(*stream, fence);
    // Inject downgraded metadata into a copy of real inventory. This is not an
    // OS/physical identity downgrade; native I/O and its stop/restart are real.
    auto weak_inventory = monitor.snapshot().devices;
    bool injected = false;
    for (auto& candidate : weak_inventory) if (candidate.native_hash == record.native_hash) {
        candidate.identity_strength = IdentityStrength::InstallationSnapshot;
        candidate.automatic_reconnect = false; injected = true;
    }
    require(injected, "assurance fixture record not found");
    require(!fence.reconcile(weak_inventory).execution_allowed, "injected downgrade did not fence authority");
    stream->service(fence);
    require(!stream->stats().native_running && !stream->stats().lifecycle.callback_execution_allowed,
            "identity downgrade did not stop native I/O");
    const auto downgrade_count = stream->stats().callbacks;
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    require(stream->stats().callbacks == downgrade_count, "callbacks continued after downgrade stop");
    require(!fence.explicit_rearm(weak_inventory), "weak metadata explicitly rearmed");
    auto strong_inventory = monitor.snapshot().devices;
    require(!fence.reconcile(strong_inventory).execution_allowed, "restored assurance silently rearmed");
    require(!stream->prepare(request, fence), "restored assurance bypassed explicit rearm");
    require(fence.explicit_rearm(strong_inventory), "restored assurance could not rearm");
    require(stream->prepare(request, fence) && stream->start(fence), "assurance recovery did not restart native I/O");
    collect(*stream, fence);
    std::cerr << "selected-loss " << audio_direction_name(direction) << ": removing active endpoint\n";
    aggregate.destroy();
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (fence.observation().resolution != ResolutionStatus::Detached && std::chrono::steady_clock::now() < deadline) {
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, true);
        fence.reconcile(monitor.snapshot().devices);
    }
    require(fence.observation().resolution == ResolutionStatus::Detached, "removed selected device still resolved");
    require(!probe_audio_endpoint(fence.selection(), direction).endpoint_present,
            "removed selected endpoint probe fell back to another device");
    require(probe_default_audio_endpoint(direction).endpoint_present, "default fixture disappeared with selected aggregate");
    stream->service(fence);
    require(!stream->stats().native_running && !stream->stats().lifecycle.callback_execution_allowed, "selected loss did not stop native stream");
    auto stopped_count = stream->stats().callbacks;
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    require(stream->stats().callbacks == stopped_count, "callbacks continued after selected device loss");
    require(!fence.explicit_rearm(monitor.snapshot().devices), "absent selected device rearmed");
    std::cerr << "selected-loss " << audio_direction_name(direction) << ": recreating endpoint\n";
    aggregate.create();
    await_record(monitor, aggregate.device, direction);
    auto restored = monitor.snapshot();
    auto recovered = fence.reconcile(restored.devices);
    require(!recovered.execution_allowed && recovered.explicit_rearm_required, "recreated endpoint silently rearmed");
    require(!stream->prepare(request, fence), "disarmed recovered endpoint prepared");
    require(fence.explicit_rearm(restored.devices), "recreated strong identity could not explicitly rearm");
    const auto restored_capabilities = probe_audio_endpoint(fence.selection(), direction);
    require(restored_capabilities.endpoint_present && restored_capabilities.endpoint_identity_hash == selection.persistent_hash,
            "explicitly rebound selection could not probe recreated endpoint");
    require(stream->prepare(request, fence) && stream->start(fence), "recreated selected endpoint restart failed");
    collect(*stream, fence); stream->close();
    return stream->stats().callbacks;
}
#endif
}
int main() {
    try {
        bool available = false; std::uint64_t playback = 0, capture = 0;
#ifdef __APPLE__
        for (const auto* key : {"STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST", "STAGEMESH_ALLOW_ENDPOINT_CAPTURE_TEST", "STAGEMESH_HOSTED_CAPTURE_AUTHORIZED"}) {
            auto value = std::getenv(key);
            require(value && std::string(value) == "1", "selected loss fixture requires authorized endpoint test environment");
        }
        // Recreate the monitor wrapper between phases, after HAL I/O teardown.
        // The underlying CoreMIDI service connection stays process-owned.
        playback = exercise(AudioDirection::Playback);
        capture = exercise(AudioDirection::Capture);
        available = true;
#endif
        std::cout << std::boolalpha << "{\"softwareFixtureAvailable\":" << available
            << ",\"selectedRemovalStopsNativeIo\":" << available << ",\"recreationRequiresExplicitRearm\":" << available
            << ",\"injectedIdentityDowngradeStopsNativeIo\":" << available
            << ",\"restoredAssuranceRequiresExplicitRearm\":" << available
            << ",\"physicalIdentityDowngradeQualified\":false"
            << ",\"pinnedNonDefaultPreflight\":" << available << ",\"removedPinNeverFallsBack\":" << available
            << ",\"playbackCallbacks\":" << playback << ",\"captureCallbacks\":" << capture
            << ",\"audioSamplesStored\":false,\"physicalHotplugQualified\":false,\"physicalHardwareQualified\":false}\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
