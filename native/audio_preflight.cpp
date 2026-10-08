#include "audio_preflight.h"
#include "device_identity.h"
#include "device_monitor.h"
#include "stagemesh/windows_hresult.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <audioclient.h>
#include <mmdeviceapi.h>
#include <mmreg.h>
#include <ks.h>
#include <ksmedia.h>
#include <wrl/client.h>
#else
#include <CoreAudio/CoreAudio.h>
#include <CoreFoundation/CoreFoundation.h>
#include <vector>
#endif

namespace stagemesh {
namespace {

bool supported_rate(const AudioHostCapabilities& capabilities, std::uint32_t rate) {
    if (!capabilities.supported_sample_rates.empty()) {
        const double value = static_cast<double>(rate);
        for (const auto& range : capabilities.supported_sample_rates) {
            if (value >= range.minimum_hz && value <= range.maximum_hz) return true;
        }
        return false;
    }
    return capabilities.native_sample_rate_hz == rate;
}

std::uint32_t directional_channels(const AudioRequest& request, const AudioHostCapabilities& capabilities) {
    return request.direction == AudioDirection::Playback ? capabilities.output_channels : capabilities.input_channels;
}

bool supported_period(const AudioHostCapabilities& capabilities, std::uint32_t period) {
    if (capabilities.minimum_period_frames && capabilities.maximum_period_frames) {
        return period >= capabilities.minimum_period_frames && period <= capabilities.maximum_period_frames;
    }
    return capabilities.default_period_frames != 0 && period == capabilities.default_period_frames;
}

#ifdef _WIN32
void checked(HRESULT status, const char* operation) {
    if (FAILED(status))
        throw std::runtime_error(std::string(operation) + ": " +
            format_windows_hresult(static_cast<std::int32_t>(status)));
}

struct ComApartment {
    ComApartment() { checked(CoInitializeEx(nullptr, COINIT_MULTITHREADED), "CoInitializeEx"); }
    ~ComApartment() { CoUninitialize(); }
    ComApartment(const ComApartment&) = delete;
    ComApartment& operator=(const ComApartment&) = delete;
};

std::string utf8(LPCWSTR text) {
    if (!text || !*text) return {};
    const int required = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, -1, nullptr, 0, nullptr, nullptr);
    if (required <= 1) throw std::runtime_error("WideCharToMultiByte size failed");
    std::string result(static_cast<std::size_t>(required), '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, -1, result.data(), required, nullptr, nullptr))
        throw std::runtime_error("WideCharToMultiByte failed");
    if (!result.empty() && result.back() == '\0') result.pop_back();
    return result;
}

std::uint32_t period_frames(REFERENCE_TIME period, std::uint32_t sample_rate) {
    if (period <= 0 || sample_rate == 0) return 0;
    const double frames = static_cast<double>(period) * static_cast<double>(sample_rate) / 10000000.0;
    return static_cast<std::uint32_t>(std::max(1.0, std::round(frames)));
}

AudioSampleFormat wave_format(const WAVEFORMATEX* wave) {
    if (!wave) return AudioSampleFormat::Unknown;
    WORD tag = wave->wFormatTag;
    if (tag == WAVE_FORMAT_EXTENSIBLE && wave->cbSize >= sizeof(WAVEFORMATEXTENSIBLE) - sizeof(WAVEFORMATEX)) {
        const auto* extensible = reinterpret_cast<const WAVEFORMATEXTENSIBLE*>(wave);
        if (IsEqualGUID(extensible->SubFormat, KSDATAFORMAT_SUBTYPE_IEEE_FLOAT)) tag = WAVE_FORMAT_IEEE_FLOAT;
        else if (IsEqualGUID(extensible->SubFormat, KSDATAFORMAT_SUBTYPE_PCM)) tag = WAVE_FORMAT_PCM;
    }
    if (tag == WAVE_FORMAT_IEEE_FLOAT && wave->wBitsPerSample == 32) return AudioSampleFormat::Float32;
    if (tag == WAVE_FORMAT_PCM) {
        if (wave->wBitsPerSample == 16) return AudioSampleFormat::Int16;
        if (wave->wBitsPerSample == 24) return AudioSampleFormat::Int24Packed;
        if (wave->wBitsPerSample == 32) return AudioSampleFormat::Int32;
    }
    return AudioSampleFormat::Unknown;
}

#else
void checked(OSStatus status, const char* operation) {
    if (status != noErr) throw std::runtime_error(std::string(operation) + ": " + std::to_string(status));
}

std::string cf_string(CFStringRef value) {
    if (!value) return {};
    const auto length = CFStringGetLength(value);
    const auto maximum = CFStringGetMaximumSizeForEncoding(length, kCFStringEncodingUTF8) + 1;
    std::vector<char> buffer(static_cast<std::size_t>(maximum));
    if (!CFStringGetCString(value, buffer.data(), maximum, kCFStringEncodingUTF8))
        throw std::runtime_error("CFString UTF-8 conversion failed");
    return std::string(buffer.data());
}

std::uint32_t channel_count(AudioDeviceID device, AudioObjectPropertyScope scope) {
    AudioObjectPropertyAddress address{kAudioDevicePropertyStreamConfiguration, scope, kAudioObjectPropertyElementMain};
    UInt32 size = 0;
    if (AudioObjectGetPropertyDataSize(device, &address, 0, nullptr, &size) != noErr || !size) return 0;
    std::vector<std::uint8_t> storage(size);
    if (AudioObjectGetPropertyData(device, &address, 0, nullptr, &size, storage.data()) != noErr) return 0;
    const auto* list = reinterpret_cast<const AudioBufferList*>(storage.data());
    std::uint32_t channels = 0;
    for (UInt32 index = 0; index < list->mNumberBuffers; ++index) channels += list->mBuffers[index].mNumberChannels;
    return channels;
}
#endif

}

AudioPreflightDecision evaluate_audio_preflight(const AudioRequest& request, const AudioHostCapabilities& capabilities) {
    AudioPreflightDecision result{};
    if (!request.sample_rate_hz || !request.period_frames || !request.channels || request.format == AudioSampleFormat::Unknown) {
        result.status = AudioPreflightStatus::Unsupported;
        result.reason = "invalid-request";
        return result;
    }
    if (!capabilities.endpoint_present) {
        result.status = AudioPreflightStatus::NoEndpoint;
        result.reason = "no-endpoint";
        return result;
    }

    result.configured_sample_rate_hz = request.sample_rate_hz;
    result.configured_period_frames = request.period_frames;
    result.configured_channels = request.channels;
    result.configured_format = request.format;

    if (!supported_rate(capabilities, request.sample_rate_hz)) {
        if (!request.allow_rate_conversion || !capabilities.native_sample_rate_hz) {
            result.status = AudioPreflightStatus::Unsupported;
            result.reason = "sample-rate-unsupported";
            return result;
        }
        result.rate_conversion = true;
        result.configured_sample_rate_hz = capabilities.native_sample_rate_hz;
    }

    if (!supported_period(capabilities, request.period_frames)) {
        if (!request.allow_period_adaptation || !capabilities.default_period_frames) {
            result.status = AudioPreflightStatus::Unsupported;
            result.reason = "period-unsupported";
            return result;
        }
        result.period_adaptation = true;
        result.configured_period_frames = capabilities.default_period_frames;
    }

    const auto channels = directional_channels(request, capabilities);
    if (!channels) {
        result.status = AudioPreflightStatus::Unsupported;
        result.reason = "direction-unavailable";
        return result;
    }
    if (request.channels != channels) {
        if (!request.allow_channel_conversion) {
            result.status = AudioPreflightStatus::Unsupported;
            result.reason = "channels-unsupported";
            return result;
        }
        result.channel_conversion = true;
        result.configured_channels = channels;
    }

    if (request.format != capabilities.client_format) {
        if (!request.allow_format_conversion || capabilities.client_format == AudioSampleFormat::Unknown) {
            result.status = AudioPreflightStatus::Unsupported;
            result.reason = "format-unsupported";
            return result;
        }
        result.format_conversion = true;
        result.configured_format = capabilities.client_format;
    }

    const bool adapted = result.rate_conversion || result.period_adaptation || result.channel_conversion || result.format_conversion;
    result.status = adapted ? AudioPreflightStatus::ExplicitAdaptation : AudioPreflightStatus::Exact;
    result.reason = adapted ? "explicit-adaptation" : "exact";
    return result;
}

static AudioHostCapabilities probe_native_audio_endpoint(AudioDirection direction, const DeviceSelection* selection) {
    AudioHostCapabilities result{};
#ifdef _WIN32
    result.backend = "wasapi";
    ComApartment apartment;
    Microsoft::WRL::ComPtr<IMMDeviceEnumerator> enumerator;
    checked(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
        IID_PPV_ARGS(enumerator.GetAddressOf())), "MMDeviceEnumerator");
    Microsoft::WRL::ComPtr<IMMDevice> endpoint;
    const auto flow = direction == AudioDirection::Playback ? eRender : eCapture;
    if (selection) {
        Microsoft::WRL::ComPtr<IMMDeviceCollection> devices;
        checked(enumerator->EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE, devices.GetAddressOf()), "enumerate pinned endpoints");
        UINT count = 0; checked(devices->GetCount(&count), "pinned endpoint count");
        for (UINT i = 0; i < count; ++i) {
            Microsoft::WRL::ComPtr<IMMDevice> candidate;
            checked(devices->Item(i, candidate.GetAddressOf()), "pinned endpoint item");
            LPWSTR raw = nullptr; checked(candidate->GetId(&raw), "pinned endpoint ID");
            std::string hash;
            try { hash = sha256_token("wasapi-native:" + utf8(raw)); }
            catch (...) { CoTaskMemFree(raw); throw; }
            CoTaskMemFree(raw);
            if (hash == selection->native_hash) {
                if (endpoint) return result;
                endpoint = candidate;
            }
        }
        if (!endpoint) return result;
    } else {
        const HRESULT selected = enumerator->GetDefaultAudioEndpoint(flow, eConsole, endpoint.GetAddressOf());
        if (selected == HRESULT_FROM_WIN32(ERROR_NOT_FOUND)) return result;
        checked(selected, "GetDefaultAudioEndpoint");
    }
    result.endpoint_present = true;

    LPWSTR raw_id = nullptr;
    checked(endpoint->GetId(&raw_id), "endpoint id");
    try { result.endpoint_identity_hash = sha256_token("wasapi-native:" + utf8(raw_id)); }
    catch (...) { CoTaskMemFree(raw_id); throw; }
    CoTaskMemFree(raw_id);
    result.endpoint_identity_strong = false;

    Microsoft::WRL::ComPtr<IAudioClient> client;
    checked(endpoint->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
        reinterpret_cast<void**>(client.GetAddressOf())), "activate IAudioClient");
    WAVEFORMATEX* mix = nullptr;
    checked(client->GetMixFormat(&mix), "GetMixFormat");
    try {
        result.native_sample_rate_hz = mix->nSamplesPerSec;
        result.input_channels = direction == AudioDirection::Capture ? mix->nChannels : 0;
        result.output_channels = direction == AudioDirection::Playback ? mix->nChannels : 0;
        result.client_format = wave_format(mix);
        result.supported_sample_rates.push_back({static_cast<double>(mix->nSamplesPerSec), static_cast<double>(mix->nSamplesPerSec)});
    } catch (...) { CoTaskMemFree(mix); throw; }
    CoTaskMemFree(mix);

    REFERENCE_TIME default_period = 0;
    REFERENCE_TIME minimum_period = 0;
    checked(client->GetDevicePeriod(&default_period, &minimum_period), "GetDevicePeriod");
    result.default_period_frames = period_frames(default_period, result.native_sample_rate_hz);
    result.minimum_period_frames = result.default_period_frames;
    result.maximum_period_frames = result.default_period_frames;
    (void)minimum_period;
    return result;
#else
    result.backend = "coreaudio";
    AudioObjectPropertyAddress default_address{
        direction == AudioDirection::Playback ? kAudioHardwarePropertyDefaultOutputDevice : kAudioHardwarePropertyDefaultInputDevice,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain
    };
    AudioDeviceID device = kAudioObjectUnknown;
    UInt32 size = sizeof(device);
    if (selection) {
        AudioObjectPropertyAddress list_address{kAudioHardwarePropertyDevices, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
        UInt32 bytes = 0;
        checked(AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &list_address, 0, nullptr, &bytes), "pinned device list size");
        if (bytes % sizeof(AudioDeviceID)) throw std::runtime_error("invalid pinned device list size");
        std::vector<AudioDeviceID> devices(bytes / sizeof(AudioDeviceID));
        const auto capacity = bytes;
        if (bytes) checked(AudioObjectGetPropertyData(kAudioObjectSystemObject, &list_address, 0, nullptr, &bytes, devices.data()), "pinned device list");
        if (bytes > capacity || bytes % sizeof(AudioDeviceID)) throw std::runtime_error("pinned device list changed size");
        devices.resize(bytes / sizeof(AudioDeviceID));
        for (auto candidate : devices) if (sha256_token("coreaudio-native:" + std::to_string(candidate)) == selection->native_hash) {
            if (device != kAudioObjectUnknown) return result;
            device = candidate;
        }
    } else {
        checked(AudioObjectGetPropertyData(kAudioObjectSystemObject, &default_address, 0, nullptr, &size, &device),
            "default CoreAudio device");
    }
    if (device == kAudioObjectUnknown) return result;
    result.endpoint_present = true;

    AudioObjectPropertyAddress uid_address{kAudioDevicePropertyDeviceUID, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    CFStringRef uid = nullptr;
    size = sizeof(uid);
    if (AudioObjectGetPropertyData(device, &uid_address, 0, nullptr, &size, &uid) == noErr && uid) {
        const auto text = cf_string(uid);
        CFRelease(uid);
        if (!text.empty()) {
            result.endpoint_identity_hash = sha256_token("coreaudio-uid:" + text);
            result.endpoint_identity_strong = true;
        }
    }

    AudioObjectPropertyAddress rate_address{kAudioDevicePropertyNominalSampleRate, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    Float64 rate = 0.0;
    size = sizeof(rate);
    checked(AudioObjectGetPropertyData(device, &rate_address, 0, nullptr, &size, &rate), "CoreAudio nominal sample rate");
    result.native_sample_rate_hz = static_cast<std::uint32_t>(std::llround(rate));

    AudioObjectPropertyAddress rate_ranges_address{kAudioDevicePropertyAvailableNominalSampleRates, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    UInt32 ranges_size = 0;
    if (AudioObjectGetPropertyDataSize(device, &rate_ranges_address, 0, nullptr, &ranges_size) == noErr && ranges_size) {
        std::vector<AudioValueRange> ranges(ranges_size / sizeof(AudioValueRange));
        if (AudioObjectGetPropertyData(device, &rate_ranges_address, 0, nullptr, &ranges_size, ranges.data()) == noErr) {
            for (const auto& range_value : ranges) result.supported_sample_rates.push_back({range_value.mMinimum, range_value.mMaximum});
        }
    }
    if (result.supported_sample_rates.empty() && result.native_sample_rate_hz)
        result.supported_sample_rates.push_back({static_cast<double>(result.native_sample_rate_hz), static_cast<double>(result.native_sample_rate_hz)});

    AudioObjectPropertyAddress buffer_address{kAudioDevicePropertyBufferFrameSize, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    UInt32 buffer = 0;
    size = sizeof(buffer);
    checked(AudioObjectGetPropertyData(device, &buffer_address, 0, nullptr, &size, &buffer), "CoreAudio buffer frame size");
    result.default_period_frames = buffer;

    AudioObjectPropertyAddress buffer_range_address{kAudioDevicePropertyBufferFrameSizeRange, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain};
    AudioValueRange buffer_range{};
    size = sizeof(buffer_range);
    if (AudioObjectGetPropertyData(device, &buffer_range_address, 0, nullptr, &size, &buffer_range) == noErr) {
        result.minimum_period_frames = static_cast<std::uint32_t>(std::llround(buffer_range.mMinimum));
        result.maximum_period_frames = static_cast<std::uint32_t>(std::llround(buffer_range.mMaximum));
    } else {
        result.minimum_period_frames = buffer;
        result.maximum_period_frames = buffer;
    }

    result.input_channels = channel_count(device, kAudioObjectPropertyScopeInput);
    result.output_channels = channel_count(device, kAudioObjectPropertyScopeOutput);
    result.client_format = AudioSampleFormat::Float32;
    return result;
#endif
}

AudioHostCapabilities probe_default_audio_endpoint(AudioDirection direction) {
    return probe_native_audio_endpoint(direction, nullptr);
}

AudioHostCapabilities probe_audio_endpoint(const DeviceSelection& selection, AudioDirection direction) {
    AudioHostCapabilities absent{};
#ifdef _WIN32
    absent.backend = "wasapi";
#else
    absent.backend = "coreaudio";
#endif
    if (selection.kind != DeviceKind::Audio ||
        (direction != AudioDirection::Playback && direction != AudioDirection::Capture)) return absent;
    auto directional = selection;
    if (direction == AudioDirection::Playback) directional.require_output = true;
    else directional.require_input = true;
    DeviceMonitor monitor; monitor.start();
    const auto revision = monitor.revision();
    if (resolve_device(directional, monitor.snapshot().devices).status != ResolutionStatus::Attached) return absent;
    auto result = probe_native_audio_endpoint(direction, &directional);
#ifdef _WIN32
    if (result.endpoint_identity_hash != directional.native_hash) return absent;
#else
    if (result.endpoint_identity_hash != directional.persistent_hash) return absent;
#endif
    if (!result.endpoint_present ||
        resolve_device(directional, monitor.snapshot().devices).status != ResolutionStatus::Attached ||
        monitor.revision() != revision) return absent;
    return result;
}

const char* audio_direction_name(AudioDirection value) {
    return value == AudioDirection::Playback ? "playback" : "capture";
}

const char* audio_sample_format_name(AudioSampleFormat value) {
    switch (value) {
        case AudioSampleFormat::Float32: return "float32";
        case AudioSampleFormat::Int16: return "int16";
        case AudioSampleFormat::Int24Packed: return "int24-packed";
        case AudioSampleFormat::Int32: return "int32";
        default: return "unknown";
    }
}

const char* audio_preflight_status_name(AudioPreflightStatus value) {
    switch (value) {
        case AudioPreflightStatus::Exact: return "exact";
        case AudioPreflightStatus::ExplicitAdaptation: return "explicit-adaptation";
        case AudioPreflightStatus::NoEndpoint: return "no-endpoint";
        default: return "unsupported";
    }
}

}
