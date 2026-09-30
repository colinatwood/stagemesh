#include "native_playback.h"
#include "device_monitor.h"
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <thread>
#ifdef __APPLE__
#include <CoreAudio/CoreAudio.h>
#include <unistd.h>
#endif

using namespace stageforge;
namespace {
void require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
struct Context { std::atomic<std::uint64_t> calls{0}; };
void silence(float*, std::uint32_t, std::uint32_t, void* raw) noexcept {
    // The adapter zeroed this entire buffer. Never write a nonzero test signal.
    static_cast<Context*>(raw)->calls.fetch_add(1);
}
void collect(NativePlaybackStream& stream, const DeviceExecutionFence& fence) {
    const auto begin = stream.stats().callbacks;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (stream.stats().callbacks < begin + 8 && std::chrono::steady_clock::now() < deadline) {
        stream.service(fence, 10);
        require(stream.stats().native_running, "endpoint stream stopped unexpectedly");
    }
    require(stream.stats().callbacks >= begin + 8, "native endpoint did not deliver callbacks");
}
#ifdef __APPLE__
struct TopologyFixture {
    AudioDeviceID device = kAudioObjectUnknown;
    TopologyFixture() {
        auto uid = CFStringCreateWithFormat(nullptr, nullptr, CFSTR("org.stageforge.playback-event.%d"), getpid());
        auto description = CFDictionaryCreateMutable(nullptr, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
        CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceNameKey), CFSTR("StageForge Playback Event"));
        CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceUIDKey), uid);
        auto status = AudioHardwareCreateAggregateDevice(description, &device);
        CFRelease(description); CFRelease(uid);
        require(status == noErr && device != kAudioObjectUnknown, "native topology fixture failed");
    }
    ~TopologyFixture() { if (device != kAudioObjectUnknown && AudioHardwareDestroyAggregateDevice(device) != noErr) std::terminate(); }
};
#endif
}
int main() {
    try {
        Context context;
        NativePlaybackStream stream(silence, &context);
        DeviceRecord fake{DeviceKind::Audio, "absent-native", "absent-persistent", IdentityStrength::InstallationSnapshot, false, false, true};
        DeviceExecutionFence missing(pin_device(fake, false, true));
        AudioRequest request;
        require(!stream.prepare(request, missing), "unarmed preparation accepted");
        require(missing.arm_initial({fake}), "synthetic pin could not arm");
        auto invalid = request; invalid.direction = AudioDirection::Capture;
        require(!stream.prepare(invalid, missing), "capture silently accepted by playback adapter");
        invalid = request; invalid.allow_rate_conversion = true;
#ifdef _WIN32
        require(!stream.prepare(invalid, missing), "unimplemented conversion accepted");
#else
        bool adaptation_absent = false;
        try { stream.prepare(invalid, missing); }
        catch (const std::runtime_error&) { adaptation_absent = true; }
        require(adaptation_absent && !stream.stats().native_running,
                "adaptation bypassed missing pinned endpoint");
        stream.close();
#endif
        for (int i = 0; i < 3; ++i) {
            bool absent = false;
            try { stream.prepare(request, missing); } catch (const std::runtime_error&) { absent = true; }
            require(absent && !stream.stats().native_running, "absent pinned endpoint not rejected");
            stream.close();
        }
        bool wrong_thread = false;
        std::thread other([&] { try { stream.stats(); } catch (const std::logic_error&) { wrong_thread = true; } });
        other.join(); require(wrong_thread, "owner-thread contract not enforced");

        const auto capabilities = probe_default_audio_endpoint(AudioDirection::Playback);
        bool live = false, stopped = false, restarted = false, config_rejected = false, native_event_stopped = false;
        bool native_event_restarted = false;
        std::uint64_t callbacks = 0, frames = 0;
        AudioPreflightDecision verified;
        if (capabilities.endpoint_present) {
            const char* allowed = std::getenv("STAGEFORGE_ALLOW_SILENT_ENDPOINT_TEST");
            if (!allowed || std::string(allowed) != "1") throw std::runtime_error("silent endpoint test requires explicit environment opt-in");
            DeviceMonitor monitor; monitor.start(); auto snapshot = monitor.snapshot();
            DeviceRecord selected; unsigned matches = 0;
            for (const auto& record : snapshot.devices) {
#ifdef _WIN32
                const bool identity = record.native_hash == capabilities.endpoint_identity_hash;
#else
                const bool identity = record.persistent_hash == capabilities.endpoint_identity_hash;
#endif
                if (record.kind == DeviceKind::Audio && record.output && identity) { selected = record; ++matches; }
            }
            require(matches == 1, "default output does not resolve to a unique monitored identity");
            DeviceExecutionFence fence(pin_device(selected, false, true));
            require(fence.arm_initial(snapshot.devices), "live endpoint cannot arm");
            request.sample_rate_hz = capabilities.native_sample_rate_hz;
            request.period_frames = capabilities.default_period_frames;
            request.channels = capabilities.output_channels;
            request.format = AudioSampleFormat::Float32;
            NativePlaybackStream endpoint(silence, &context);
            auto wrong_rate = request; wrong_rate.sample_rate_hz += 1;
            try { endpoint.prepare(wrong_rate, fence); } catch (const std::runtime_error&) { config_rejected = true; }
            require(config_rejected && !endpoint.stats().native_running, "nonexact rate was accepted");
            require(endpoint.prepare(request, fence), "exact endpoint preparation rejected");
            require(endpoint.start(fence), "exact endpoint start rejected");
            collect(endpoint, fence); live = true;
            fence.disarm(); endpoint.service(fence);
            require(!endpoint.stats().native_running && !endpoint.stats().lifecycle.callback_execution_allowed,
                    "explicit disarm did not stop native stream");
            auto count = context.calls.load();
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            require(context.calls.load() == count, "callback accessed context after native stop");
            stopped = true;
            require(!endpoint.start(fence) && !endpoint.prepare(request, fence), "implicit recovery accepted");
            require(fence.explicit_rearm(monitor.snapshot().devices), "explicit rearm failed");
            require(endpoint.prepare(request, fence) && endpoint.start(fence), "native rearm/start failed");
            collect(endpoint, fence); restarted = true;
#ifdef __APPLE__
            {
                // Real software topology notification while the pinned output is
                // active. This tests conservative invalidation, not physical loss.
                TopologyFixture topology;
                auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
                while (endpoint.stats().native_running && std::chrono::steady_clock::now() < deadline) {
                    CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, true);
                    endpoint.service(fence);
                }
                require(!endpoint.stats().native_running && !endpoint.stats().lifecycle.callback_execution_allowed,
                        "native topology notification did not stop playback");
                require(!endpoint.prepare(request, fence), "native invalidation accepted stale armed fence");
                native_event_stopped = true;
                // Settle fixture creation notifications while it remains alive.
                // The selected endpoint never disappeared and the fence is Armed.
                for (int i = 0; i < 20; ++i) CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, false);
                const auto revoked_generation = fence.observation().generation;
                require(fence.observation().execution_allowed, "topology test unexpectedly disarmed control fence");
                require(!fence.arm_initial(monitor.snapshot().devices), "initial arm reused after native invalidation");
                require(fence.explicit_rearm(monitor.snapshot().devices), "explicit native-event recovery rejected");
                require(fence.observation().generation > revoked_generation, "native recovery reused revoked generation");
                require(endpoint.prepare(request, fence) && endpoint.start(fence), "single explicit rearm did not restart native endpoint");
                collect(endpoint, fence);
                native_event_restarted = true;
                endpoint.close();
            }
#endif
            endpoint.close(); endpoint.close();
            callbacks = endpoint.stats().callbacks; frames = endpoint.stats().frames;
            verified = endpoint.stats().last_verified_configuration;
            require(verified.status == AudioPreflightStatus::Exact && verified.configured_sample_rate_hz == request.sample_rate_hz &&
                    verified.configured_period_frames == request.period_frames && verified.configured_channels == request.channels &&
                    verified.configured_format == request.format, "OS readback does not match request");
            count = context.calls.load();
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            require(context.calls.load() == count && !endpoint.stats().native_running && !endpoint.stats().callback_fault,
                    "callback lifetime/close failed");
        }
        std::cout << std::boolalpha << "{\"contractPassed\":true,\"missingPinnedEndpointRejected\":true,"
            "\"ownerThreadEnforced\":true,\"endpointPresent\":" << capabilities.endpoint_present
            << ",\"nativeCallbacksObserved\":" << live << ",\"nativeStopDrained\":" << stopped
            << ",\"explicitRestartObserved\":" << restarted << ",\"nonExactConfigurationRejected\":" << config_rejected
            << ",\"nativeTopologyStoppedStream\":" << native_event_stopped
            << ",\"singleExplicitRearmAfterNativeEvent\":" << native_event_restarted
            << ",\"callbacks\":" << callbacks << ",\"frames\":" << frames
            << ",\"configuredRateHz\":" << verified.configured_sample_rate_hz
            << ",\"configuredPeriodFrames\":" << verified.configured_period_frames
            << ",\"configuredChannels\":" << verified.configured_channels
            << ",\"configuredFormat\":\"" << audio_sample_format_name(verified.configured_format) << "\""
            << ",\"manuallyDrivenAudioUnitRender\":false,\"silentTestOnly\":true,\"physicalHardwareQualified\":false}\n";
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}

