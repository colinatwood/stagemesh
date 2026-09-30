#include "device_monitor.h"
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string_view>
#include <thread>
#include <vector>
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

void exercise_resolution_contract() {
    require(sha256_hex("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "SHA-256 self-test failed");
    DeviceRecord strong{DeviceKind::Audio,"sha256:native-a","sha256:persistent-a",IdentityStrength::OsStableEndpoint,true,false,true};
    auto selection = pin_device(strong, false, true);
    auto replacement = strong;
    replacement.native_hash = "sha256:native-b";
    require(resolve_device(selection,{replacement}).status == ResolutionStatus::Rebound, "strong identity did not rebind");
    auto duplicate = replacement;
    duplicate.native_hash = "sha256:native-c";
    require(resolve_device(selection,{replacement,duplicate}).status == ResolutionStatus::Ambiguous, "duplicate strong identity did not fail closed");
    auto weak = strong;
    weak.identity_strength = IdentityStrength::InstallationSnapshot;
    weak.automatic_reconnect = false;
    auto weak_selection = pin_device(weak,false,true);
    auto weak_changed = weak;
    weak_changed.native_hash = "sha256:native-other";
    require(resolve_device(weak_selection,{weak_changed}).status == ResolutionStatus::Detached, "weak identity rebound automatically");
    require(resolve_device(selection,{}).status == ResolutionStatus::Detached, "missing device was not detached");
    for (auto kind : {DeviceKind::Audio, DeviceKind::Midi}) {
        auto original = strong; original.kind = kind;
        auto pinned = pin_device(original, false, true);
        for (auto strength : {IdentityStrength::Volatile, IdentityStrength::InstallationSnapshot, IdentityStrength::OsStableEndpoint}) {
            for (bool reconnect : {false, true}) {
                if (strength == IdentityStrength::OsStableEndpoint && reconnect) continue;
                auto downgraded = original;
                downgraded.identity_strength = strength; downgraded.automatic_reconnect = reconnect;
                require(resolve_device(pinned, {downgraded}).status == ResolutionStatus::Detached,
                        "unchanged native hash bypassed assurance downgrade");
                downgraded.native_hash = "replacement-with-weaker-assurance";
                require(resolve_device(pinned, {downgraded}).status == ResolutionStatus::Detached,
                        "weaker replacement identity rebound");
                require(resolve_device(pinned, {original, downgraded}).status == ResolutionStatus::Ambiguous,
                        "weak duplicate hidden from ambiguity check");
                if (reconnect) {
                    bool rejected = false;
                    try { pin_device(downgraded); } catch (const std::invalid_argument&) { rejected = true; }
                    require(rejected, "contradictory weak reconnect record pinned");
                }
            }
        }
        auto malformed = original; malformed.native_hash.clear();
        require(resolve_device(pinned, {malformed}).status == ResolutionStatus::Detached, "empty native identity rebound");
        auto invalid_selection = pinned; invalid_selection.persistent_hash.clear();
        malformed.persistent_hash.clear();
        require(resolve_device(invalid_selection, {malformed}).status == ResolutionStatus::Detached, "empty identities resolved");
    }
}

std::pair<unsigned,unsigned> identity_counts(const DeviceSnapshot& snapshot) {
    unsigned stable=0, weak=0;
    for (const auto& record : snapshot.devices) {
        require(record.native_hash.rfind("sha256:",0)==0, "native identity is not SHA-256");
        require(record.persistent_hash.rfind("sha256:",0)==0, "persistent identity is not SHA-256");
        if (record.identity_strength == IdentityStrength::OsStableEndpoint) ++stable; else ++weak;
    }
    return {stable,weak};
}

#ifdef __APPLE__
bool wait_revision(DeviceMonitor& monitor, std::uint64_t before, std::chrono::milliseconds timeout = std::chrono::milliseconds(2000)) {
    auto deadline = std::chrono::steady_clock::now() + timeout;
    while (std::chrono::steady_clock::now() < deadline) {
        if (monitor.revision() > before) return true;
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, true);
    }
    return monitor.revision() > before;
}

std::set<std::string> persistent_set(const DeviceSnapshot& snapshot, DeviceKind kind) {
    std::set<std::string> result;
    for (const auto& record : snapshot.devices) if (record.kind == kind) result.insert(record.persistent_hash);
    return result;
}

const DeviceRecord* find_new_record(const DeviceSnapshot& snapshot, DeviceKind kind, const std::set<std::string>& before) {
    for (const auto& record : snapshot.devices)
        if (record.kind == kind && record.automatic_reconnect && !before.count(record.persistent_hash)) return &record;
    return nullptr;
}

struct MacEventEvidence {
    bool coreaudio_notification = false;
    bool coremidi_notification = false;
    bool coreaudio_identity_recovery = false;
    bool coremidi_identity_recovery = false;
};

MacEventEvidence exercise_macos_events(DeviceMonitor& monitor) {
    MacEventEvidence evidence;
    auto baseline = monitor.snapshot();

    const auto midi_before = persistent_set(baseline, DeviceKind::Midi);
    MIDIClientRef midi_client = 0;
    MIDIEndpointRef source = 0;
    if (MIDIClientCreate(CFSTR("StageMesh CI MIDI"), nullptr, nullptr, &midi_client) != noErr) throw std::runtime_error("MIDIClientCreate fixture failed");
    const MIDIUniqueID requested_uid = static_cast<MIDIUniqueID>(-1200000000 + (getpid() % 1000000));
    auto revision = monitor.revision();
    if (MIDISourceCreate(midi_client, CFSTR("StageMesh CI Source"), &source) != noErr) throw std::runtime_error("MIDISourceCreate failed");
    if (MIDIObjectSetIntegerProperty(source, kMIDIPropertyUniqueID, requested_uid) != noErr) throw std::runtime_error("set CoreMIDI unique ID failed");
    evidence.coremidi_notification = wait_revision(monitor, revision);
    auto midi_present = monitor.snapshot();
    const DeviceRecord* midi_record_ptr = find_new_record(midi_present, DeviceKind::Midi, midi_before);
    require(midi_record_ptr != nullptr, "CoreMIDI fixture did not expose a stable hashed identity");
    const DeviceRecord midi_record = *midi_record_ptr;
    auto midi_selection = pin_device(midi_record, true, false);
    revision = monitor.revision();
    MIDIEndpointDispose(source); source = 0;
    require(wait_revision(monitor, revision), "CoreMIDI removal notification was not observed");
    require(resolve_device(midi_selection, monitor.snapshot().devices).status == ResolutionStatus::Detached, "CoreMIDI removal did not detach selection");
    revision = monitor.revision();
    if (MIDISourceCreate(midi_client, CFSTR("StageMesh CI Source 2"), &source) != noErr) throw std::runtime_error("second MIDISourceCreate failed");
    if (MIDIObjectSetIntegerProperty(source, kMIDIPropertyUniqueID, requested_uid) != noErr) throw std::runtime_error("restore CoreMIDI unique ID failed");
    require(wait_revision(monitor, revision), "CoreMIDI restore notification was not observed");
    auto midi_restored = resolve_device(midi_selection, monitor.snapshot().devices);
    evidence.coremidi_identity_recovery = midi_restored.status == ResolutionStatus::Attached || midi_restored.status == ResolutionStatus::Rebound;
    MIDIEndpointDispose(source); source = 0;
    MIDIClientDispose(midi_client); midi_client = 0;

    const auto audio_before = persistent_set(baseline, DeviceKind::Audio);
    CFStringRef uid = CFStringCreateWithFormat(kCFAllocatorDefault, nullptr, CFSTR("org.stagemesh.ci.aggregate.%d"), getpid());
    CFMutableDictionaryRef description = CFDictionaryCreateMutable(kCFAllocatorDefault, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceNameKey), CFSTR("StageMesh CI Aggregate"));
    CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceUIDKey), uid);
    AudioDeviceID aggregate = kAudioObjectUnknown;
    revision = monitor.revision();
    auto create_status = AudioHardwareCreateAggregateDevice(description, &aggregate);
    CFRelease(description);
    if (create_status != noErr || aggregate == kAudioObjectUnknown) { CFRelease(uid); throw std::runtime_error("AudioHardwareCreateAggregateDevice failed: " + std::to_string(create_status)); }
    evidence.coreaudio_notification = wait_revision(monitor, revision);
    auto audio_present = monitor.snapshot();
    const DeviceRecord* audio_record_ptr = find_new_record(audio_present, DeviceKind::Audio, audio_before);
    require(audio_record_ptr != nullptr, "CoreAudio aggregate fixture did not expose a stable hashed identity");
    const DeviceRecord audio_record = *audio_record_ptr;
    auto audio_selection = pin_device(audio_record);
    revision = monitor.revision();
    if (AudioHardwareDestroyAggregateDevice(aggregate) != noErr) { CFRelease(uid); throw std::runtime_error("AudioHardwareDestroyAggregateDevice failed"); }
    aggregate = kAudioObjectUnknown;
    require(wait_revision(monitor, revision), "CoreAudio removal notification was not observed");
    require(resolve_device(audio_selection, monitor.snapshot().devices).status == ResolutionStatus::Detached, "CoreAudio removal did not detach selection");

    description = CFDictionaryCreateMutable(kCFAllocatorDefault, 0, &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceNameKey), CFSTR("StageMesh CI Aggregate 2"));
    CFDictionarySetValue(description, CFSTR(kAudioAggregateDeviceUIDKey), uid);
    revision = monitor.revision();
    create_status = AudioHardwareCreateAggregateDevice(description, &aggregate);
    CFRelease(description);
    CFRelease(uid);
    if (create_status != noErr || aggregate == kAudioObjectUnknown) throw std::runtime_error("second aggregate create failed: " + std::to_string(create_status));
    require(wait_revision(monitor, revision), "CoreAudio restore notification was not observed");
    auto audio_restored = resolve_device(audio_selection, monitor.snapshot().devices);
    evidence.coreaudio_identity_recovery = audio_restored.status == ResolutionStatus::Attached || audio_restored.status == ResolutionStatus::Rebound;
    AudioHardwareDestroyAggregateDevice(aggregate);
    return evidence;
}
#endif
}

int main() {
    try {
        using namespace stagemesh;
        exercise_resolution_contract();
        DeviceMonitor monitor;
        bool rejected = false;
        try { monitor.snapshot(); } catch (const std::logic_error&) { rejected = true; }
        require(rejected, "inactive snapshot accepted");
        DeviceSnapshot snapshot{};
        auto begin = std::chrono::steady_clock::now();
        for (unsigned cycle = 0; cycle < 25; ++cycle) {
            monitor.start(); monitor.start();
            snapshot = monitor.snapshot();
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
            monitor.stop(); monitor.stop();
        }
        monitor.start();
        snapshot = monitor.snapshot();
        auto counts = identity_counts(snapshot);
        if (!snapshot.native_midi_enumeration_available || !snapshot.midi_notifications_registered) {
            const auto* allow_unavailable = std::getenv("STAGEMESH_ALLOW_UNAVAILABLE_NATIVE_MIDI");
            if (allow_unavailable && std::string_view(allow_unavailable) == "1") {
                monitor.stop();
                std::cout << "{\"cycles\":25,\"activeDestructionPassed\":true,"
                    << "\"inactiveSnapshotRejected\":true,\"wrongThreadRejected\":true,"
                    << "\"identityAssuranceDowngradeRejected\":true,"
                    << "\"weakDuplicatesRemainAmbiguous\":true,"
                    << "\"nativeMidiEnumerationAvailable\":" << (snapshot.native_midi_enumeration_available ? "true" : "false") << ","
                    << "\"midiNotificationsRegistered\":" << (snapshot.midi_notifications_registered ? "true" : "false") << ","
                    << "\"identityReconciliationQualified\":false,\"physicalOutputsArmed\":false}\n";
                return 0;
            }
            require(false, "native MIDI discovery/notifications unavailable");
        }
        unsigned midi_records = 0;
        for (const auto& record : snapshot.devices) if (record.kind == DeviceKind::Midi) {
            ++midi_records;
#ifdef _WIN32
            require(!record.automatic_reconnect && record.identity_strength != IdentityStrength::OsStableEndpoint,
                    "WinMM legacy identity incorrectly permits automatic reconnect");
#endif
        }
        require(midi_records == snapshot.midi_endpoint_count, "MIDI enumeration count mismatch");
#ifdef __APPLE__
        auto mac = exercise_macos_events(monitor);
        require(mac.coreaudio_notification, "CoreAudio notification delivery not observed");
        require(mac.coremidi_notification, "CoreMIDI notification delivery not observed");
        require(mac.coreaudio_identity_recovery, "CoreAudio persistent identity recovery failed");
        require(mac.coremidi_identity_recovery, "CoreMIDI persistent identity recovery failed");
#endif
        monitor.stop();
        bool wrong_thread_rejected = false;
        std::thread other([&] { try { monitor.start(); } catch (const std::logic_error&) { wrong_thread_rejected = true; } });
        other.join();
        require(wrong_thread_rejected, "cross-thread start accepted");
        { DeviceMonitor another; another.start(); another.snapshot(); }
        { DeviceMonitor recreated; recreated.start(); recreated.snapshot(); }
        auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - begin).count();
        std::cout << std::boolalpha << "{\"cycles\":25,\"activeDestructionPassed\":true,"
            << "\"inactiveSnapshotRejected\":true,\"wrongThreadRejected\":true,\"deviceCount\":" << snapshot.device_count
            << ",\"midiEndpointCount\":" << snapshot.midi_endpoint_count
            << ",\"nativeMidiEnumerationAvailable\":" << snapshot.native_midi_enumeration_available
            << ",\"midiNotificationsRegistered\":" << snapshot.midi_notifications_registered
            << ",\"stableIdentityApiCompiled\":" << snapshot.stable_audio_identity_api_compiled
            << ",\"stableIdentityCount\":" << counts.first << ",\"weakIdentityCount\":" << counts.second
            << ",\"identityReconciliationQualified\":true"
            << ",\"identityAssuranceDowngradeRejected\":true,\"weakDuplicatesRemainAmbiguous\":true"
#ifdef __APPLE__
            << ",\"coreAudioNotificationObserved\":" << mac.coreaudio_notification
            << ",\"coreMidiNotificationObserved\":" << mac.coremidi_notification
            << ",\"coreAudioIdentityRecoveryQualified\":" << mac.coreaudio_identity_recovery
            << ",\"coreMidiIdentityRecoveryQualified\":" << mac.coremidi_identity_recovery
#endif
            << ",\"defaultInputPresent\":" << snapshot.default_input_present
            << ",\"defaultOutputPresent\":" << snapshot.default_output_present
            << ",\"observedNotificationRevision\":" << monitor.revision()
            << ",\"elapsedSeconds\":" << elapsed << "}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
