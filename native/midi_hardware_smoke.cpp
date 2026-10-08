#include "stagemesh/midi_input.hpp"
#include "stagemesh/midi_smoke_evidence.hpp"
#include "device_identity.h"

#include <CoreFoundation/CoreFoundation.h>
#include <CoreMIDI/CoreMIDI.h>

#include <chrono>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>

namespace {

std::string endpoint_name(MIDIEndpointRef endpoint) {
    CFStringRef value = nullptr;
    if (MIDIObjectGetStringProperty(endpoint, kMIDIPropertyName, &value) != noErr || !value) return {};
    char buffer[256]{};
    const bool converted = CFStringGetCString(value, buffer, sizeof(buffer), kCFStringEncodingUTF8);
    CFRelease(value);
    return converted ? std::string(buffer) : std::string{};
}

std::string endpoint_property(MIDIEndpointRef endpoint, CFStringRef property) {
    CFStringRef value = nullptr;
    if (MIDIObjectGetStringProperty(endpoint, property, &value) != noErr || !value) return {};
    char buffer[256]{};
    const bool converted = CFStringGetCString(value, buffer, sizeof(buffer), kCFStringEncodingUTF8);
    CFRelease(value);
    return converted ? std::string(buffer) : std::string{};
}

std::string endpoint_search_text(MIDIEndpointRef endpoint) {
    return endpoint_name(endpoint) + " " +
           endpoint_property(endpoint, kMIDIPropertyDisplayName) + " " +
           endpoint_property(endpoint, kMIDIPropertyManufacturer) + " " +
           endpoint_property(endpoint, kMIDIPropertyModel);
}

bool contains_folded(std::string value, std::string needle) {
    for (auto* text : {&value, &needle}) {
        for (char& character : *text) {
            if (character >= 'A' && character <= 'Z') character = static_cast<char>(character - 'A' + 'a');
        }
    }
    return value.find(needle) != std::string::npos;
}

std::string manager_id(MIDIEndpointRef source) {
    const auto hash = stagemesh::sha256_token(
        "coremidi-native:" + std::to_string(static_cast<std::uint64_t>(source)) + ":in");
    std::string digest = hash;
    if (digest.rfind("sha256:", 0) == 0) digest.erase(0, 7);
    if (digest.size() > 40) digest.resize(40);
    return "coremidi-" + digest;
}

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

} // namespace

int main() {
    try {
        const char* configured = std::getenv("STAGEMESH_MIDI_DEVICE_NAME");
        const std::string needle = configured && *configured ? configured : "FLkey Mini";
        MIDIEndpointRef selected = 0;
        std::string selected_name;
        for (ItemCount index = 0; index < MIDIGetNumberOfSources(); ++index) {
            const auto source = MIDIGetSource(index);
            const auto name = endpoint_name(source);
            if (contains_folded(endpoint_search_text(source), needle)) {
                require(selected == 0, "multiple matching MIDI sources; narrow STAGEMESH_MIDI_DEVICE_NAME");
                selected = source;
                selected_name = name;
            }
        }
        if (selected == 0) {
            std::cerr << "CoreMIDI sources discovered: " << MIDIGetNumberOfSources() << '\n';
            for (ItemCount index = 0; index < MIDIGetNumberOfSources(); ++index) {
                const auto source = MIDIGetSource(index);
                std::cerr << "  source[" << index << "]: " << endpoint_search_text(source) << '\n';
            }
            throw std::runtime_error("named MIDI source not found; inspect the listed CoreMIDI source metadata");
        }

        stagemesh::MidiInputManager manager;
        require(manager.scan() > 0, "CoreMIDI input scan found no sources");
        const auto id = manager_id(selected);
        require(manager.attach(id, "hardware-qualification"), "production MIDI input attach failed");

        std::uint64_t events = 0;
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(15);
        while (std::chrono::steady_clock::now() < deadline) {
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, true);
            stagemesh::CapturedMidiInput event{};
            while (manager.pop(event)) ++events;
            if (events > 0) break;
        }
        const auto audit = manager.audit_status();
        manager.detach(id);
        manager.deactivate();
        std::cout << stagemesh::midi_smoke_evidence(
            selected_name, needle, events, audit.messages, audit.physical_outputs_armed) << '\n';
        return events > 0 ? 0 : 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
