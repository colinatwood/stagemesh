#include "device_execution_fence.h"
#include "device_monitor.h"
#include <chrono>
#include <iostream>
#include <set>
#include <stdexcept>
#include <thread>
#include <type_traits>
#ifdef __APPLE__
#include <CoreAudio/CoreAudio.h>
#include <CoreMIDI/CoreMIDI.h>
#include <CoreFoundation/CoreFoundation.h>
#include <unistd.h>
#endif

namespace {
using namespace stagemesh;

void require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}

bool synthetic_fence_contract() {
    static_assert(!std::is_copy_constructible_v<DeviceExecutionFence>);
    static_assert(!std::is_copy_assignable_v<DeviceExecutionFence>);
    static_assert(!std::is_move_constructible_v<DeviceExecutionFence>);
    static_assert(!std::is_move_assignable_v<DeviceExecutionFence>);
    DeviceRecord original{DeviceKind::Audio,"sha256:native-a","sha256:persistent-a",IdentityStrength::OsStableEndpoint,true,false,true};
    auto selection = pin_device(original, false, true);
    DeviceExecutionFence fence(selection);
    require(fence.arm_initial({original}), "initial exact device did not arm");
    require(fence.observation().execution_allowed, "armed fence did not allow execution");
    const auto initial_generation = fence.observation().generation;
    require(!fence.arm_initial({original}), "initial arm was reusable");
    require(fence.observation().generation == initial_generation, "rejected initial arm changed authority");
    require(fence.explicit_rearm({original}) && fence.observation().generation > initial_generation,
            "explicit rearm of armed fence did not issue fresh authority");

    auto removed = fence.reconcile({});
    require(removed.state == ExecutionFenceState::FencedDetached && !removed.execution_allowed,
            "detach did not fence execution");

    auto replacement = original;
    replacement.native_hash = "sha256:native-b";
    auto recovered = fence.reconcile({replacement});
    require(recovered.state == ExecutionFenceState::RecoveredDisarmed && !recovered.execution_allowed,
            "strong recovery silently rearmed execution");
    require(recovered.explicit_rearm_required, "recovered device did not require explicit rearm");
    require(!fence.arm_initial({replacement}) && !fence.observation().execution_allowed,
            "initial arm bypassed recovery gate");
    require(fence.explicit_rearm({replacement}), "explicit rearm failed for exact-unique strong recovery");
    require(fence.observation().state == ExecutionFenceState::Armed, "explicit rearm did not arm");

    auto duplicate = replacement;
    duplicate.native_hash = "sha256:native-c";
    auto ambiguous = fence.reconcile({replacement, duplicate});
    require(ambiguous.state == ExecutionFenceState::FencedAmbiguous && !ambiguous.execution_allowed,
            "ambiguous identity did not fence execution");
    require(!fence.explicit_rearm({replacement, duplicate}), "ambiguous identity explicitly rearmed");

    DeviceRecord weak{DeviceKind::Audio,"sha256:weak-native","sha256:weak-install",IdentityStrength::InstallationSnapshot,false,false,true};
    DeviceExecutionFence weak_fence(pin_device(weak,false,true));
    require(weak_fence.arm_initial({weak}), "weak exact device did not initially arm");
    auto weak_changed = weak;
    weak_changed.native_hash = "sha256:weak-other";
    auto weak_result = weak_fence.reconcile({weak_changed});
    require(weak_result.state == ExecutionFenceState::FencedDetached && !weak_result.execution_allowed,
            "weak identity rebound automatically");
    require(!weak_fence.explicit_rearm({weak_changed}), "weak changed identity explicitly rearmed");
    DeviceExecutionFence failed_initial(selection);
    require(!failed_initial.arm_initial({}), "absent initial device armed");
    require(!failed_initial.arm_initial({original}), "failed initial attempt was reusable");
    require(failed_initial.explicit_rearm({original}), "explicit recovery after failed initial arm rejected");
    failed_initial.disarm();
    require(!failed_initial.arm_initial({original}) && !failed_initial.observation().execution_allowed,
            "initial arm bypassed explicit disarm");
    DeviceExecutionFence assurance(selection);
    require(assurance.arm_initial({original}), "assurance fixture did not arm");
    auto downgraded = original;
    downgraded.identity_strength = IdentityStrength::InstallationSnapshot;
    downgraded.automatic_reconnect = false;
    require(!assurance.reconcile({downgraded}).execution_allowed, "weakened identity retained execution");
    require(!assurance.explicit_rearm({downgraded}), "explicit rearm bypassed weak identity");
    require(!assurance.reconcile({original}).execution_allowed, "restored assurance silently rearmed");
    require(assurance.explicit_rearm({original}), "restored strong identity could not explicitly recover");
    return true;
}

#ifdef __APPLE__
bool wait_revision(DeviceMonitor& monitor, std::uint64_t before,
                   std::chrono::milliseconds timeout = std::chrono::milliseconds(2000)) {
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    while (std::chrono::steady_clock::now() < deadline) {
        if (monitor.revision() > before) return true;
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, true);
    }
    return monitor.revision() > before;
}

std::set<std::string> persistent_set(const DeviceSnapshot& snapshot, DeviceKind kind) {
    std::set<std::string> result;
    for (const auto& record : snapshot.devices)
        if (record.kind == kind) result.insert(record.persistent_hash);
    return result;
}

DeviceRecord new_strong_record(const DeviceSnapshot& snapshot, DeviceKind kind,
                               const std::set<std::string>& before) {
    for (const auto& record : snapshot.devices) {
        if (record.kind == kind && record.automatic_reconnect && !before.count(record.persistent_hash))
            return record;
    }
    throw std::runtime_error("new strong fixture identity not found");
}

bool exercise_midi_fence(DeviceMonitor& monitor) {
    const auto baseline = monitor.snapshot();
    const auto before = persistent_set(baseline, DeviceKind::Midi);
    MIDIClientRef client = 0;
    MIDIEndpointRef source = 0;
    require(MIDIClientCreate(CFSTR("StageMesh Fence CI"), nullptr, nullptr, &client) == noErr,
            "MIDIClientCreate fence fixture failed");
    const MIDIUniqueID uid = static_cast<MIDIUniqueID>(-1100000000 + (getpid() % 1000000));
    auto revision = monitor.revision();
    require(MIDISourceCreate(client, CFSTR("StageMesh Fence Source"), &source) == noErr,
            "MIDISourceCreate fence fixture failed");
    require(MIDIObjectSetIntegerProperty(source, kMIDIPropertyUniqueID, uid) == noErr,
            "CoreMIDI fence UID set failed");
    require(wait_revision(monitor, revision), "CoreMIDI fence add notification not observed");
    auto present = monitor.snapshot();
    auto record = new_strong_record(present, DeviceKind::Midi, before);
    DeviceExecutionFence fence(pin_device(record, true, false));
    require(fence.arm_initial(present.devices), "CoreMIDI fence initial arm failed");

    revision = monitor.revision();
    MIDIEndpointDispose(source); source = 0;
    require(wait_revision(monitor, revision), "CoreMIDI fence removal notification not observed");
    auto removed = fence.reconcile(monitor.snapshot().devices);
    require(removed.state == ExecutionFenceState::FencedDetached && !removed.execution_allowed,
            "CoreMIDI removal did not fence execution");

    revision = monitor.revision();
    require(MIDISourceCreate(client, CFSTR("StageMesh Fence Source 2"), &source) == noErr,
            "CoreMIDI fence recreate failed");
    require(MIDIObjectSetIntegerProperty(source, kMIDIPropertyUniqueID, uid) == noErr,
            "CoreMIDI fence UID restore failed");
    require(wait_revision(monitor, revision), "CoreMIDI fence recreate notification not observed");
    auto restored_snapshot = monitor.snapshot();
    auto restored = fence.reconcile(restored_snapshot.devices);
    require(restored.state == ExecutionFenceState::RecoveredDisarmed && !restored.execution_allowed,
            "CoreMIDI identity recovery silently rearmed execution");
    require(fence.explicit_rearm(restored_snapshot.devices), "CoreMIDI explicit rearm failed");
    require(fence.observation().execution_allowed, "CoreMIDI explicit rearm did not allow execution");

    MIDIEndpointDispose(source);
    MIDIClientDispose(client);
    return true;
}

bool exercise_audio_fence(DeviceMonitor& monitor) {
    const auto baseline = monitor.snapshot();
    const auto before = persistent_set(baseline, DeviceKind::Audio);
    CFStringRef uid = CFStringCreateWithFormat(kCFAllocatorDefault, nullptr,
                                               CFSTR("org.stagemesh.fence.aggregate.%d"), getpid());
    auto make_description = [&](CFStringRef name) {
        auto dictionary = CFDictionaryCreateMutable(kCFAllocatorDefault, 0,
            &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
        CFDictionarySetValue(dictionary, CFSTR(kAudioAggregateDeviceNameKey), name);
        CFDictionarySetValue(dictionary, CFSTR(kAudioAggregateDeviceUIDKey), uid);
        return dictionary;
    };

    AudioDeviceID aggregate = kAudioObjectUnknown;
    auto description = make_description(CFSTR("StageMesh Fence Aggregate"));
    auto revision = monitor.revision();
    auto status = AudioHardwareCreateAggregateDevice(description, &aggregate);
    CFRelease(description);
    require(status == noErr && aggregate != kAudioObjectUnknown, "CoreAudio fence aggregate create failed");
    require(wait_revision(monitor, revision), "CoreAudio fence add notification not observed");
    auto present = monitor.snapshot();
    auto record = new_strong_record(present, DeviceKind::Audio, before);
    DeviceExecutionFence fence(pin_device(record));
    require(fence.arm_initial(present.devices), "CoreAudio fence initial arm failed");

    revision = monitor.revision();
    require(AudioHardwareDestroyAggregateDevice(aggregate) == noErr, "CoreAudio fence aggregate destroy failed");
    aggregate = kAudioObjectUnknown;
    require(wait_revision(monitor, revision), "CoreAudio fence removal notification not observed");
    auto removed = fence.reconcile(monitor.snapshot().devices);
    require(removed.state == ExecutionFenceState::FencedDetached && !removed.execution_allowed,
            "CoreAudio removal did not fence execution");

    description = make_description(CFSTR("StageMesh Fence Aggregate 2"));
    revision = monitor.revision();
    status = AudioHardwareCreateAggregateDevice(description, &aggregate);
    CFRelease(description);
    require(status == noErr && aggregate != kAudioObjectUnknown, "CoreAudio fence aggregate recreate failed");
    require(wait_revision(monitor, revision), "CoreAudio fence recreate notification not observed");
    auto restored_snapshot = monitor.snapshot();
    auto restored = fence.reconcile(restored_snapshot.devices);
    require(restored.state == ExecutionFenceState::RecoveredDisarmed && !restored.execution_allowed,
            "CoreAudio identity recovery silently rearmed execution");
    require(fence.explicit_rearm(restored_snapshot.devices), "CoreAudio explicit rearm failed");
    require(fence.observation().execution_allowed, "CoreAudio explicit rearm did not allow execution");

    AudioHardwareDestroyAggregateDevice(aggregate);
    CFRelease(uid);
    return true;
}
#endif
}

int main() {
    try {
        const bool synthetic = synthetic_fence_contract();
        bool midi = false;
        bool audio = false;
        stagemesh::DeviceMonitor monitor;
        monitor.start();
#ifdef __APPLE__
        midi = exercise_midi_fence(monitor);
        audio = exercise_audio_fence(monitor);
#endif
        monitor.stop();
        std::cout << std::boolalpha
                  << "{\"syntheticFenceQualified\":" << synthetic
                  << ",\"coreMidiFenceQualified\":" << midi
                  << ",\"coreAudioFenceQualified\":" << audio
                  << ",\"silentRearmPrevented\":true"
                  << ",\"freshExplicitGeneration\":true,\"initialArmSingleUse\":true,\"authorityNoncopyable\":true"
                  << ",\"identityDowngradeFenced\":true,\"assuranceRecoveryRequiresRearm\":true"
                  << ",\"physicalOutputsArmed\":false"
                  << ",\"audioStreamingQualified\":false"
                  << ",\"physicalHotplugQualified\":false}"
                  << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
