#pragma once
#include "device_identity.h"
#include <cstdint>
#include <memory>
#include <vector>

namespace stagemesh {
struct DeviceSnapshot {
    unsigned device_count = 0;
    unsigned midi_endpoint_count = 0;
    bool default_input_present = false;
    bool default_output_present = false;
    bool stable_audio_identity_api_compiled = false;
    bool native_midi_enumeration_available = false;
    bool midi_notifications_registered = false;
    std::vector<DeviceRecord> devices;
};

// Control-thread API. OS callbacks only advance an atomic revision; callers
// refresh snapshots off the audio thread. Snapshots export hashed identities only.
// No stream is opened or automatically restarted by this monitor.
// macOS shares one process-owned CoreMIDI client; start/stop owns only this
// monitor's notification subscription and CoreAudio listeners.
class DeviceMonitor {
public:
    DeviceMonitor();
    ~DeviceMonitor();
    DeviceMonitor(const DeviceMonitor&) = delete;
    DeviceMonitor& operator=(const DeviceMonitor&) = delete;
    void start();
    void stop();
    DeviceSnapshot snapshot() const;
    std::uint64_t revision() const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
