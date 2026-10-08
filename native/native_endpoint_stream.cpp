#include "native_endpoint_stream.h"
#include <atomic>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <vector>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <audioclient.h>
#include <mmdeviceapi.h>
#include <ks.h>
#include <ksmedia.h>
#include <wrl/client.h>
#else
#include <AudioUnit/AudioUnit.h>
#include <CoreAudio/CoreAudio.h>
#endif

namespace stagemesh {
namespace {
// Process-lifetime callback storage: OS notifications never dereference a stream
// object, including a callback already dispatched during listener removal.
// Conservative policy: any watched endpoint change fences all prepared streams.
std::atomic<std::uint64_t> endpoint_epoch{0};
static_assert(std::atomic<std::uint64_t>::is_always_lock_free);
static_assert(std::atomic<bool>::is_always_lock_free);
#ifdef _WIN32
void checked(HRESULT value, const char* operation) {
    if (FAILED(value)) {
        char hexadecimal[11]{};
        std::snprintf(hexadecimal, sizeof(hexadecimal), "0x%08lX", static_cast<unsigned long>(value));
        throw std::runtime_error(std::string(operation) + ": " + std::to_string(value) +
            " (" + hexadecimal + ")");
    }
}
std::string utf8(const wchar_t* text) {
    int n = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, -1, nullptr, 0, nullptr, nullptr);
    if (n <= 1) throw std::runtime_error("invalid endpoint ID");
    std::string result(n, '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, -1, result.data(), n, nullptr, nullptr))
        throw std::runtime_error("endpoint ID conversion failed");
    result.pop_back(); return result;
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
    HRESULT changed() { endpoint_epoch.fetch_add(1); return S_OK; }
};
Notifications notifications;
bool exact_wave(const WAVEFORMATEX* wave, const AudioRequest& request) {
    bool floating = wave->wFormatTag == WAVE_FORMAT_IEEE_FLOAT;
    if (wave->wFormatTag == WAVE_FORMAT_EXTENSIBLE && wave->cbSize >= 22) {
        const auto* extended = reinterpret_cast<const WAVEFORMATEXTENSIBLE*>(wave);
        floating = IsEqualGUID(extended->SubFormat, KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) &&
            extended->Samples.wValidBitsPerSample == 32;
    }
    return floating && wave->wBitsPerSample == 32 && wave->nSamplesPerSec == request.sample_rate_hz &&
        wave->nChannels == request.channels && wave->nBlockAlign == request.channels * sizeof(float);
}
#else
void checked(OSStatus value, const char* operation) {
    if (value != noErr) throw std::runtime_error(std::string(operation) + ": " + std::to_string(value));
}
OSStatus property_changed(AudioObjectID, UInt32, const AudioObjectPropertyAddress*, void*) {
    endpoint_epoch.fetch_add(1); return noErr;
}
const AudioObjectPropertyAddress watched[] = {
    {kAudioDevicePropertyDeviceIsAlive, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain},
    {kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain},
    {kAudioDevicePropertyBufferFrameSize, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain},
    {kAudioDevicePropertyStreams, kAudioObjectPropertyScopeOutput, kAudioObjectPropertyElementMain},
    {kAudioDevicePropertyStreamConfiguration, kAudioObjectPropertyScopeOutput, kAudioObjectPropertyElementMain},
    {kAudioDevicePropertyDeviceUID, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain},
};
const AudioObjectPropertyAddress devices_address{
    kAudioHardwarePropertyDevices, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
template<class T> T property(AudioDeviceID device, AudioObjectPropertySelector selector) {
    T result{}; UInt32 size = sizeof(result);
    AudioObjectPropertyAddress address{selector, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    checked(AudioObjectGetPropertyData(device, &address, 0, nullptr, &size, &result), "read device property");
    if (size != sizeof(result)) throw std::runtime_error("unexpected device property size");
    return result;
}
std::string uid_hash(AudioDeviceID device) {
    auto value = property<CFStringRef>(device, kAudioDevicePropertyDeviceUID);
    if (!value) throw std::runtime_error("empty device UID");
    std::vector<char> bytes(CFStringGetMaximumSizeForEncoding(CFStringGetLength(value), kCFStringEncodingUTF8) + 1);
    const bool ok = CFStringGetCString(value, bytes.data(), bytes.size(), kCFStringEncodingUTF8);
    CFRelease(value);
    if (!ok || !bytes[0]) throw std::runtime_error("invalid device UID");
    return sha256_token("coreaudio-uid:" + std::string(bytes.data()));
}
#endif
}

struct NativeEndpointStream::Impl {
    std::thread::id owner = std::this_thread::get_id();
    GuardedAudioStreamLifecycle lifecycle;
    const AudioDirection direction;
    PlaybackRender render;
    CaptureReceive receive;
    void* context;
    AudioRequest request;
    AudioPreflightDecision verified;
    DeviceSelection selection;
    const DeviceExecutionFence* fence_owner = nullptr;
    std::atomic<bool> allowed{false}, fault{false};
    std::atomic<std::uint64_t> callbacks{0}, frames{0};
    std::atomic<std::uint64_t> in_flight{0};
    std::atomic<std::uint64_t> discontinuities{0};
    std::vector<float> capture_buffer;
    std::uint64_t prepared_epoch = 0;
    bool opened = false, running = false;
#ifdef _WIN32
    bool apartment = false, registered = false;
    Microsoft::WRL::ComPtr<IMMDeviceEnumerator> enumerator;
    Microsoft::WRL::ComPtr<IMMDevice> device;
    Microsoft::WRL::ComPtr<IAudioClient3> client;
    Microsoft::WRL::ComPtr<IAudioRenderClient> output;
    Microsoft::WRL::ComPtr<IAudioCaptureClient> input;
    HANDLE event = nullptr;
    UINT32 buffer_frames = 0;
#else
    AudioDeviceID device = kAudioObjectUnknown;
    AudioUnit unit = nullptr;
    bool initialized = false, system_registered = false;
    unsigned registered = 0;
    bool previous_timestamp = false;
    double next_sample = 0;
    AudioObjectPropertyAddress watch_address(unsigned index) const {
        auto address = watched[index];
        if (direction == AudioDirection::Capture && address.mScope == kAudioObjectPropertyScopeOutput)
            address.mScope = kAudioObjectPropertyScopeInput;
        return address;
    }
    static OSStatus callback(void* raw, AudioUnitRenderActionFlags* flags, const AudioTimeStamp* timestamp,
                             UInt32, UInt32 count, AudioBufferList* buffers) {
        auto& self = *static_cast<Impl*>(raw);
        struct Lease {
            std::atomic<std::uint64_t>& count;
            explicit Lease(std::atomic<std::uint64_t>& value) : count(value) { count.fetch_add(1); }
            ~Lease() { count.fetch_sub(1); }
        } lease(self.in_flight);
        if (self.direction == AudioDirection::Capture) {
            if (!self.allowed.load() || endpoint_epoch.load() != self.prepared_epoch) return noErr;
            if (!timestamp || count > self.capture_buffer.size() / self.request.channels) {
                self.fault.store(true); self.allowed.store(false); return kAudio_ParamError;
            }
            AudioBufferList captured{}; captured.mNumberBuffers = 1;
            captured.mBuffers[0] = {self.request.channels, static_cast<UInt32>(count * self.request.channels * sizeof(float)), self.capture_buffer.data()};
            auto status = AudioUnitRender(self.unit, flags, timestamp, 1, count, &captured);
            if (status != noErr) { self.fault.store(true); self.allowed.store(false); return status; }
            CapturePacketInfo info;
            info.timestamp_valid = (timestamp->mFlags & kAudioTimeStampSampleTimeValid) != 0;
            info.sample_position = info.timestamp_valid ? timestamp->mSampleTime : 0;
            info.discontinuity = info.timestamp_valid && self.previous_timestamp && timestamp->mSampleTime != self.next_sample;
            self.previous_timestamp = info.timestamp_valid;
            self.next_sample = timestamp->mSampleTime + count;
            self.deliver(self.capture_buffer.data(), count, info);
            return noErr;
        }
        if (!buffers || buffers->mNumberBuffers != 1 ||
            buffers->mBuffers[0].mNumberChannels != self.request.channels ||
            !buffers->mBuffers[0].mData ||
            buffers->mBuffers[0].mDataByteSize < std::uint64_t(count) * self.request.channels * sizeof(float)) {
            self.fault.store(true); self.allowed.store(false); return kAudio_ParamError;
        }
        auto* data = static_cast<float*>(buffers->mBuffers[0].mData);
        if (!self.dispatch(data, count)) *flags |= kAudioUnitRenderAction_OutputIsSilence;
        return noErr;
    }
#endif
    Impl(AudioDirection flow, PlaybackRender fn, CaptureReceive input_fn, void* ctx)
        : direction(flow), render(fn), receive(input_fn), context(ctx) {}
    void check_thread() const {
        if (std::this_thread::get_id() != owner) throw std::logic_error("playback stream used off owner thread");
    }
    bool matches(const DeviceExecutionFence& fence) const {
        return fence_owner == &fence && selection.native_hash == fence.selection().native_hash &&
            selection.persistent_hash == fence.selection().persistent_hash;
    }
    bool dispatch(float* data, std::uint32_t count) noexcept {
        // Zero before calling user code so partially written buffers remain safe.
        std::memset(data, 0, std::size_t(count) * request.channels * sizeof(float));
        if (!allowed.load() || endpoint_epoch.load() != prepared_epoch || fault.load()) return false;
        if (render) render(data, count, request.channels, context);
        // A revoke concurrent with rendering discards that completed buffer.
        if (!allowed.load() || endpoint_epoch.load() != prepared_epoch) {
            std::memset(data, 0, std::size_t(count) * request.channels * sizeof(float)); return false;
        }
        callbacks.fetch_add(1, std::memory_order_relaxed);
        frames.fetch_add(count, std::memory_order_relaxed);
        return render != nullptr;
    }
    void deliver(const float* data, std::uint32_t count, const CapturePacketInfo& info) noexcept {
        if (!allowed.load() || endpoint_epoch.load() != prepared_epoch || fault.load()) return;
        if (info.discontinuity) discontinuities.fetch_add(1, std::memory_order_relaxed);
        if (receive) receive(data, count, request.channels, info, context);
        callbacks.fetch_add(1, std::memory_order_relaxed);
        frames.fetch_add(count, std::memory_order_relaxed);
    }
    void stop_native() {
        allowed.store(false);
        if (!running) return;
#ifdef _WIN32
        const auto status = client->Stop();
        if (status != AUDCLNT_E_DEVICE_INVALIDATED && status != AUDCLNT_E_RESOURCES_INVALIDATED)
            checked(status, "stop WASAPI");
#else
        checked(AudioOutputUnitStop(unit), "stop AUHAL");
        // Stop prevents future scheduling; drain any already executing callback
        // before the control thread can mutate its configuration/user context.
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        while (in_flight.load()) {
            if (std::chrono::steady_clock::now() >= deadline) throw std::runtime_error("AUHAL callback did not drain");
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
#endif
        running = false;
    }
    void release_native() {
        stop_native();
#ifdef _WIN32
        if (registered) { checked(enumerator->UnregisterEndpointNotificationCallback(&notifications), "unregister WASAPI listener"); registered = false; }
        output.Reset(); input.Reset(); client.Reset(); device.Reset(); enumerator.Reset();
        if (event) { CloseHandle(event); event = nullptr; }
        if (apartment) { CoUninitialize(); apartment = false; }
#else
        if (initialized) { checked(AudioUnitUninitialize(unit), "uninitialize AUHAL"); initialized = false; }
        if (unit) { checked(AudioComponentInstanceDispose(unit), "dispose AUHAL"); unit = nullptr; }
        while (registered) {
            auto address = watch_address(registered - 1);
            auto status = AudioObjectRemovePropertyListener(device, &address, property_changed, nullptr);
            if (status != kAudioHardwareBadObjectError) checked(status, "remove device listener");
            --registered;
        }
        if (system_registered) {
            checked(AudioObjectRemovePropertyListener(kAudioObjectSystemObject, &devices_address, property_changed, nullptr), "remove topology listener");
            system_registered = false;
        }
        device = kAudioObjectUnknown;
#endif
        opened = false;
        // Discard captured data after the native callback has drained.
        std::fill(capture_buffer.begin(), capture_buffer.end(), 0.0f);
        capture_buffer.clear();
    }
    void validate_native() {
#ifdef _WIN32
        DWORD state = 0; checked(device->GetState(&state), "WASAPI state");
        if (state != DEVICE_STATE_ACTIVE) throw std::runtime_error("selected endpoint inactive");
        WAVEFORMATEX* current = nullptr; UINT32 period = 0;
        checked(client->GetCurrentSharedModeEnginePeriod(&current, &period), "WASAPI active format");
        const bool exact = exact_wave(current, request) && period == request.period_frames;
        const auto rate = current->nSamplesPerSec, channels = static_cast<DWORD>(current->nChannels);
        CoTaskMemFree(current);
        if (!exact) throw std::runtime_error("WASAPI active configuration differs from exact request");
        verified.configured_sample_rate_hz = rate; verified.configured_period_frames = period;
        verified.configured_channels = channels;
#else
        const auto native_rate = property<Float64>(device, kAudioDevicePropertyNominalSampleRate);
        const auto native_period = property<UInt32>(device, kAudioDevicePropertyBufferFrameSize);
        if (!property<UInt32>(device, kAudioDevicePropertyDeviceIsAlive) ||
            uid_hash(device) != selection.persistent_hash ||
            (native_rate != request.sample_rate_hz && !request.allow_rate_conversion) ||
            (native_period != request.period_frames && !request.allow_period_adaptation))
            throw std::runtime_error("CoreAudio identity/rate/period changed");
        AudioStreamBasicDescription format{}; UInt32 size = sizeof(format);
        checked(AudioUnitGetProperty(unit, kAudioUnitProperty_StreamFormat,
            direction == AudioDirection::Playback ? kAudioUnitScope_Input : kAudioUnitScope_Output,
            direction == AudioDirection::Playback ? 0 : 1, &format, &size), "read AUHAL client format");
        if ((format.mSampleRate != request.sample_rate_hz && !request.allow_rate_conversion) ||
            (format.mChannelsPerFrame != request.channels && !request.allow_channel_conversion) ||
            format.mFormatID != kAudioFormatLinearPCM || format.mBitsPerChannel != 32 ||
            format.mFormatFlags != kAudioFormatFlagsNativeFloatPacked || format.mBytesPerFrame != request.channels * sizeof(float))
            throw std::runtime_error("AUHAL client configuration differs from exact request");
        verified.configured_sample_rate_hz = static_cast<std::uint32_t>(native_rate);
        verified.configured_period_frames = native_period;
        verified.configured_channels = format.mChannelsPerFrame;
#endif
        verified.configured_format = AudioSampleFormat::Float32;
        const bool adapted = verified.configured_sample_rate_hz != request.sample_rate_hz ||
            verified.configured_period_frames != request.period_frames || verified.configured_channels != request.channels;
        verified.status = adapted ? AudioPreflightStatus::ExplicitAdaptation : AudioPreflightStatus::Exact;
        verified.reason = adapted ? "native-readback-explicit-adaptation" : "native-readback-exact";
    }
    void open_native() {
#ifdef _WIN32
        checked(CoInitializeEx(nullptr, COINIT_MULTITHREADED), "playback COM apartment"); apartment = true;
        checked(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, IID_PPV_ARGS(enumerator.GetAddressOf())), "playback enumerator");
        checked(enumerator->RegisterEndpointNotificationCallback(&notifications), "register playback listener"); registered = true;
        prepared_epoch = endpoint_epoch.load();
        Microsoft::WRL::ComPtr<IMMDeviceCollection> endpoints;
        checked(enumerator->EnumAudioEndpoints(direction == AudioDirection::Playback ? eRender : eCapture, DEVICE_STATE_ACTIVE, &endpoints), "enumerate audio endpoints");
        UINT count = 0; checked(endpoints->GetCount(&count), "playback endpoint count");
        for (UINT i = 0; i < count; ++i) {
            Microsoft::WRL::ComPtr<IMMDevice> candidate; checked(endpoints->Item(i, &candidate), "playback endpoint");
            LPWSTR raw = nullptr; checked(candidate->GetId(&raw), "playback ID");
            std::string hash;
            try { hash = sha256_token("wasapi-native:" + utf8(raw)); } catch (...) { CoTaskMemFree(raw); throw; }
            CoTaskMemFree(raw);
            if (hash == selection.native_hash) { if (device) throw std::runtime_error("ambiguous playback ID"); device = candidate; }
        }
        if (!device) throw std::runtime_error("selected playback endpoint absent");
        checked(device->Activate(__uuidof(IAudioClient3), CLSCTX_ALL, nullptr, reinterpret_cast<void**>(client.GetAddressOf())), "activate IAudioClient3");
        WAVEFORMATEX* mix = nullptr; checked(client->GetMixFormat(&mix), "playback mix format");
        try {
            if (!exact_wave(mix, request)) throw std::runtime_error("exact float32 mix format required");
            UINT32 def = 0, fundamental = 0, minimum = 0, maximum = 0;
            checked(client->GetSharedModeEnginePeriod(mix, &def, &fundamental, &minimum, &maximum), "shared engine periods");
            if (!fundamental || request.period_frames % fundamental || request.period_frames < minimum || request.period_frames > maximum)
                throw std::runtime_error("exact shared engine period unavailable");
            event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
            if (!event) throw std::runtime_error("playback event creation failed");
            checked(client->InitializeSharedAudioStream(AUDCLNT_STREAMFLAGS_EVENTCALLBACK, request.period_frames, mix, nullptr), "initialize exact WASAPI stream");
            checked(client->SetEventHandle(event), "playback event handle");
        } catch (...) { CoTaskMemFree(mix); throw; }
        CoTaskMemFree(mix);
        checked(client->GetBufferSize(&buffer_frames), "playback buffer size");
        if (direction == AudioDirection::Playback)
            checked(client->GetService(IID_PPV_ARGS(output.GetAddressOf())), "playback render service");
        else {
            checked(client->GetService(IID_PPV_ARGS(input.GetAddressOf())), "capture service");
            capture_buffer.assign(static_cast<std::size_t>(buffer_frames) * request.channels, 0.0f);
        }
#else
        checked(AudioObjectAddPropertyListener(kAudioObjectSystemObject, &devices_address, property_changed, nullptr), "listen playback topology");
        system_registered = true;
        prepared_epoch = endpoint_epoch.load();
        UInt32 size = 0;
        checked(AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &devices_address, 0, nullptr, &size), "device list size");
        std::vector<AudioDeviceID> devices(size / sizeof(AudioDeviceID));
        checked(AudioObjectGetPropertyData(kAudioObjectSystemObject, &devices_address, 0, nullptr, &size, devices.data()), "device list");
        for (auto id : devices) if (sha256_token("coreaudio-native:" + std::to_string(id)) == selection.native_hash) device = id;
        if (device == kAudioObjectUnknown)
            throw std::runtime_error("selected CoreAudio native ID absent");
        if (uid_hash(device) != selection.persistent_hash)
            throw std::runtime_error("selected CoreAudio UID hash mismatch");
        for (; registered < sizeof(watched) / sizeof(watched[0]); ++registered) {
            auto address = watch_address(registered);
            checked(AudioObjectAddPropertyListener(device, &address, property_changed, nullptr), "listen selected device");
        }
        AudioComponentDescription description{};
        description.componentType = kAudioUnitType_Output; description.componentSubType = kAudioUnitSubType_HALOutput;
        description.componentManufacturer = kAudioUnitManufacturer_Apple;
        auto component = AudioComponentFindNext(nullptr, &description);
        if (!component) throw std::runtime_error("AUHAL unavailable");
        checked(AudioComponentInstanceNew(component, &unit), "create AUHAL");
        UInt32 output_enabled = direction == AudioDirection::Playback ? 1 : 0;
        UInt32 input_enabled = direction == AudioDirection::Capture ? 1 : 0;
        checked(AudioUnitSetProperty(unit, kAudioOutputUnitProperty_EnableIO, kAudioUnitScope_Output, 0, &output_enabled, sizeof(output_enabled)), "set AUHAL output enable");
        checked(AudioUnitSetProperty(unit, kAudioOutputUnitProperty_EnableIO, kAudioUnitScope_Input, 1, &input_enabled, sizeof(input_enabled)), "set AUHAL input enable");
        checked(AudioUnitSetProperty(unit, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0, &device, sizeof(device)), "pin AUHAL device");
        AudioStreamBasicDescription native{}; size = sizeof(native);
        checked(AudioUnitGetProperty(unit, kAudioUnitProperty_StreamFormat,
            direction == AudioDirection::Playback ? kAudioUnitScope_Output : kAudioUnitScope_Input,
            direction == AudioDirection::Playback ? 0 : 1, &native, &size), "AUHAL native format");
        if ((native.mSampleRate != request.sample_rate_hz && !request.allow_rate_conversion) ||
            (native.mChannelsPerFrame != request.channels && !request.allow_channel_conversion))
            throw std::runtime_error("AUHAL rate/channel conversion requires explicit permission");
        AudioStreamBasicDescription format{};
        format.mSampleRate = request.sample_rate_hz; format.mFormatID = kAudioFormatLinearPCM;
        format.mFormatFlags = kAudioFormatFlagsNativeFloatPacked; format.mChannelsPerFrame = request.channels;
        format.mBytesPerPacket = format.mBytesPerFrame = request.channels * sizeof(float);
        format.mFramesPerPacket = 1; format.mBitsPerChannel = 32;
        checked(AudioUnitSetProperty(unit, kAudioUnitProperty_StreamFormat,
            direction == AudioDirection::Playback ? kAudioUnitScope_Input : kAudioUnitScope_Output,
            direction == AudioDirection::Playback ? 0 : 1, &format, sizeof(format)), "configure exact AUHAL client format");
        checked(AudioUnitSetProperty(unit, kAudioUnitProperty_MaximumFramesPerSlice, kAudioUnitScope_Global, 0, &request.period_frames, sizeof(request.period_frames)), "AUHAL maximum slice");
        AURenderCallbackStruct cb{callback, this};
        if (direction == AudioDirection::Playback)
            checked(AudioUnitSetProperty(unit, kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0, &cb, sizeof(cb)), "AUHAL output callback");
        else {
            const auto callback_frames = std::max<std::uint32_t>(request.period_frames,
                property<UInt32>(device, kAudioDevicePropertyBufferFrameSize));
            capture_buffer.assign(static_cast<std::size_t>(callback_frames) * request.channels, 0.0f);
            checked(AudioUnitSetProperty(unit, kAudioOutputUnitProperty_SetInputCallback, kAudioUnitScope_Global, 0, &cb, sizeof(cb)), "AUHAL input callback");
        }
        checked(AudioUnitInitialize(unit), "initialize AUHAL"); initialized = true;
#endif
        validate_native();
        if (prepared_epoch != endpoint_epoch.load()) throw std::runtime_error("device changed during preparation");
        opened = true;
    }
    void revoke(FenceObservation fence) {
        allowed.store(false);
        fence.execution_allowed = false; fence.explicit_rearm_required = true;
        lifecycle.reconcile(fence);
        stop_native(); lifecycle.mark_stopped();
    }
};

NativeEndpointStream::NativeEndpointStream(AudioDirection direction, PlaybackRender render, CaptureReceive receive, void* context)
    : impl_(std::make_unique<Impl>(direction, render, receive, context)) {}
NativeEndpointStream::~NativeEndpointStream() { try { close(); } catch (...) { std::terminate(); } }
bool NativeEndpointStream::prepare(const AudioRequest& request, const DeviceExecutionFence& fence) {
    auto& self = *impl_; self.check_thread();
    if (self.running || request.direction != self.direction || request.format != AudioSampleFormat::Float32 ||
        !request.sample_rate_hz || !request.period_frames || request.period_frames > 65536 || !request.channels || request.channels > 64 ||
#ifdef _WIN32
        request.allow_rate_conversion || request.allow_period_adaptation || request.allow_channel_conversion || request.allow_format_conversion ||
#endif
        fence.selection().kind != DeviceKind::Audio ||
        (self.direction == AudioDirection::Playback ? !fence.selection().require_output : !fence.selection().require_input) ||
        (self.fence_owner && self.fence_owner != &fence)) return false;
    AudioPreflightDecision plan{}; plan.status = AudioPreflightStatus::Exact;
    plan.configured_sample_rate_hz = request.sample_rate_hz; plan.configured_period_frames = request.period_frames;
    plan.configured_channels = request.channels; plan.configured_format = request.format;
    if (!self.lifecycle.prepare(plan, fence.observation())) return false;
    try {
        self.release_native(); self.request = request; self.selection = fence.selection(); self.fence_owner = &fence;
        self.fault.store(false); self.open_native(); return true;
    } catch (...) { self.lifecycle.close(); self.release_native(); throw; }
}
bool NativeEndpointStream::start(const DeviceExecutionFence& fence) {
    auto& self = *impl_; self.check_thread();
    if (!self.opened || !self.matches(fence) || self.running) return false;
    try {
        self.validate_native();
        if (endpoint_epoch.load() != self.prepared_epoch || self.fault.load()) { self.revoke(fence.observation()); return false; }
        if (!self.lifecycle.start(fence.observation())) return false;
        self.allowed.store(true);
#ifdef _WIN32
        // Prime with silence. Never leave an initial endpoint buffer uninitialized.
        if (self.direction == AudioDirection::Playback) {
            BYTE* data = nullptr; checked(self.output->GetBuffer(self.buffer_frames, &data), "prime WASAPI buffer");
            checked(self.output->ReleaseBuffer(self.buffer_frames, AUDCLNT_BUFFERFLAGS_SILENT), "prime WASAPI silence");
        }
        checked(self.client->Start(), "start WASAPI");
#else
        self.previous_timestamp = false;
        checked(AudioOutputUnitStart(self.unit), "start AUHAL");
#endif
        self.running = true; return true;
    } catch (...) { self.revoke(fence.observation()); throw; }
}
void NativeEndpointStream::service(const DeviceExecutionFence& fence, std::uint32_t wait_ms) {
    auto& self = *impl_; self.check_thread();
    if (wait_ms > 100) throw std::invalid_argument("playback service wait exceeds 100ms");
    if (!self.running) return;
    auto observation = self.lifecycle.reconcile(fence.observation());
    if (!self.matches(fence) || !observation.callback_execution_allowed ||
        endpoint_epoch.load() != self.prepared_epoch || self.fault.load()) { self.revoke(fence.observation()); return; }
    try {
#ifdef _WIN32
        auto status = WaitForSingleObject(self.event, wait_ms);
        if (status == WAIT_TIMEOUT) return;
        if (status != WAIT_OBJECT_0) throw std::runtime_error("WASAPI event wait failed");
        if (endpoint_epoch.load() != self.prepared_epoch) { self.revoke(fence.observation()); return; }
        self.validate_native();
        if (self.direction == AudioDirection::Playback) {
            UINT32 padding = 0; checked(self.client->GetCurrentPadding(&padding), "WASAPI padding");
            if (padding > self.buffer_frames) throw std::runtime_error("invalid WASAPI padding");
            const UINT32 count = self.buffer_frames - padding;
            if (count) {
                BYTE* data = nullptr; checked(self.output->GetBuffer(count, &data), "WASAPI render buffer");
                const bool rendered = self.dispatch(reinterpret_cast<float*>(data), count);
                checked(self.output->ReleaseBuffer(count, rendered ? 0 : AUDCLNT_BUFFERFLAGS_SILENT), "WASAPI submit buffer");
            }
        } else {
            // Bound one service pass even if the producer remains continuously active.
            for (unsigned packet = 0; packet < 64 && endpoint_epoch.load() == self.prepared_epoch; ++packet) {
                UINT32 pending = 0; checked(self.input->GetNextPacketSize(&pending), "capture packet size");
                if (!pending) break;
                BYTE* data = nullptr; UINT32 count = 0; DWORD flags = 0; UINT64 position = 0;
                auto status = self.input->GetBuffer(&data, &count, &flags, &position, nullptr);
                checked(status, "capture packet");
                if (status == AUDCLNT_S_BUFFER_EMPTY || !count) break;
                if (count > self.buffer_frames || (!data && !(flags & AUDCLNT_BUFFERFLAGS_SILENT))) {
                    checked(self.input->ReleaseBuffer(count), "release invalid capture packet");
                    throw std::runtime_error("invalid capture buffer");
                }
                CapturePacketInfo info{(flags & AUDCLNT_BUFFERFLAGS_DATA_DISCONTINUITY) != 0,
                    (flags & AUDCLNT_BUFFERFLAGS_TIMESTAMP_ERROR) == 0, static_cast<double>(position)};
                self.deliver(flags & AUDCLNT_BUFFERFLAGS_SILENT ? self.capture_buffer.data() : reinterpret_cast<const float*>(data), count, info);
                checked(self.input->ReleaseBuffer(count), "release capture packet");
            }
        }
#else
        self.validate_native();
        if (wait_ms) std::this_thread::sleep_for(std::chrono::milliseconds(wait_ms));
#endif
        if (endpoint_epoch.load() != self.prepared_epoch || self.fault.load()) self.revoke(fence.observation());
    } catch (...) { self.revoke(fence.observation()); throw; }
}
void NativeEndpointStream::close() {
    auto& self = *impl_; self.check_thread(); self.allowed.store(false);
    self.lifecycle.close(); self.release_native(); self.lifecycle.mark_stopped();
}
EndpointStreamStats NativeEndpointStream::stats() const {
    auto& self = *impl_; self.check_thread();
    return {self.callbacks.load(), self.frames.load(), self.running, self.fault.load(), self.lifecycle.observation(), self.verified, self.discontinuities.load()};
}
}
