#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace stagemesh {

enum class ProfileLayer : std::uint8_t { base=0, user=1, role=2, venue=3, session=4 };
enum class ProfileValueType : std::uint8_t { boolean=0, integer=1, scalar=2, token=3 };

struct ProfilePreference {
    std::uint64_t namespace_id{0};
    std::uint64_t key_id{0};
    ProfileLayer layer{ProfileLayer::base};
    ProfileValueType type{ProfileValueType::boolean};
    std::uint64_t revision{0};
    std::int64_t integer_value{0};
    double scalar_value{0.0};
    std::uint64_t token_value{0};
};

struct UserProfileStatus {
    std::uint64_t profile_id{0};
    std::uint64_t authority_epoch{0};
    std::uint64_t revision{0};
    std::uint64_t accepted_updates{0};
    std::uint64_t rejected_updates{0};
    std::uint32_t stored_preferences{0};
    bool configured{false};
    bool physical_outputs_armed{false};
};

template <std::size_t Capacity=128>
class UserProfileCustomization final {
public:
    [[nodiscard]] bool configure(std::uint64_t profile_id,std::uint64_t authority_epoch) noexcept {
        if(profile_id==0||authority_epoch==0||authority_epoch<authority_epoch_){++rejected_;return false;}
        if(profile_id_!=profile_id||authority_epoch_!=authority_epoch){entries_.fill({});used_=0;revision_=0;}
        profile_id_=profile_id;authority_epoch_=authority_epoch;configured_=true;return true;
    }

    [[nodiscard]] bool set(ProfilePreference preference) noexcept {
        if(!configured_||preference.namespace_id==0||preference.key_id==0||preference.revision==0||
           static_cast<unsigned int>(preference.layer)>static_cast<unsigned int>(ProfileLayer::session)||
           static_cast<unsigned int>(preference.type)>static_cast<unsigned int>(ProfileValueType::token)){
            ++rejected_;return false;
        }
        for(std::size_t i=0;i<used_;++i){
            auto& current=entries_[i];
            if(current.namespace_id==preference.namespace_id&&current.key_id==preference.key_id&&current.layer==preference.layer){
                if(preference.revision<=current.revision){++rejected_;return false;}
                current=preference;revision_=preference.revision>revision_?preference.revision:revision_;++accepted_;return true;
            }
        }
        if(used_>=Capacity){++rejected_;return false;}
        entries_[used_++]=preference;revision_=preference.revision>revision_?preference.revision:revision_;++accepted_;return true;
    }

    [[nodiscard]] bool resolve(std::uint64_t namespace_id,std::uint64_t key_id,ProfilePreference& out) const noexcept {
        const ProfilePreference* best=nullptr;
        for(std::size_t i=0;i<used_;++i){const auto& item=entries_[i];
            if(item.namespace_id!=namespace_id||item.key_id!=key_id)continue;
            if(!best||static_cast<unsigned int>(item.layer)>static_cast<unsigned int>(best->layer)||
               (item.layer==best->layer&&item.revision>best->revision))best=&item;
        }
        if(!best)return false;
        out=*best;
        return true;
    }

    [[nodiscard]] std::size_t clear_layer(ProfileLayer layer) noexcept {
        std::size_t removed=0,write=0;
        for(std::size_t read=0;read<used_;++read){if(entries_[read].layer==layer){++removed;continue;}entries_[write++]=entries_[read];}
        while(write<used_)entries_[write++]={};
        used_-=removed;
        return removed;
    }

    [[nodiscard]] UserProfileStatus status() const noexcept {return {profile_id_,authority_epoch_,revision_,accepted_,rejected_,static_cast<std::uint32_t>(used_),configured_,false};}

private:
    std::array<ProfilePreference,Capacity> entries_{};
    std::size_t used_{0};
    std::uint64_t profile_id_{0},authority_epoch_{0},revision_{0},accepted_{0},rejected_{0};
    bool configured_{false};
};

} // namespace stagemesh
