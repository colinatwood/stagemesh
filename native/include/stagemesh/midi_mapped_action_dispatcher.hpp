#pragma once

#include "stagemesh/midi_learn_router.hpp"
#include "stagemesh/show_event.hpp"

#include <cstdint>

namespace stagemesh {

using MidiMappedEventSinkFn = bool (*)(void* context, const ShowEvent& event) noexcept;

struct MidiMappedDispatchStatus {
    std::uint64_t received{0};
    std::uint64_t submitted{0};
    std::uint64_t rejected{0};
    std::uint64_t ignored{0};
    std::uint64_t last_event_id{0};
    bool physical_outputs_armed{false};
};

// Converts mapped controller gestures into authoritative typed Show Events.
// The caller remains the single producer for the supplied event sink; Core's
// ShowExecutionLoop remains the only timeline/dispatch owner.
class MidiMappedActionDispatcher final {
public:
    MidiMappedActionDispatcher(MidiMappedEventSinkFn sink, void* context,
                               std::uint64_t owner_id) noexcept
        : sink_(sink), context_(context), owner_id_(owner_id ? owner_id : 1) {}

    [[nodiscard]] bool dispatch(const MidiMappedAction& action,
                                std::uint64_t revision) noexcept {
        ++status_.received;
        ShowEvent event{};
        event.event_id = 0x8000000000000000ULL | next_sequence_++;
        event.revision = revision;
        event.show_time_ns = action.show_time_ns;
        event.owner_id = owner_id_;
        event.priority = SF_PRIORITY_SHOW;
        event.flags = show_event_authoritative | show_event_replay_safe;

        switch (action.action) {
            case MidiMappedActionKind::automation:
                if (!action.target_id || !action.parameter_id) return ignored();
                event.type = ShowEventType::automation;
                event.payload.automation = {action.target_id, action.parameter_id, action.value, 0};
                break;
            case MidiMappedActionKind::transport_play:
                if (!(action.value > 0.0F)) return ignored();
                event.type = ShowEventType::transport;
                event.priority = SF_PRIORITY_CRITICAL;
                event.payload.transport = {SF_CORE_TRANSPORT_PLAY, 0.0};
                break;
            case MidiMappedActionKind::transport_stop:
                if (!(action.value > 0.0F)) return ignored();
                event.type = ShowEventType::transport;
                event.priority = SF_PRIORITY_CRITICAL;
                event.payload.transport = {SF_CORE_TRANSPORT_STOP, 0.0};
                break;
            case MidiMappedActionKind::transport_tempo:
                event.type = ShowEventType::transport;
                event.priority = SF_PRIORITY_CRITICAL;
                event.payload.transport = {SF_CORE_TRANSPORT_SET_BPM, action.value};
                break;
            case MidiMappedActionKind::sample_trigger:
                if (!(action.value > 0.0F) || !action.resource_id) return ignored();
                event.type = ShowEventType::sampler;
                event.payload.sampler = {action.resource_id, action.value, action.key_synced?action.output_note:action.input_note, ShowSamplerAction::trigger, {0,0}};
                break;
            case MidiMappedActionKind::loop_toggle:
                if (!action.resource_id) return ignored();
                event.type = ShowEventType::sampler;
                event.payload.sampler = {action.resource_id, 1.0F, action.key_synced?action.output_note:action.input_note,
                    action.value>0.0F?ShowSamplerAction::trigger:ShowSamplerAction::stop_sample, {0,0}};
                break;
            case MidiMappedActionKind::loop_clear:
                if (!(action.value > 0.0F) || !action.resource_id) return ignored();
                event.type = ShowEventType::sampler;
                event.payload.sampler = {action.resource_id, 0.0F, 0, ShowSamplerAction::stop_sample, {0,0}};
                break;
        }

        status_.last_event_id = event.event_id;
        if (!sink_ || !sink_(context_, event)) {
            ++status_.rejected;
            return false;
        }
        ++status_.submitted;
        return true;
    }

    [[nodiscard]] MidiMappedDispatchStatus status() const noexcept { return status_; }

private:
    [[nodiscard]] bool ignored() noexcept {
        ++status_.ignored;
        return false;
    }

    MidiMappedEventSinkFn sink_{nullptr};
    void* context_{nullptr};
    std::uint64_t owner_id_{1};
    std::uint64_t next_sequence_{1};
    MidiMappedDispatchStatus status_{};
};

} // namespace stagemesh
