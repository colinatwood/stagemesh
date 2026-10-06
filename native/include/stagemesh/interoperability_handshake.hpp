#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

struct HandshakeCapability {std::uint64_t id{0};bool required{false};};
struct HandshakeAdapter {std::uint64_t from{0};std::uint64_t to{0};std::uint8_t quality{0};};

template <std::size_t MaxCapabilities=64>
struct HandshakeOffer {
    std::uint64_t participant_id{0};
    std::uint32_t protocol_min{0},protocol_max{0};
    std::uint32_t profile_schema_min{0},profile_schema_max{0};
    std::array<HandshakeCapability,MaxCapabilities> capabilities{};
    std::size_t capability_count{0};
    bool preserves_unknown{true};
    bool offline_capable{true};
};

struct HandshakePlan {
    std::uint32_t protocol_version{0},profile_schema_version{0};
    std::uint32_t direct_capabilities{0},translated_capabilities{0},preserved_unknown_capabilities{0},missing_required{0};
    std::uint8_t minimum_adapter_quality{100};
    bool compatible{false},unknown_preservation{false},offline_compatible{false},physical_outputs_armed{false};
};

template <std::size_t MaxCapabilities=64,std::size_t MaxAdapters=32>
class InteroperabilityHandshake final {
public:
    [[nodiscard]] bool configure_local(const HandshakeOffer<MaxCapabilities>& offer) noexcept {if(!valid(offer))return false;local_=offer;adapter_count_=0;configured_=true;return true;}
    [[nodiscard]] bool add_adapter(HandshakeAdapter adapter) noexcept {
        if(adapter.from==0||adapter.to==0||adapter.quality==0||adapter_count_>=MaxAdapters)return false;
        adapters_[adapter_count_++]=adapter;return true;
    }
    [[nodiscard]] HandshakePlan negotiate(const HandshakeOffer<MaxCapabilities>& remote) const noexcept {
        HandshakePlan plan{};if(!configured_||!valid(remote))return plan;
        plan.protocol_version=highest_common(local_.protocol_min,local_.protocol_max,remote.protocol_min,remote.protocol_max);
        plan.profile_schema_version=highest_common(local_.profile_schema_min,local_.profile_schema_max,remote.profile_schema_min,remote.profile_schema_max);
        plan.unknown_preservation=local_.preserves_unknown&&remote.preserves_unknown;
        plan.offline_compatible=local_.offline_capable&&remote.offline_capable;
        for(std::size_t i=0;i<remote.capability_count;++i){
            const auto cap=remote.capabilities[i];if(contains(local_,cap.id)){++plan.direct_capabilities;continue;}
            std::uint8_t quality=0;for(std::size_t j=0;j<adapter_count_;++j)if(adapters_[j].from==cap.id&&contains(local_,adapters_[j].to)){quality=adapters_[j].quality;break;}
            if(quality>0){++plan.translated_capabilities;if(quality<plan.minimum_adapter_quality)plan.minimum_adapter_quality=quality;continue;}
            if(cap.required)++plan.missing_required;else ++plan.preserved_unknown_capabilities;
        }
        for(std::size_t i=0;i<local_.capability_count;++i){const auto cap=local_.capabilities[i];if(!cap.required||contains(remote,cap.id))continue;
            bool translated=false;for(std::size_t j=0;j<adapter_count_;++j)if(adapters_[j].to==cap.id&&contains(remote,adapters_[j].from)){translated=true;break;}
            if(!translated)++plan.missing_required;
        }
        const bool unknown_safe=plan.preserved_unknown_capabilities==0||plan.unknown_preservation;
        plan.compatible=plan.protocol_version>0&&plan.profile_schema_version>0&&plan.missing_required==0&&unknown_safe;
        plan.physical_outputs_armed=false;return plan;
    }
private:
    [[nodiscard]] static bool valid(const HandshakeOffer<MaxCapabilities>& offer) noexcept {
        if(offer.participant_id==0||offer.protocol_min==0||offer.protocol_min>offer.protocol_max||offer.profile_schema_min==0||offer.profile_schema_min>offer.profile_schema_max||offer.capability_count>MaxCapabilities)return false;
        for(std::size_t i=0;i<offer.capability_count;++i)if(offer.capabilities[i].id==0)return false;
        return true;
    }
    [[nodiscard]] static bool contains(const HandshakeOffer<MaxCapabilities>& offer,std::uint64_t id) noexcept {for(std::size_t i=0;i<offer.capability_count;++i)if(offer.capabilities[i].id==id)return true;return false;}
    [[nodiscard]] static std::uint32_t highest_common(std::uint32_t amin,std::uint32_t amax,std::uint32_t bmin,std::uint32_t bmax) noexcept {const auto low=amin>bmin?amin:bmin,high=amax<bmax?amax:bmax;return low<=high?high:0;}
    HandshakeOffer<MaxCapabilities> local_{};
    std::array<HandshakeAdapter,MaxAdapters> adapters_{};
    std::size_t adapter_count_{0};bool configured_{false};
};

} // namespace stagemesh
