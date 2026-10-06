#pragma once
#include "stagemesh/show_event.hpp"
#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

enum class CueActionType : std::uint8_t { transport=0, automation=1, midi=2, lighting=3 };
struct CueAction {
    CueActionType type{CueActionType::automation};
    sf_priority priority{SF_PRIORITY_SHOW};
    std::uint64_t offset_ns{0};
    std::uint64_t owner_id{0};
    ShowEventPayload payload{};
};
struct CueDefinition { std::uint64_t cue_id{0}; std::uint16_t action_count{0}; std::array<CueAction, 32> actions{}; };

template <std::size_t MaxCues=128>
class CoreCueActionGraph final {
public:
    [[nodiscard]] bool define(std::uint64_t cue_id, const CueAction* actions, std::size_t count) noexcept {
        if (cue_id == 0 || !actions || count > 32) return false;
        CueDefinition* slot = nullptr;
        for (auto& cue : cues_) { if (cue.cue_id == cue_id) { slot=&cue; break; } if (!slot && cue.cue_id==0) slot=&cue; }
        if (!slot) return false;
        slot->cue_id = cue_id; slot->action_count = static_cast<std::uint16_t>(count);
        for (std::size_t i=0;i<count;++i) slot->actions[i]=actions[i];
        ++revision_; return true;
    }
    [[nodiscard]] const CueDefinition* find(std::uint64_t cue_id) const noexcept {
        for (const auto& cue : cues_) {
            if (cue.cue_id == cue_id) return &cue;
        }
        return nullptr;
    }
    template <typename Fn>
    [[nodiscard]] std::size_t expand(std::uint64_t cue_id, std::uint64_t cue_event_id, std::uint64_t show_ns, Fn&& fn) const noexcept {
        const auto* cue=find(cue_id); if(!cue) return 0; std::size_t emitted=0;
        for(std::size_t i=0;i<cue->action_count;++i){
            const auto& a=cue->actions[i]; ShowEvent e{}; e.event_id=(cue_event_id<<8U)|(i+1U); e.show_time_ns=show_ns+a.offset_ns;
            e.priority=a.priority; e.owner_id=a.owner_id; e.payload=a.payload;
            switch(a.type){case CueActionType::transport:e.type=ShowEventType::transport;break;case CueActionType::automation:e.type=ShowEventType::automation;break;case CueActionType::midi:e.type=ShowEventType::midi;break;case CueActionType::lighting:e.type=ShowEventType::lighting;break;}
            if(fn(e)) ++emitted;
        } return emitted;
    }
    [[nodiscard]] std::uint64_t revision() const noexcept { return revision_; }
private: std::array<CueDefinition,MaxCues> cues_{}; std::uint64_t revision_{0};
};
} // namespace stagemesh
