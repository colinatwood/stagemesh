#pragma once

#include "stagemesh/core_api.h"

#include <cstdint>
#include <type_traits>

namespace stagemesh {

enum class ShowEventType : std::uint8_t {
    transport = 0,
    midi = 1,
    lighting = 2,
    cue = 3,
    automation = 4,
    sampler = 5,
};

enum ShowEventFlags : std::uint16_t {
    show_event_none = 0,
    show_event_authoritative = 1u << 0,
    show_event_replay_safe = 1u << 1,
    show_event_drop_if_late = 1u << 2,
    show_event_automation_release_owner = 1u << 3,
};

struct ShowTransportPayload {
    sf_core_transport_action action{SF_CORE_TRANSPORT_PLAY};
    double value{0.0};
};

struct ShowMidiPayload {
    std::uint8_t status{0};
    std::uint8_t data1{0};
    std::uint8_t data2{0};
    std::uint8_t port{0};
};

struct ShowLightingPayload {
    std::uint16_t universe{0};
    std::uint16_t channel{1};
    std::uint8_t value{0};
    std::uint8_t reserved[3]{};
};

struct ShowCuePayload {
    std::uint64_t cue_id{0};
};

struct ShowAutomationPayload {
    std::uint64_t target_id{0};
    std::uint64_t parameter_id{0};
    float value{0.0F};
    std::uint32_t duration_ms{0};
};

enum class ShowSamplerAction : std::uint8_t { trigger=0, stop_sample=1, stop_all=2 };
struct ShowSamplerPayload {
    std::uint64_t sample_id{0};
    float velocity{1.0F};
    std::uint8_t note{60};
    ShowSamplerAction action{ShowSamplerAction::trigger};
    std::uint8_t reserved[2]{};
};

union ShowEventPayload {
    ShowTransportPayload transport;
    ShowMidiPayload midi;
    ShowLightingPayload lighting;
    ShowCuePayload cue;
    ShowAutomationPayload automation;
    ShowSamplerPayload sampler;

    constexpr ShowEventPayload() noexcept : cue{} {}
};

struct ShowEvent {
    std::uint64_t event_id{0};
    std::uint64_t revision{0};
    std::uint64_t show_time_ns{0};
    std::uint64_t owner_id{0};
    ShowEventType type{ShowEventType::cue};
    sf_priority priority{SF_PRIORITY_SHOW};
    std::uint16_t flags{show_event_none};
    ShowEventPayload payload{};
};

[[nodiscard]] inline bool show_event_is_valid(const ShowEvent& event) noexcept {
    if (event.event_id == 0) return false;
    switch (event.type) {
        case ShowEventType::transport:
            return event.payload.transport.action >= SF_CORE_TRANSPORT_PLAY &&
                   event.payload.transport.action <= SF_CORE_TRANSPORT_SEEK_SECONDS;
        case ShowEventType::midi:
            return event.payload.midi.status >= 0x80;
        case ShowEventType::lighting:
            return event.payload.lighting.channel >= 1 && event.payload.lighting.channel <= 512;
        case ShowEventType::cue:
            return event.payload.cue.cue_id != 0;
        case ShowEventType::automation:
            return event.payload.automation.target_id != 0 && event.payload.automation.parameter_id != 0;
        case ShowEventType::sampler:
            return event.payload.sampler.action == ShowSamplerAction::stop_all || event.payload.sampler.sample_id != 0;
    }
    return false;
}

static_assert(std::is_trivially_copyable_v<ShowEvent>, "ShowEvent must remain allocation-free/SPSC-safe");

} // namespace stagemesh
