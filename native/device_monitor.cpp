#include "device_monitor.h"
#include <atomic>
#include <chrono>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#include <mmdeviceapi.h>
#include <propsys.h>
#include <propvarutil.h>
#include <wrl/client.h>
#include <mmsystem.h>
#include <mmddk.h>
#include <cfgmgr32.h>
#ifndef STAGEFORGE_HAS_AUDIOENDPOINT_STABLEID
#define STAGEFORGE_HAS_AUDIOENDPOINT_STABLEID 0
#endif
#ifndef STAGEFORGE_HAS_CM_NOTIFY
#define STAGEFORGE_HAS_CM_NOTIFY 0
#endif
#else
#include <CoreAudio/CoreAudio.h>
#include <CoreMIDI/CoreMIDI.h>
#include <CoreFoundation/CoreFoundation.h>
#endif

namespace stageforge {
namespace {
std::atomic<std::uint64_t> topology_revision{0};

#ifdef _WIN32
void checked(HRESULT status, const char* operation) {
    if (FAILED(status)) throw std::runtime_error(std::string(operation) + ": " + std::to_string(status));
}
std::string utf8(LPCWSTR text) {
    if (!text || !*text) return {};
    int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, -1, nullptr, 0, nullptr, nullptr);
    if (size <= 1) throw std::runtime_error("WideCharToMultiByte size failed");
    std::string out(static_cast<std::size_t>(size), '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, -1, out.data(), size, nullptr, nullptr))
        throw std::runtime_error("WideCharToMultiByte failed");
    if (!out.empty() && out.back() == '\0') out.pop_back();
    return out;
}

class Notifications final : public IMMNotificationClient {
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** out) override {
        if (!out) return E_POINTER;
        *out = nullptr;
        if (iid != __uuidof(IUnknown) && iid != __uuidof(IMMNotificationClient)) return E_NOINTERFACE;
        *out = static_cast<IMMNotificationClient*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return 2; }
    ULONG STDMETHODCALLTYPE Release() override { return 1; }
    HRESULT STDMETHODCALLTYPE OnDeviceStateChanged(LPCWSTR, DWORD) override { return changed(); }
    HRESULT STDMETHODCALLTYPE OnDeviceAdded(LPCWSTR) override { return changed(); }
    HRESULT STDMETHODCALLTYPE OnDeviceRemoved(LPCWSTR) override { return changed(); }
    HRESULT STDMETHODCALLTYPE OnDefaultDeviceChanged(EDataFlow, ERole, LPCWSTR) override { return changed(); }
    HRESULT STDMETHODCALLTYPE OnPropertyValueChanged(LPCWSTR, const PROPERTYKEY) override { return changed(); }
private:
    HRESULT changed() { topology_revision.fetch_add(1, std::memory_order_relaxed); return S_OK; }
};
Notifications notifications;
#if STAGEFORGE_HAS_CM_NOTIFY
DWORD CALLBACK pnp_changed(HCMNOTIFICATION, PVOID, CM_NOTIFY_ACTION, PCM_NOTIFY_EVENT_DATA, DWORD) {
    topology_revision.fetch_add(1, std::memory_order_relaxed); return ERROR_SUCCESS;
}
#endif

DeviceRecord windows_midi_record(UINT index, bool input) {
    const auto message = [&](UINT msg, DWORD_PTR first, DWORD_PTR second) {
        return input ? midiInMessage(reinterpret_cast<HMIDIIN>(static_cast<UINT_PTR>(index)), msg, first, second)
                     : midiOutMessage(reinterpret_cast<HMIDIOUT>(static_cast<UINT_PTR>(index)), msg, first, second);
    };
    std::string caps_material;
    if (input) {
        MIDIINCAPSW caps{};
        if (midiInGetDevCapsW(index, &caps, sizeof(caps)) != MMSYSERR_NOERROR)
            throw std::runtime_error("MIDI input changed during snapshot");
        caps.szPname[MAXPNAMELEN - 1] = L'\0';
        caps_material = std::to_string(caps.wMid) + ":" + std::to_string(caps.wPid) + ":" + utf8(caps.szPname);
    } else {
        MIDIOUTCAPSW caps{};
        if (midiOutGetDevCapsW(index, &caps, sizeof(caps)) != MMSYSERR_NOERROR)
            throw std::runtime_error("MIDI output changed during snapshot");
        caps.szPname[MAXPNAMELEN - 1] = L'\0';
        caps_material = std::to_string(caps.wMid) + ":" + std::to_string(caps.wPid) + ":" + utf8(caps.szPname);
    }
    ULONG bytes = 0;
    std::string interface_name;
    if (message(DRV_QUERYDEVICEINTERFACESIZE, reinterpret_cast<DWORD_PTR>(&bytes), 0) == MMSYSERR_NOERROR &&
        bytes >= sizeof(wchar_t) && bytes <= 65536 && bytes % sizeof(wchar_t) == 0) {
        std::vector<wchar_t> buffer(bytes / sizeof(wchar_t), L'\0');
        if (message(DRV_QUERYDEVICEINTERFACE, reinterpret_cast<DWORD_PTR>(buffer.data()), bytes) == MMSYSERR_NOERROR &&
            buffer.back() == L'\0') interface_name = utf8(buffer.data());
    }
    const std::string direction = input ? ":input:" : ":output:";
    DeviceRecord record;
    record.kind = DeviceKind::Midi; record.input = input; record.output = !input;
    if (!interface_name.empty()) {
        record.native_hash = sha256_token("winmm-native" + direction + interface_name + ":" + std::to_string(index));
        record.persistent_hash = sha256_token("winmm-installation" + direction + interface_name);
        record.identity_strength = IdentityStrength::InstallationSnapshot;
    } else {
        // Legacy index/name is not a persistence-grade identity. Any notified
        // topology change invalidates this fallback, even if the index is reused.
        record.native_hash = sha256_token("winmm-volatile" + direction + caps_material + ":" + std::to_string(index) +
            ":" + std::to_string(topology_revision.load(std::memory_order_relaxed)));
        record.persistent_hash = record.native_hash;
        record.identity_strength = IdentityStrength::Volatile;
    }
    record.automatic_reconnect = false;
    return record;
}

DeviceRecord windows_record(IMMDevice* device) {
    LPWSTR raw_id = nullptr;
    checked(device->GetId(&raw_id), "endpoint id");
    std::string native_material;
    try { native_material = utf8(raw_id); }
    catch (...) { CoTaskMemFree(raw_id); throw; }
    CoTaskMemFree(raw_id);

    Microsoft::WRL::ComPtr<IMMEndpoint> endpoint;
    checked(device->QueryInterface(IID_PPV_ARGS(endpoint.GetAddressOf())), "endpoint flow interface");
    EDataFlow flow = eAll;
    checked(endpoint->GetDataFlow(&flow), "endpoint flow");

    std::string persistent_material;
    bool stable = false;
#if STAGEFORGE_HAS_AUDIOENDPOINT_STABLEID
    Microsoft::WRL::ComPtr<IPropertyStore> store;
    if (SUCCEEDED(device->OpenPropertyStore(STGM_READ, store.GetAddressOf()))) {
        PROPVARIANT value;
        PropVariantInit(&value);
        if (SUCCEEDED(store->GetValue(PKEY_AudioEndpoint_StableId, &value)) && value.vt == VT_LPWSTR && value.pwszVal && *value.pwszVal) {
            persistent_material = utf8(value.pwszVal);
            stable = true;
        }
        PropVariantClear(&value);
    }
#endif
    if (persistent_material.empty()) persistent_material = native_material;

    DeviceRecord record;
    record.kind = DeviceKind::Audio;
    record.native_hash = sha256_token("wasapi-native:" + native_material);
    record.persistent_hash = sha256_token(std::string(stable ? "wasapi-stable:" : "wasapi-installation:") + persistent_material);
    record.identity_strength = stable ? IdentityStrength::OsStableEndpoint : IdentityStrength::InstallationSnapshot;
    record.automatic_reconnect = stable;
    record.input = flow == eCapture || flow == eAll;
    record.output = flow == eRender || flow == eAll;
    return record;
}

#else
void checked(OSStatus status, const char* operation) {
    if (status != noErr) throw std::runtime_error(std::string(operation) + ": " + std::to_string(status));
}
OSStatus changed(AudioObjectID, UInt32, const AudioObjectPropertyAddress*, void*) {
    topology_revision.fetch_add(1, std::memory_order_relaxed); return noErr;
}
std::atomic<unsigned> midi_subscribers{0};
void midi_changed(const MIDINotification*, void*) {
    if (midi_subscribers.load(std::memory_order_relaxed)) topology_revision.fetch_add(1, std::memory_order_relaxed);
}
MIDIClientRef process_midi_client() {
    // CoreMIDI infrastructure is process-owned, like the static notification
    // callback state. A monitor only owns a subscription. Avoid tearing down
    // and rebuilding the MIDI service connection after HAL I/O has executed.
    struct Client {
        MIDIClientRef value = 0;
        Client() { checked(MIDIClientCreate(CFSTR("StageForge Device Monitor"), midi_changed, nullptr, &value), "MIDIClientCreate"); }
        ~Client() { if (value && MIDIClientDispose(value) != noErr) std::terminate(); }
    };
    static Client client;
    return client.value;
}
const AudioObjectPropertyAddress addresses[] = {
    {kAudioHardwarePropertyDevices, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain},
    {kAudioHardwarePropertyDefaultInputDevice, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain},
    {kAudioHardwarePropertyDefaultOutputDevice, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain},
};

std::string cf_string(CFStringRef value) {
    if (!value) return {};
    const auto length = CFStringGetLength(value);
    const auto maximum = CFStringGetMaximumSizeForEncoding(length, kCFStringEncodingUTF8) + 1;
    std::vector<char> buffer(static_cast<std::size_t>(maximum));
    if (!CFStringGetCString(value, buffer.data(), maximum, kCFStringEncodingUTF8))
        throw std::runtime_error("CFString UTF-8 conversion failed");
    return std::string(buffer.data());
}

unsigned channel_count(AudioDeviceID device, AudioObjectPropertyScope scope) {
    AudioObjectPropertyAddress address{kAudioDevicePropertyStreamConfiguration, scope, kAudioObjectPropertyElementMain};
    UInt32 size = 0;
    auto status = AudioObjectGetPropertyDataSize(device, &address, 0, nullptr, &size);
    if (status != noErr || !size) return 0;
    std::vector<std::uint8_t> storage(size);
    status = AudioObjectGetPropertyData(device, &address, 0, nullptr, &size, storage.data());
    if (status != noErr) return 0;
    auto* list = reinterpret_cast<const AudioBufferList*>(storage.data());
    unsigned channels = 0;
    for (UInt32 i=0;i<list->mNumberBuffers;++i) channels += list->mBuffers[i].mNumberChannels;
    return channels;
}

DeviceRecord coreaudio_record(AudioDeviceID device) {
    AudioObjectPropertyAddress uid_address{kAudioDevicePropertyDeviceUID, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    CFStringRef uid = nullptr;
    UInt32 size = sizeof(uid);
    std::string uid_text;
    if (AudioObjectGetPropertyData(device, &uid_address, 0, nullptr, &size, &uid) == noErr && uid) {
        uid_text = cf_string(uid);
        CFRelease(uid);
    }
    DeviceRecord record;
    record.kind = DeviceKind::Audio;
    record.native_hash = sha256_token("coreaudio-native:" + std::to_string(device));
    if (uid_text.empty()) {
        record.persistent_hash = record.native_hash;
        record.identity_strength = IdentityStrength::Volatile;
        record.automatic_reconnect = false;
    } else {
        record.persistent_hash = sha256_token("coreaudio-uid:" + uid_text);
        record.identity_strength = IdentityStrength::OsStableEndpoint;
        record.automatic_reconnect = true;
    }
    record.input = channel_count(device, kAudioObjectPropertyScopeInput) > 0;
    record.output = channel_count(device, kAudioObjectPropertyScopeOutput) > 0;
    return record;
}

DeviceRecord coremidi_record(MIDIEndpointRef endpoint, bool input, bool output) {
    MIDIUniqueID unique = 0;
    const auto status = MIDIObjectGetIntegerProperty(endpoint, kMIDIPropertyUniqueID, &unique);
    const auto native_material = std::to_string(static_cast<std::uint64_t>(endpoint));
    DeviceRecord record;
    record.kind = DeviceKind::Midi;
    record.native_hash = sha256_token("coremidi-native:" + native_material + (input ? ":in" : ":out"));
    if (status == noErr && unique != 0) {
        record.persistent_hash = sha256_token("coremidi-unique:" + std::to_string(unique) + (input ? ":in" : ":out"));
        record.identity_strength = IdentityStrength::OsStableEndpoint;
        record.automatic_reconnect = true;
    } else {
        record.persistent_hash = record.native_hash;
        record.identity_strength = IdentityStrength::Volatile;
        record.automatic_reconnect = false;
    }
    record.input = input;
    record.output = output;
    return record;
}
#endif
}

struct DeviceMonitor::Impl {
    std::thread::id owner = std::this_thread::get_id();
    bool active = false;
    void check_thread() const {
        if (owner != std::this_thread::get_id()) throw std::logic_error("DeviceMonitor control thread changed");
    }
#ifdef _WIN32
    Microsoft::WRL::ComPtr<IMMDeviceEnumerator> enumerator;
    HCMNOTIFICATION midi_notification = nullptr;
    bool audio_registered = false;
    Impl() {
        checked(CoInitializeEx(nullptr, COINIT_MULTITHREADED), "CoInitializeEx");
        try {
            checked(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                IID_PPV_ARGS(enumerator.GetAddressOf())), "MMDeviceEnumerator");
        } catch (...) { CoUninitialize(); throw; }
    }
    ~Impl() { enumerator.Reset(); CoUninitialize(); }
#else
    unsigned registered = 0;
    MIDIClientRef midi_client = 0;
    Impl() : midi_client(process_midi_client()) {}
#endif
};

DeviceMonitor::DeviceMonitor() : impl_(std::make_unique<Impl>()) {}
DeviceMonitor::~DeviceMonitor() {
    try { stop(); } catch (...) { std::terminate(); }
}
void DeviceMonitor::start() {
    impl_->check_thread();
    if (impl_->active) return;
#ifdef _WIN32
    try {
        checked(impl_->enumerator->RegisterEndpointNotificationCallback(&notifications), "register notifications");
        impl_->audio_registered = true;
#if STAGEFORGE_HAS_CM_NOTIFY
        CM_NOTIFY_FILTER filter{};
        filter.cbSize = sizeof(filter); filter.FilterType = CM_NOTIFY_FILTER_TYPE_DEVICEINTERFACE;
        // All interface classes avoids missing vendor-specific MIDI interfaces.
        // Callback only invalidates snapshots; it never opens a device.
        filter.Flags = CM_NOTIFY_FILTER_FLAG_ALL_INTERFACE_CLASSES;
        auto status = CM_Register_Notification(&filter, nullptr, pnp_changed, &impl_->midi_notification);
        if (status != CR_SUCCESS) throw std::runtime_error("register MIDI PnP notifications: " + std::to_string(status));
#endif
    } catch (...) { stop(); throw; }
#else
    try {
        for (; impl_->registered < 3; ++impl_->registered)
            checked(AudioObjectAddPropertyListener(kAudioObjectSystemObject,
                &addresses[impl_->registered], changed, impl_.get()), "add property listener");
        midi_subscribers.fetch_add(1, std::memory_order_relaxed);
    } catch (...) { stop(); throw; }
#endif
    impl_->active = true;
}
void DeviceMonitor::stop() {
    impl_->check_thread();
#ifdef _WIN32
#if STAGEFORGE_HAS_CM_NOTIFY
    if (impl_->midi_notification) {
        auto status = CM_Unregister_Notification(impl_->midi_notification);
        if (status != CR_SUCCESS) throw std::runtime_error("unregister MIDI PnP notifications: " + std::to_string(status));
        impl_->midi_notification = nullptr;
    }
#endif
    if (impl_->audio_registered) {
        checked(impl_->enumerator->UnregisterEndpointNotificationCallback(&notifications), "unregister notifications");
        impl_->audio_registered = false;
    }
#else
    if (impl_->active) midi_subscribers.fetch_sub(1, std::memory_order_relaxed);
    while (impl_->registered) {
        checked(AudioObjectRemovePropertyListener(kAudioObjectSystemObject,
            &addresses[impl_->registered - 1], changed, impl_.get()), "remove property listener");
        --impl_->registered;
    }
#endif
    impl_->active = false;
}
std::uint64_t DeviceMonitor::revision() const { return topology_revision.load(std::memory_order_relaxed); }
DeviceSnapshot DeviceMonitor::snapshot() const {
    impl_->check_thread();
    if (!impl_->active) throw std::logic_error("snapshot requires an active monitor");
    DeviceSnapshot result{};
#ifdef _WIN32
    result.stable_audio_identity_api_compiled = STAGEFORGE_HAS_AUDIOENDPOINT_STABLEID != 0;
    Microsoft::WRL::ComPtr<IMMDeviceCollection> devices;
    checked(impl_->enumerator->EnumAudioEndpoints(eAll, DEVICE_STATE_ACTIVE, devices.GetAddressOf()), "enumerate endpoints");
    checked(devices->GetCount(&result.device_count), "endpoint count");
    for (UINT i=0;i<result.device_count;++i) {
        Microsoft::WRL::ComPtr<IMMDevice> device;
        checked(devices->Item(i, device.GetAddressOf()), "endpoint item");
        result.devices.push_back(windows_record(device.Get()));
    }
    auto has_default = [&](EDataFlow flow) {
        Microsoft::WRL::ComPtr<IMMDevice> device;
        auto status = impl_->enumerator->GetDefaultAudioEndpoint(flow, eConsole, device.GetAddressOf());
        if (status == HRESULT_FROM_WIN32(ERROR_NOT_FOUND)) return false;
        checked(status, "default endpoint"); return true;
    };
    result.default_input_present = has_default(eCapture);
    result.default_output_present = has_default(eRender);
    result.native_midi_enumeration_available = true;
    result.midi_notifications_registered = impl_->midi_notification != nullptr;
    const auto revision_before = topology_revision.load(std::memory_order_relaxed);
    const UINT inputs = midiInGetNumDevs(), outputs = midiOutGetNumDevs();
    for (UINT i = 0; i < inputs; ++i) result.devices.push_back(windows_midi_record(i, true));
    for (UINT i = 0; i < outputs; ++i) result.devices.push_back(windows_midi_record(i, false));
    if (inputs != midiInGetNumDevs() || outputs != midiOutGetNumDevs() ||
        revision_before != topology_revision.load(std::memory_order_relaxed))
        throw std::runtime_error("MIDI topology changed during snapshot; refresh required");
    result.midi_endpoint_count = inputs + outputs;
#else
    result.stable_audio_identity_api_compiled = true;
    std::vector<AudioDeviceID> audio_devices;
    for (unsigned attempt = 0; ; ++attempt) {
        UInt32 size = 0;
        checked(AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &addresses[0], 0, nullptr, &size), "device data size");
        audio_devices.resize(size / sizeof(AudioDeviceID));
        auto status = size ? AudioObjectGetPropertyData(kAudioObjectSystemObject, &addresses[0], 0, nullptr, &size, audio_devices.data()) : noErr;
        if (status == kAudioHardwareBadPropertySizeError && attempt < 2) continue;
        checked(status, "enumerate devices");
        audio_devices.resize(size / sizeof(AudioDeviceID));
        break;
    }
    result.device_count = static_cast<unsigned>(audio_devices.size());
    for (auto device : audio_devices) result.devices.push_back(coreaudio_record(device));
    auto has_default = [&](unsigned index) {
        AudioDeviceID device = kAudioObjectUnknown; UInt32 size = sizeof(device);
        checked(AudioObjectGetPropertyData(kAudioObjectSystemObject, &addresses[index], 0, nullptr, &size, &device), "default device");
        return device != kAudioObjectUnknown;
    };
    result.default_input_present = has_default(1);
    result.default_output_present = has_default(2);

    const auto sources = MIDIGetNumberOfSources();
    const auto destinations = MIDIGetNumberOfDestinations();
    result.midi_endpoint_count = static_cast<unsigned>(sources + destinations);
    result.native_midi_enumeration_available = true;
    result.midi_notifications_registered = impl_->midi_client != 0;
    for (ItemCount i=0;i<sources;++i) {
        auto endpoint = MIDIGetSource(i);
        if (endpoint) result.devices.push_back(coremidi_record(endpoint, true, false));
    }
    for (ItemCount i=0;i<destinations;++i) {
        auto endpoint = MIDIGetDestination(i);
        if (endpoint) result.devices.push_back(coremidi_record(endpoint, false, true));
    }
#endif
    return result;
}
}
