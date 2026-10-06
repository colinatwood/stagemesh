#include "stagemesh/midi_input.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <string>

#if defined(__linux__)
#include <dirent.h>
#include <fcntl.h>
#include <unistd.h>
#elif defined(_WIN32) || defined(__APPLE__)
#include "device_monitor.h"
#if defined(__APPLE__)
#include <CoreMIDI/CoreMIDI.h>
#include <mach/mach_time.h>
#endif
#if defined(_WIN32)
#include <windows.h>
#include <mmsystem.h>
#endif
#endif

namespace stagemesh {
namespace {

template <std::size_t N>
void copy_text(std::array<char, N>& target, std::string_view source) noexcept {
    const auto count = std::min(source.size(), N - 1);
    if (count > 0) {
        std::memcpy(target.data(), source.data(), count);
    }
    target[count] = '\0';
}

bool same_text(const auto& buffer, std::string_view value) noexcept {
    return std::string_view(buffer.data()) == value;
}

#if defined(__linux__)
bool parse_linux_raw_midi_name(const char* name, unsigned int& card, unsigned int& device) noexcept {
    if (std::strncmp(name, "midiC", 5) != 0) {
        return false;
    }
    char tail = '\0';
    return std::sscanf(name, "midiC%uD%u%c", &card, &device, &tail) == 2;
}
#elif defined(_WIN32) || defined(__APPLE__)
std::string target_midi_id(const DeviceRecord& record, std::string_view backend) {
    std::string digest = record.native_hash;
    constexpr std::string_view prefix{"sha256:"};
    if (digest.rfind(prefix, 0) == 0) digest.erase(0, prefix.size());
    if (digest.size() > 40) digest.resize(40);
    return std::string(backend) + "-" + digest;
}

std::string target_midi_identity(const DeviceRecord& record, std::string_view backend) {
    // Raw CoreMIDI objects, WinMM interface names and PnP IDs must not cross
    // the engine boundary. DeviceMonitor has already reduced them to one-way
    // SHA-256 evidence before this legacy descriptor is populated.
    return std::string("backend=") + std::string(backend) +
        ";native=" + record.native_hash +
        ";persistent=" + record.persistent_hash +
        ";strength=" + identity_strength_name(record.identity_strength) +
        ";auto=" + (record.automatic_reconnect ? "1" : "0");
}
#endif

#if defined(__APPLE__)
void coremidi_read(const MIDIPacketList* packets, void*, void* source_refcon) {
    // The slot is supplied as the connection refcon by MIDIPortConnectSource.
    // The port-level refcon is intentionally unused because one shared input
    // port may service multiple CoreMIDI sources.
    auto* slot = static_cast<MidiInputManager::DeviceSlot*>(source_refcon);
    if (!slot || !slot->owner) return;
    auto timestamp = static_cast<std::uint64_t>(mach_absolute_time());
    const MIDIPacket* packet = &packets->packet[0];
    for (UInt32 packet_index = 0; packet_index < packets->numPackets; ++packet_index) {
        MidiByteParser parser = slot->parser;
        for (UInt16 byte_index = 0; byte_index < packet->length; ++byte_index) {
            MidiInputMessage message{};
            if (!parser.feed(packet->data[byte_index], timestamp, message)) continue;
            (void)slot->owner->capture_callback(slot->descriptor.id.data(), slot->player_id.data(), message);
        }
        slot->parser = parser;
        packet = MIDIPacketNext(packet);
    }
}
#endif

#if defined(_WIN32)
void CALLBACK winmm_read(HMIDIIN, UINT message, DWORD_PTR instance, DWORD_PTR packed, DWORD_PTR timestamp) {
    if (message != MIM_DATA) return;
    auto* slot = reinterpret_cast<MidiInputManager::DeviceSlot*>(instance);
    if (!slot || !slot->owner) return;
    MidiInputMessage parsed{static_cast<std::uint64_t>(timestamp),
        static_cast<std::uint8_t>(packed & 0xffu),
        static_cast<std::uint8_t>((packed >> 8) & 0x7fu),
        static_cast<std::uint8_t>((packed >> 16) & 0x7fu)};
    if ((parsed.status & 0x80u) != 0u && (parsed.status & 0xf0u) != 0xf0u)
        slot->owner->capture_callback(slot->descriptor.id.data(), slot->player_id.data(), parsed);
}
#endif

} // namespace

std::uint8_t MidiByteParser::data_length(std::uint8_t status) noexcept {
    const auto high = static_cast<std::uint8_t>(status & 0xF0U);
    if (high >= 0x80U && high <= 0xE0U) {
        return (high == 0xC0U || high == 0xD0U) ? 1U : 2U;
    }
    switch (status) {
        case 0xF1U: return 1U;
        case 0xF2U: return 2U;
        case 0xF3U: return 1U;
        default: return 0U;
    }
}

void MidiByteParser::reset() noexcept {
    running_status_ = 0;
    message_status_ = 0;
    expected_ = 0;
    received_ = 0;
    in_sysex_ = false;
}

bool MidiByteParser::feed(std::uint8_t byte, std::uint64_t show_time_ns, MidiInputMessage& out) noexcept {
    // MIDI realtime messages may appear anywhere and do not disturb running
    // status. They are not emitted through this channel-voice parser.
    if (byte >= 0xF8U) {
        return false;
    }

    if (in_sysex_) {
        if (byte == 0xF7U) {
            in_sysex_ = false;
        }
        return false;
    }

    if ((byte & 0x80U) != 0U) {
        received_ = 0;
        message_status_ = byte;
        expected_ = data_length(byte);
        if (byte == 0xF0U) {
            in_sysex_ = true;
            running_status_ = 0;
            expected_ = 0;
            return false;
        }
        if (byte < 0xF0U) {
            running_status_ = byte;
        } else {
            running_status_ = 0;
        }
        return false;
    }

    if (expected_ == 0) {
        if (running_status_ == 0) {
            return false;
        }
        message_status_ = running_status_;
        expected_ = data_length(message_status_);
        received_ = 0;
    }

    if (received_ < data_.size()) {
        data_[received_] = static_cast<std::uint8_t>(byte & 0x7FU);
    }
    ++received_;
    if (received_ < expected_) {
        return false;
    }

    const auto status = message_status_;
    const auto channel_voice = status < 0xF0U;
    out = MidiInputMessage{
        show_time_ns,
        status,
        data_[0],
        expected_ > 1 ? data_[1] : static_cast<std::uint8_t>(0),
    };

    received_ = 0;
    if (channel_voice && running_status_ != 0) {
        message_status_ = running_status_;
        expected_ = data_length(running_status_);
    } else {
        message_status_ = 0;
        expected_ = 0;
    }
    return channel_voice;
}

MidiInputManager::MidiInputManager() noexcept = default;

MidiInputManager::~MidiInputManager() {
    deactivate();
}

void MidiInputManager::deactivate() noexcept {
    for (std::size_t i = 0; i < device_count_; ++i) close_slot(devices_[i]);
    device_count_ = 0;
#if defined(__APPLE__)
    if (native_port_) { MIDIPortDispose(static_cast<MIDIPortRef>(native_port_)); native_port_ = 0; }
    if (native_client_) { MIDIClientDispose(static_cast<MIDIClientRef>(native_client_)); native_client_ = 0; }
#endif
}

const MidiDeviceDescriptor* MidiInputManager::device(std::size_t index) const noexcept {
    return index < device_count_ ? &devices_[index].descriptor : nullptr;
}

MidiInputManager::DeviceSlot* MidiInputManager::find_slot(std::string_view device_id) noexcept {
    for (std::size_t i = 0; i < device_count_; ++i) {
        if (same_text(devices_[i].descriptor.id, device_id)) {
            return &devices_[i];
        }
    }
    return nullptr;
}

const MidiInputManager::DeviceSlot* MidiInputManager::find_slot(std::string_view device_id) const noexcept {
    for (std::size_t i = 0; i < device_count_; ++i) {
        if (same_text(devices_[i].descriptor.id, device_id)) {
            return &devices_[i];
        }
    }
    return nullptr;
}

bool MidiInputManager::attached(std::string_view device_id) const noexcept {
    const auto* slot = find_slot(device_id);
    return slot != nullptr && slot->attached;
}

void MidiInputManager::close_slot(DeviceSlot& slot) noexcept {
#if defined(__APPLE__)
    if (slot.native_source && native_port_) {
        MIDIPortDisconnectSource(static_cast<MIDIPortRef>(native_port_), static_cast<MIDIEndpointRef>(slot.native_source));
    }
#endif
#if defined(_WIN32)
    if (slot.native_source) {
        const auto handle = reinterpret_cast<HMIDIIN>(slot.native_source);
        midiInStop(handle); midiInReset(handle); midiInClose(handle);
    }
#endif
#if defined(__linux__)
    if (slot.handle >= 0) {
        ::close(slot.handle);
    }
#endif
    slot.handle = -1;
    slot.native_source = 0;
    slot.attached = false;
    slot.player_id[0] = '\0';
    slot.parser.reset();
}

std::size_t MidiInputManager::scan() noexcept {
    // Preserve active attachments across scans by copying matching slots into a
    // fresh fixed registry. This lets hot-plug rescans avoid invalidating an
    // unchanged open endpoint.
    std::array<DeviceSlot, max_devices> found{};
    std::size_t found_count = 0;

#if defined(__linux__)
    DIR* directory = ::opendir("/dev/snd");
    if (directory != nullptr) {
        while (auto* entry = ::readdir(directory)) {
            if (found_count >= max_devices) {
                break;
            }
            unsigned int card = 0;
            unsigned int device_number = 0;
            if (!parse_linux_raw_midi_name(entry->d_name, card, device_number)) {
                continue;
            }
            char id[64]{};
            char path[192]{};
            char name[128]{};
            std::snprintf(id, sizeof(id), "linux-raw-%u-%u", card, device_number);
            std::snprintf(path, sizeof(path), "/dev/snd/midiC%uD%u", card, device_number);
            std::snprintf(name, sizeof(name), "Linux Raw MIDI C%u D%u", card, device_number);

            auto& slot = found[found_count++];
            copy_text(slot.descriptor.id, id);
            copy_text(slot.descriptor.path, path);
            copy_text(slot.descriptor.name, name);
            slot.descriptor.connected = true;
            slot.descriptor.input = true;
            slot.owner = this;

            if (auto* existing = find_slot(id); existing && existing->attached) {
                slot.handle = existing->handle;
                existing->handle = -1; // transfer ownership
                slot.attached = true;
                slot.player_id = existing->player_id;
                slot.parser = existing->parser;
            }
        }
        ::closedir(directory);
    }
#elif defined(_WIN32) || defined(__APPLE__)
    try {
        DeviceMonitor monitor;
        monitor.start();
        const auto snapshot = monitor.snapshot();
        monitor.stop();
        const std::string_view backend =
#if defined(_WIN32)
            "windows-midi";
#else
            "coremidi";
#endif
        for (const auto& record : snapshot.devices) {
            if (found_count >= max_devices) break;
            if (record.kind != DeviceKind::Midi || !record.input) continue;
            auto& slot = found[found_count++];
            copy_text(slot.descriptor.id, target_midi_id(record, backend));
            copy_text(slot.descriptor.path, target_midi_identity(record, backend));
#if defined(_WIN32)
            copy_text(slot.descriptor.name, "Windows MIDI Endpoint");
#else
            copy_text(slot.descriptor.name, "CoreMIDI Endpoint");
#endif
            slot.descriptor.connected = true;
            slot.descriptor.input = true;
            copy_text(slot.native_hash, record.native_hash);
            slot.native_index = record.native_index;
            slot.owner = this;
        }
    } catch (...) {
        // Topology observation is non-authoritative. A concurrent change leaves
        // this scan empty instead of fabricating an endpoint identity.
        found_count = 0;
    }
#endif

    for (std::size_t i = 0; i < device_count_; ++i) {
        close_slot(devices_[i]);
    }
    devices_ = std::move(found);
    device_count_ = found_count;
    return device_count_;
}

bool MidiInputManager::attach(std::string_view device_id, std::string_view player_id) noexcept {
    auto* slot = find_slot(device_id);
    if (!slot || player_id.empty() || player_id.size() >= slot->player_id.size()) {
        return false;
    }
    if (slot->attached) {
        copy_text(slot->player_id, player_id);
        return true;
    }
#if defined(__linux__)
    const auto handle = ::open(slot->descriptor.path.data(), O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    if (handle < 0) {
        return false;
    }
    slot->handle = handle;
    slot->attached = true;
    copy_text(slot->player_id, player_id);
    slot->parser.reset();
    return true;
#else
#if defined(__APPLE__)
    if (!native_client_) {
        MIDIClientRef client = 0;
        if (MIDIClientCreate(CFSTR("StageMesh MIDI Input"), nullptr, nullptr, &client) != noErr) return false;
        native_client_ = static_cast<std::uintptr_t>(client);
    }
    if (!native_port_) {
        MIDIPortRef port = 0;
        if (MIDIInputPortCreate(static_cast<MIDIClientRef>(native_client_), CFSTR("StageMesh MIDI Input Port"), coremidi_read, nullptr, &port) != noErr) return false;
        native_port_ = static_cast<std::uintptr_t>(port);
    }
    for (ItemCount index = 0; index < MIDIGetNumberOfSources(); ++index) {
        const auto source = MIDIGetSource(index);
        const auto hash = sha256_token("coremidi-native:" + std::to_string(static_cast<std::uint64_t>(source)) + ":in");
        if (hash != slot->native_hash.data()) continue;
        if (MIDIPortConnectSource(static_cast<MIDIPortRef>(native_port_), source, slot) != noErr) return false;
        slot->native_source = static_cast<std::uintptr_t>(source);
        slot->attached = true;
        copy_text(slot->player_id, player_id);
        slot->parser.reset();
        return true;
    }
    return false;
#elif defined(_WIN32)
    if (slot->native_index == 0xffffffffu) return false;
    HMIDIIN handle = nullptr;
    if (midiInOpen(&handle, static_cast<UINT>(slot->native_index), reinterpret_cast<DWORD_PTR>(slot),
                   reinterpret_cast<DWORD_PTR>(&winmm_read), CALLBACK_FUNCTION) != MMSYSERR_NOERROR) return false;
    if (midiInStart(handle) != MMSYSERR_NOERROR) { midiInClose(handle); return false; }
    slot->native_source = reinterpret_cast<std::uintptr_t>(handle);
    slot->attached = true;
    copy_text(slot->player_id, player_id);
    slot->parser.reset();
    return true;
#else
    (void)player_id;
    return false;
#endif
#endif
}

bool MidiInputManager::detach(std::string_view device_id) noexcept {
    auto* slot = find_slot(device_id);
    if (!slot) {
        return false;
    }
    close_slot(*slot);
    return true;
}

std::size_t MidiInputManager::attached_count() const noexcept {
    std::size_t count = 0;
    for (std::size_t i = 0; i < device_count_; ++i) {
        if (devices_[i].attached) {
            ++count;
        }
    }
    return count;
}

bool MidiInputManager::queue(const CapturedMidiInput& event) noexcept {
    if (!queue_.try_push(event)) {
        audit_queue_drops_.fetch_add(1,std::memory_order_relaxed);
        return false;
    }
    return true;
}

bool MidiInputManager::pop(CapturedMidiInput& out) noexcept {
    return queue_.try_pop(out);
}

bool MidiInputManager::capture_callback(std::string_view device_id, std::string_view player_id,
                                        const MidiInputMessage& message) noexcept {
    if (device_id.empty() || player_id.empty() || device_id.size() >= 64 || player_id.size() >= 64) {
        return false;
    }
    CapturedMidiInput event{};
    copy_text(event.device_id, device_id);
    copy_text(event.player_id, player_id);
    event.message = message;
    const auto accepted = queue(event);
    if (accepted) audit_messages_.fetch_add(1, std::memory_order_relaxed);
    return accepted;
}

bool MidiInputManager::inject(std::string_view device_id, std::string_view player_id,
                              const MidiInputMessage& message) noexcept {
    const auto accepted = capture_callback(device_id, player_id, message);
    if (accepted) audit_injected_.fetch_add(1, std::memory_order_relaxed);
    return accepted;
}

std::size_t MidiInputManager::poll(std::uint64_t show_time_ns) noexcept {
    const auto started=std::chrono::steady_clock::now();audit_polls_.fetch_add(1,std::memory_order_relaxed);
    std::size_t captured = 0;
#if defined(__linux__)
    std::array<std::uint8_t, 256> bytes{};
    for (std::size_t i = 0; i < device_count_; ++i) {
        auto& slot = devices_[i];
        if (!slot.attached || slot.handle < 0) {
            continue;
        }
        for (;;) {
            const auto read_count = ::read(slot.handle, bytes.data(), bytes.size());
            if (read_count <= 0) {
                break;
            }
            audit_bytes_.fetch_add(static_cast<std::uint64_t>(read_count),std::memory_order_relaxed);
            for (ssize_t index = 0; index < read_count; ++index) {
                MidiInputMessage parsed{};
                if (!slot.parser.feed(bytes[static_cast<std::size_t>(index)], show_time_ns, parsed)) {
                    continue;
                }
                CapturedMidiInput event{};
                event.device_id = slot.descriptor.id;
                event.player_id = slot.player_id;
                event.message = parsed;
                if (queue(event)) {
                    ++captured;audit_messages_.fetch_add(1,std::memory_order_relaxed);
                }
            }
        }
    }
#else
    (void)show_time_ns;
#endif
    const auto duration=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count());auto maximum=audit_max_poll_ns_.load(std::memory_order_relaxed);while(duration>maximum&&!audit_max_poll_ns_.compare_exchange_weak(maximum,duration,std::memory_order_relaxed)){}
    return captured;
}

void MidiInputManager::reconcile() noexcept {
#if defined(_WIN32) || defined(__APPLE__)
    try {
        DeviceMonitor monitor;
        monitor.start();
        const auto snapshot = monitor.snapshot();
        monitor.stop();
        for (std::size_t index = 0; index < device_count_; ++index) {
            auto& slot = devices_[index];
            if (!slot.attached) continue;
            bool present = false;
            for (const auto& record : snapshot.devices) {
                if (record.kind == DeviceKind::Midi && record.input && record.native_hash == slot.native_hash.data()) {
                    present = true;
                    break;
                }
            }
            if (!present) {
                close_slot(slot);
                audit_topology_detaches_.fetch_add(1, std::memory_order_relaxed);
            }
        }
    } catch (...) {
        // A failed topology read cannot authorize a rebind. Existing streams
        // remain attached until a definitive missing/changed identity is seen.
    }
#else
    // Linux poll/read errors are handled by the non-blocking stream itself.
#endif
}

MidiIngressAuditStatus MidiInputManager::audit_status() const noexcept {
    return {audit_polls_.load(std::memory_order_relaxed),audit_bytes_.load(std::memory_order_relaxed),audit_messages_.load(std::memory_order_relaxed),audit_queue_drops_.load(std::memory_order_relaxed),audit_injected_.load(std::memory_order_relaxed),audit_max_poll_ns_.load(std::memory_order_relaxed),false,audit_topology_detaches_.load(std::memory_order_relaxed)};
}

} // namespace stagemesh

