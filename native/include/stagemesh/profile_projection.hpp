#pragma once

#include "stagemesh/user_profile.hpp"
#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

struct ProfileProjectionCandidate {ProfilePreference preference{};bool accessibility{false};};
struct ProfileProjectionEntry {ProfilePreference preference{};bool consent_required{false};};
template <std::size_t Capacity=128> struct ProfileProjection {std::array<ProfileProjectionEntry,Capacity> entries{};std::size_t count{0};std::uint64_t digest{0};std::uint32_t consent_required{0};bool physical_outputs_armed{false};};

template <std::size_t Capacity=128>
class ProfileProjector final {
public:
    [[nodiscard]] ProfileProjection<Capacity> project(const ProfileProjectionCandidate* candidates,std::size_t count) const noexcept {
        ProfileProjection<Capacity> result{};if(!candidates)return result;count=count>Capacity?Capacity:count;
        for(std::size_t i=0;i<count;++i){const auto& candidate=candidates[i];std::size_t found=result.count;
            for(std::size_t j=0;j<result.count;++j)if(result.entries[j].preference.namespace_id==candidate.preference.namespace_id&&result.entries[j].preference.key_id==candidate.preference.key_id){found=j;break;}
            if(found==result.count){result.entries[result.count++].preference=candidate.preference;continue;}
            auto& selected=result.entries[found].preference;if(rank(candidate)>rank({selected,candidate.accessibility})||(rank(candidate)==rank({selected,candidate.accessibility})&&candidate.preference.revision>selected.revision))selected=candidate.preference;
        }
        for(std::size_t i=0;i<result.count;++i){auto& entry=result.entries[i];const auto layer=entry.preference.layer;
            if(layer==ProfileLayer::role||layer==ProfileLayer::venue||layer==ProfileLayer::session){
                for(std::size_t j=0;j<count;++j)if(candidates[j].preference.namespace_id==entry.preference.namespace_id&&candidates[j].preference.key_id==entry.preference.key_id&&candidates[j].preference.layer==ProfileLayer::user&&different(candidates[j].preference,entry.preference)){entry.consent_required=true;++result.consent_required;break;}
            }
            result.digest=mix(result.digest,entry.preference.namespace_id);result.digest=mix(result.digest,entry.preference.key_id);result.digest=mix(result.digest,entry.preference.revision);
        }
        result.physical_outputs_armed=false;return result;
    }
private:
    [[nodiscard]] static unsigned int rank(ProfileProjectionCandidate candidate) noexcept {const auto layer=candidate.preference.layer;if(candidate.accessibility&&layer==ProfileLayer::venue)return 1;if(candidate.accessibility&&layer==ProfileLayer::user)return 2;return static_cast<unsigned int>(layer);}
    [[nodiscard]] static bool different(const ProfilePreference& a,const ProfilePreference& b) noexcept {return a.type!=b.type||a.integer_value!=b.integer_value||a.scalar_value!=b.scalar_value||a.token_value!=b.token_value;}
    [[nodiscard]] static std::uint64_t mix(std::uint64_t hash,std::uint64_t value) noexcept {hash=hash?hash:14695981039346656037ULL;for(unsigned int i=0;i<8;++i){hash^=static_cast<std::uint8_t>(value>>(i*8U));hash*=1099511628211ULL;}return hash;}
};

} // namespace stagemesh
