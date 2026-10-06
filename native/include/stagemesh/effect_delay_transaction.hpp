#pragma once
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include "stagemesh/effect_chain.hpp"
#include "stagemesh/plugin_delay_compensation.hpp"

namespace stagemesh {

// Publishes effect bypass decisions and their replacement output delays through
// one generation. Each output callback pins one immutable bank, applies that
// bank's policy to its private chain, then processes the matching delay bank.
template<std::size_t Outputs=4,std::size_t EffectsPerOutput=16,std::size_t MaxDelayFrames=65536>
class EffectDelayTransaction final {
public:
    struct Change { std::uint8_t output{0}; std::uint64_t effect_id{0}; bool bypassed{false}; };
    struct Status {
        std::uint64_t active_generation{0},prepared_generation{0},activation_show_ns{0},commits{0},rollbacks{0},rejected{0},processed_frames{0};
        std::uint32_t paths{0},changes{0},maximum_latency_frames{0};
        bool prepared{false},physical_outputs_armed{false};
    };
    explicit EffectDelayTransaction(std::array<CoreEffectChain<EffectsPerOutput>,Outputs>& chains) noexcept:chains_(chains) {}

    [[nodiscard]] bool prepare(std::uint64_t generation,std::uint64_t boundary,const std::uint32_t*latencies,std::size_t paths,const Change*changes,std::size_t count) noexcept {
        if(!generation||generation<=active_generation_.load(std::memory_order_acquire)||prepared_generation_.load(std::memory_order_acquire)||!latencies||paths==0||paths>Outputs||count>Outputs*EffectsPerOutput){reject();return false;}
        const auto target=1-active_.load(std::memory_order_acquire);
        if(readers_[target].load(std::memory_order_acquire)){reject();return false;}
        auto& bank=banks_[target];
        for(std::size_t i=0;i<count;++i){
            if(!changes||changes[i].output>=Outputs||changes[i].effect_id==0){reject();return false;}
            CoreEffectSlotStatus slot{};if(!chains_[changes[i].output].slot_status(changes[i].effect_id,slot)){reject();return false;}
            for(std::size_t j=0;j<i;++j)if(changes[j].output==changes[i].output&&changes[j].effect_id==changes[i].effect_id){reject();return false;}
        }
        if(!bank.delay.configure(latencies,paths)){reject();return false;}
        bank.generation=generation;bank.boundary=boundary;bank.paths=static_cast<std::uint32_t>(paths);bank.change_count=static_cast<std::uint32_t>(count);bank.maximum=0;
        for(std::size_t i=0;i<paths;++i){bank.latencies[i]=latencies[i];if(latencies[i]>bank.maximum)bank.maximum=latencies[i];}
        for(std::size_t i=0;i<count;++i){bank.changes[i]=changes[i];CoreEffectSlotStatus slot{};(void)chains_[changes[i].output].slot_status(changes[i].effect_id,slot);bank.previous[i]={changes[i].output,changes[i].effect_id,slot.bypassed};}
        activation_show_ns_.store(boundary,std::memory_order_relaxed);prepared_generation_.store(generation,std::memory_order_release);return true;
    }

    [[nodiscard]] bool prepare_rollback(std::uint64_t generation,std::uint64_t boundary) noexcept {
        if(prepared_generation_.load(std::memory_order_acquire)){reject();return false;}
        const auto source=active_.load(std::memory_order_acquire);const auto& current=banks_[source];
        if(!current.generation)return false;
        const bool ok=prepare(generation,boundary,current.latencies.data(),current.paths,current.previous.data(),current.change_count);
        if(ok)prepared_rollback_.store(true,std::memory_order_release);
        return ok;
    }

    [[nodiscard]] bool activate(std::uint64_t show_ns)noexcept{return activate_if_due(show_ns);}

    [[nodiscard]] bool begin(std::size_t output,std::uint64_t show_ns)noexcept{
        if(output>=Outputs||pinned_[output].load(std::memory_order_acquire))return false;
        (void)activate_if_due(show_ns);std::size_t selected=0;
        for(;;){selected=active_.load(std::memory_order_acquire);readers_[selected].fetch_add(1,std::memory_order_acq_rel);if(selected==active_.load(std::memory_order_acquire))break;readers_[selected].fetch_sub(1,std::memory_order_release);}
        auto& bank=banks_[selected];
        for(std::size_t i=0;i<bank.change_count;++i)if(bank.changes[i].output==output)(void)chains_[output].set_bypass(bank.changes[i].effect_id,bank.changes[i].bypassed);
        pinned_[output].store(selected+1,std::memory_order_release);return true;
    }

    [[nodiscard]] bool end(std::size_t output,float*left,float*right,std::uint32_t frames)noexcept{
        if(output>=Outputs||!left||!right||frames==0)return false;
        const auto token=pinned_[output].exchange(0,std::memory_order_acq_rel);if(!token)return false;
        const auto selected=token-1;auto& bank=banks_[selected];const bool ok=bank.generation==0||(output<bank.paths&&bank.delay.process(output,left,right,frames));
        readers_[selected].fetch_sub(1,std::memory_order_release);processed_frames_.fetch_add(frames,std::memory_order_relaxed);return ok;
    }

    [[nodiscard]] bool process(std::size_t output,float*const*channels,std::uint32_t channel_count,std::uint32_t frames,std::uint64_t show_ns) noexcept {
        if(output>=Outputs||!channels||channel_count==0||frames==0)return false;
        if(!begin(output,show_ns))return false;
        const bool effects_ok=chains_[output].process(channels,channel_count,frames,show_ns);
        return end(output,channels[0],channel_count>1?channels[1]:channels[0],frames)&&effects_ok;
    }

    [[nodiscard]] Status status()const noexcept {const auto index=active_.load(std::memory_order_acquire);const auto& bank=banks_[index];return{active_generation_.load(),prepared_generation_.load(),activation_show_ns_.load(),commits_.load(),rollbacks_.load(),rejected_.load(),processed_frames_.load(),bank.paths,bank.change_count,bank.maximum,prepared_generation_.load()!=0,false};}
private:
    struct Bank {PluginDelayCompensator<Outputs,MaxDelayFrames> delay{};std::array<std::uint32_t,Outputs>latencies{};std::array<Change,Outputs*EffectsPerOutput>changes{},previous{};std::uint64_t generation{0},boundary{0};std::uint32_t paths{0},change_count{0},maximum{0};};
    void reject()noexcept{rejected_.fetch_add(1,std::memory_order_relaxed);}
    bool activate_if_due(std::uint64_t show_ns)noexcept{
        auto pending=prepared_generation_.load(std::memory_order_acquire);if(!pending||show_ns<activation_show_ns_.load(std::memory_order_relaxed))return false;
        if(!prepared_generation_.compare_exchange_strong(pending,0,std::memory_order_acq_rel))return false;
        active_.store(1-active_.load(std::memory_order_relaxed),std::memory_order_release);active_generation_.store(pending,std::memory_order_release);commits_.fetch_add(1,std::memory_order_relaxed);
        if(prepared_rollback_.exchange(false,std::memory_order_acq_rel))rollbacks_.fetch_add(1,std::memory_order_relaxed);
        return true;
    }
    std::array<CoreEffectChain<EffectsPerOutput>,Outputs>& chains_;std::array<Bank,2>banks_{};std::array<std::atomic<std::uint32_t>,2>readers_{};std::array<std::atomic<std::size_t>,Outputs>pinned_{};
    std::atomic<std::size_t>active_{0};std::atomic<std::uint64_t>active_generation_{0},prepared_generation_{0},activation_show_ns_{0},commits_{0},rollbacks_{0},rejected_{0},processed_frames_{0};std::atomic<bool>prepared_rollback_{false};
};
}
