#include "audio_stream_lifecycle.h"
#include <iostream>
#include <stdexcept>

using namespace stagemesh;
namespace {
void require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
AudioPreflightDecision plan() {
    AudioPreflightDecision value{};
    value.status = AudioPreflightStatus::Exact;
    value.configured_sample_rate_hz = 48000; value.configured_period_frames = 256;
    value.configured_channels = 2; value.configured_format = AudioSampleFormat::Float32;
    return value;
}
void contract() {
    DeviceRecord device{DeviceKind::Audio, "native-original", "persistent", IdentityStrength::OsStableEndpoint, true, false, true};
    std::vector<DeviceRecord> devices{device};
    DeviceExecutionFence fence(pin_device(device, false, true));
    GuardedAudioStreamLifecycle lifecycle;
    require(!lifecycle.start(fence.observation()), "closed/unarmed start accepted");
    require(!lifecycle.prepare(plan(), fence.observation()), "unarmed prepare accepted");
    require(fence.arm_initial(devices), "initial fence arm failed");
    auto first_arm = fence.observation();
    for (auto status : {AudioPreflightStatus::NoEndpoint, AudioPreflightStatus::Unsupported, AudioPreflightStatus::ExplicitAdaptation}) {
        auto invalid = plan(); invalid.status = status;
        require(!lifecycle.prepare(invalid, first_arm), "non-executable plan accepted");
    }
    auto malformed = plan(); malformed.configured_period_frames = 0;
    require(!lifecycle.prepare(malformed, first_arm), "zero-period plan accepted");
    malformed = plan(); malformed.format_conversion = true;
    require(!lifecycle.prepare(malformed, first_arm), "unimplemented conversion accepted");
    auto inconsistent = first_arm; inconsistent.explicit_rearm_required = true;
    require(!lifecycle.prepare(plan(), inconsistent), "contradictory fence accepted");
    require(lifecycle.prepare(plan(), first_arm), "prepare failed");
    require(!lifecycle.observation().callback_execution_allowed, "prepared callbacks allowed");
    require(lifecycle.start(first_arm), "start failed");
    require(!lifecycle.prepare(plan(), first_arm), "running reconfiguration accepted");
    auto detached = fence.reconcile({});
    auto stopped = lifecycle.reconcile(detached);
    require(stopped.stop_required && !stopped.callback_execution_allowed, "detach did not revoke callbacks and request stop");
    device.native_hash = "native-replacement"; devices = {device};
    auto recovered = fence.reconcile(devices);
    require(!recovered.execution_allowed, "recovery silently armed fence");
    require(lifecycle.reconcile(recovered).stop_required, "recovery lost pending stop");
    require(fence.explicit_rearm(devices), "explicit rearm failed");
    require(!lifecycle.prepare(plan(), fence.observation()), "prepare bypassed pending native stop");
    lifecycle.close();
    require(lifecycle.observation().stop_required, "close discarded pending native stop");
    lifecycle.mark_stopped();
    require(lifecycle.observation().state == AudioStreamState::Closed, "stop acknowledgement did not complete close");
    require(!lifecycle.prepare(plan(), first_arm), "stale authority survived close");
    require(lifecycle.prepare(plan(), fence.observation()) && lifecycle.start(fence.observation()), "fresh explicit recovery did not restart");
    auto active = fence.observation();
    lifecycle.reconcile(first_arm);
    require(lifecycle.observation().stop_required && !lifecycle.observation().callback_execution_allowed, "stale running observation did not fail closed");
    lifecycle.mark_stopped();
    require(!lifecycle.prepare(plan(), active), "revoked generation could reprepare");
    fence.disarm(); require(fence.explicit_rearm(devices), "new rearm failed");
    require(lifecycle.prepare(plan(), fence.observation()), "fresh prepare after revocation failed");
    auto changed = fence.observation(); ++changed.generation;
    require(!lifecycle.start(changed), "prepare/start generation race accepted");
    require(!lifecycle.observation().callback_execution_allowed, "failed start left callbacks enabled");

    // Closing an ordinary active stream also requires a native stop acknowledgement.
    GuardedAudioStreamLifecycle normal;
    require(normal.prepare(plan(), active) && normal.start(active), "normal start failed");
    normal.close(); normal.close();
    require(normal.observation().stop_required && !normal.observation().callback_execution_allowed, "running close was not sticky");
    normal.mark_stopped(); normal.mark_stopped();
    require(normal.observation().state == AudioStreamState::Closed && !normal.observation().stop_required, "idempotent close completion failed");

    // Native invalidation revokes the stream while the control fence may still
    // be Armed. One explicit rearm must recover without a ceremonial disarm.
    DeviceExecutionFence native_fence(pin_device(device, false, true));
    require(native_fence.arm_initial(devices), "native recovery initial arm failed");
    GuardedAudioStreamLifecycle native;
    auto before = native_fence.observation();
    require(native.prepare(plan(), before) && native.start(before), "native recovery start failed");
    auto revoked = before; revoked.execution_allowed = false; revoked.explicit_rearm_required = true;
    native.reconcile(revoked);
    require(!native.prepare(plan(), before), "native pending stop bypassed");
    native.mark_stopped();
    require(!native.prepare(plan(), before), "native revoked authority reused");
    require(native_fence.explicit_rearm(devices), "native recovery explicit rearm failed");
    auto fresh = native_fence.observation();
    require(fresh.generation > before.generation, "native recovery did not advance authority");
    require(native.prepare(plan(), fresh) && native.start(fresh), "single explicit rearm did not recover native revocation");
    // Reauthorizing a shared fence invalidates any still-running old consumer.
    require(native_fence.explicit_rearm(devices), "second explicit rearm failed");
    require(native.reconcile(native_fence.observation()).stop_required, "old consumer survived new authorization");
    native.mark_stopped();
    require(!native.prepare(plan(), fresh), "old authorization replay accepted");
}
}
int main() {
    try {
        contract();
        const auto native = run_software_audio_render(48000, 256, 16);
#ifdef __APPLE__
        require(native.available && native.started && native.stopped && native.samples_verified &&
            native.fenced_render_silent && native.restart_verified && !native.hardware_output_used,
            "Generic Output rendering evidence incomplete");
#else
        require(!native.available && !native.started && !native.callback_count, "non-macOS software renderer unexpectedly available");
#endif
        std::cout << std::boolalpha
            << "{\"lifecycleContractPassed\":true,\"staleGenerationRejected\":true,\"pendingStopPreserved\":true,"
            << "\"implicitRecoveryRejected\":true,\"unimplementedConversionRejected\":true,"
            << "\"singleExplicitRearmRecoversNativeRevocation\":true,\"oldConsumerRevokedOnRearm\":true,"
            << "\"softwareRendererAvailable\":" << native.available
            << ",\"nativeUnitStarted\":" << native.started << ",\"nativeUnitStopped\":" << native.stopped
            << ",\"samplesVerified\":" << native.samples_verified << ",\"fencedRenderSilent\":" << native.fenced_render_silent
            << ",\"restartVerified\":" << native.restart_verified << ",\"manualRender\":" << native.manually_driven
            << ",\"callbackCount\":" << native.callback_count << ",\"renderedFrames\":" << native.rendered_frames
            << ",\"physicalOutputsArmed\":false,\"deviceClockQualified\":false,\"audioStreamingQualified\":false,\"physicalHardwareQualified\":false}\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
