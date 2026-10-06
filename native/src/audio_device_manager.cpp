#include "stagemesh/audio_device_manager.hpp"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#if defined(__linux__)
#include <dlfcn.h>
#elif defined(_WIN32) || defined(__APPLE__)
#include "device_monitor.h"
#endif

namespace stagemesh {

namespace {

template <std::size_t N>
void copy_text(std::array<char, N>& target, std::string_view source) noexcept {
    const auto size = std::min(source.size(), N - 1);
    std::memcpy(target.data(), source.data(), size);
    target[size] = '\0';
}

std::uint32_t fnv1a(std::string_view text) noexcept {
    std::uint32_t hash = 2166136261u;
    for (unsigned char ch : text) {
        hash ^= ch;
        hash *= 16777619u;
    }
    return hash;
}

std::string clean_description(std::string value) {
    std::replace(value.begin(), value.end(), '\n', ' ');
    std::replace(value.begin(), value.end(), '\r', ' ');
    while (value.find("  ") != std::string::npos) {
        value.replace(value.find("  "), 2, " ");
    }
    return value;
}

#if defined(_WIN32) || defined(__APPLE__)
std::string identity_token(const DeviceRecord& record) {
    // This value is returned through the legacy engine "address" field. Both
    // native/persistent values are already one-way SHA-256 tokens. Never place
    // a raw MMDevice ID, CoreAudio UID or other OS identifier in this channel.
    return std::string("native=") + record.native_hash +
        ";persistent=" + record.persistent_hash +
        ";strength=" + identity_strength_name(record.identity_strength) +
        ";auto=" + (record.automatic_reconnect ? "1" : "0");
}
#endif

} // namespace

void AudioDeviceManager::add_null() noexcept {
    add_endpoint("StageMesh Null Audio Device", "null", "null", false, true);
}

void AudioDeviceManager::add_endpoint(
    std::string_view name,
    std::string_view address,
    std::string_view backend,
    bool input,
    bool output) noexcept {
    if (count_ >= devices_.size() || address.empty()) {
        return;
    }
    for (std::size_t index = 0; index < count_; ++index) {
        if (std::string_view(devices_[index].backend_address.data()) == address &&
            std::string_view(devices_[index].backend.data()) == backend) {
            return;
        }
    }

    auto& descriptor = devices_[count_++];
    descriptor = {};
    char id[64]{};
    if (backend == "null") {
        std::snprintf(id, sizeof(id), "null-audio");
    } else {
        std::snprintf(id, sizeof(id), "%.*s-%08x", static_cast<int>(std::min<std::size_t>(backend.size(), 20)), backend.data(), fnv1a(address));
    }
    copy_text(descriptor.id, id);
    copy_text(descriptor.name, name.empty() ? address : name);
    copy_text(descriptor.backend_address, address);
    copy_text(descriptor.backend, backend);
    descriptor.input = input;
    descriptor.output = output;
    descriptor.connected = true;
}

std::size_t AudioDeviceManager::scan() noexcept {
    count_ = 0;
    add_null();
    scan_platform();
    return count_;
}

const AudioEndpointDescriptor* AudioDeviceManager::device(std::size_t index) const noexcept {
    return index < count_ ? &devices_[index] : nullptr;
}

const AudioEndpointDescriptor* AudioDeviceManager::find(std::string_view id) const noexcept {
    for (std::size_t index = 0; index < count_; ++index) {
        if (std::string_view(devices_[index].id.data()) == id) {
            return &devices_[index];
        }
    }
    return nullptr;
}

void AudioDeviceManager::scan_platform() noexcept {
#if defined(__linux__)
    using hint_fn = int (*)(int, const char*, void***);
    using get_hint_fn = char* (*)(const void*, const char*);
    using free_hint_fn = int (*)(void**);

    void* library = dlopen("libasound.so.2", RTLD_LAZY | RTLD_LOCAL);
    if (!library) {
        return;
    }
    const auto device_name_hint = reinterpret_cast<hint_fn>(dlsym(library, "snd_device_name_hint"));
    const auto device_name_get_hint = reinterpret_cast<get_hint_fn>(dlsym(library, "snd_device_name_get_hint"));
    const auto device_name_free_hint = reinterpret_cast<free_hint_fn>(dlsym(library, "snd_device_name_free_hint"));
    if (!device_name_hint || !device_name_get_hint || !device_name_free_hint) {
        dlclose(library);
        return;
    }

    void** hints = nullptr;
    if (device_name_hint(-1, "pcm", &hints) < 0 || !hints) {
        dlclose(library);
        return;
    }

    for (void** item = hints; *item && count_ < devices_.size(); ++item) {
        char* raw_name = device_name_get_hint(*item, "NAME");
        char* raw_desc = device_name_get_hint(*item, "DESC");
        char* raw_io = device_name_get_hint(*item, "IOID");
        if (raw_name) {
            const std::string address(raw_name);
            const std::string description = raw_desc ? clean_description(raw_desc) : address;
            const std::string io = raw_io ? raw_io : "";
            const bool input = io.empty() || io == "Input";
            const bool output = io.empty() || io == "Output";
            add_endpoint(description, address, "alsa", input, output);
        }
        std::free(raw_name);
        std::free(raw_desc);
        std::free(raw_io);
    }

    device_name_free_hint(hints);
    dlclose(library);
#elif defined(_WIN32) || defined(__APPLE__)
    try {
        DeviceMonitor monitor;
        monitor.start();
        const auto snapshot = monitor.snapshot();
        monitor.stop();
        const std::string_view backend =
#if defined(_WIN32)
            "wasapi";
#else
            "coreaudio";
#endif
        for (const auto& record : snapshot.devices) {
            if (record.kind != DeviceKind::Audio || count_ >= devices_.size()) continue;
            add_endpoint(
#if defined(_WIN32)
                "Windows Audio Endpoint",
#else
                "CoreAudio Endpoint",
#endif
                identity_token(record), backend, record.input, record.output);
        }
    } catch (...) {
        // Discovery remains observation-only and non-fatal. The engine keeps the
        // null endpoint when the target-OS topology changes during this snapshot.
        return;
    }
#endif
}

} // namespace stagemesh
