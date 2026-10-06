#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

enum class CoreEffectFormat : std::uint8_t { builtin=0, vst3=1, clap=2, lv2=3, audio_unit=4 };
using CoreEffectActivateFn = bool (*)(void*, double, std::uint32_t, std::uint32_t) noexcept;
using CoreEffectProcessFn = bool (*)(void*, float* const*, std::uint32_t, std::uint32_t, std::uint64_t) noexcept;
using CoreEffectDeactivateFn = void (*)(void*) noexcept;

struct CoreEffectAdapter {
    void* context{nullptr};
    CoreEffectActivateFn activate{nullptr};
    CoreEffectProcessFn process{nullptr};
    CoreEffectDeactivateFn deactivate{nullptr};
};
struct CoreEffectDescriptor {
    std::uint64_t effect_id{0};
    CoreEffectFormat format{CoreEffectFormat::builtin};
    std::uint32_t channels{2};
    std::uint32_t latency_frames{0};
    bool realtime_safe{false};
};
struct CoreEffectSlotStatus {
    CoreEffectDescriptor descriptor{};
    std::uint64_t processed_blocks{0};
    std::uint64_t processed_frames{0};
    std::uint64_t failures{0};
    bool registered{false};
    bool active{false};
    bool bypassed{false};
};
struct CoreEffectChainStatus {
    std::uint32_t registered{0}, active{0}, bypassed{0}, total_latency_frames{0};
    std::uint64_t processed_blocks{0}, failures{0};
};

// Format-neutral real-time chain. VST3/CLAP/LV2/AU SDK ownership, discovery,
// licensing and lifecycle details stay in adapters; Core owns bounded ordering,
// bypass and failure isolation. Registration/activation are control-thread calls.
template<std::size_t Capacity = 16>
class CoreEffectChain final {
public:
    ~CoreEffectChain() { deactivate_all(); }
    [[nodiscard]] bool register_effect(const CoreEffectDescriptor& descriptor, CoreEffectAdapter adapter) noexcept {
        if (descriptor.effect_id==0 || descriptor.channels==0 || !descriptor.realtime_safe || !adapter.activate || !adapter.process || find(descriptor.effect_id)) return false;
        for (auto& slot:slots_) if (!slot.registered.load(std::memory_order_acquire)) {
            slot.descriptor=descriptor; slot.adapter=adapter; slot.bypassed.store(false,std::memory_order_relaxed);
            slot.active.store(false,std::memory_order_relaxed); slot.processed_blocks.store(0,std::memory_order_relaxed);
            slot.processed_frames.store(0,std::memory_order_relaxed); slot.failures.store(0,std::memory_order_relaxed);
            slot.registered.store(true,std::memory_order_release); return true;
        }
        return false;
    }
    [[nodiscard]] bool activate_all(double sample_rate, std::uint32_t max_frames, std::uint32_t channels) noexcept {
        if (!(sample_rate>0.0) || max_frames==0 || channels==0) return false;
        for (auto& slot:slots_) {
            if (!slot.registered.load(std::memory_order_acquire) || slot.active.load(std::memory_order_acquire)) continue;
            if (channels>slot.descriptor.channels || !slot.adapter.activate(slot.adapter.context,sample_rate,max_frames,channels)) {
                slot.bypassed.store(true,std::memory_order_release); slot.failures.fetch_add(1,std::memory_order_relaxed); failures_.fetch_add(1,std::memory_order_relaxed); continue;
            }
            slot.active.store(true,std::memory_order_release);
        }
        return true;
    }
    void deactivate_all() noexcept {
        for (auto& slot:slots_) if (slot.active.exchange(false,std::memory_order_acq_rel) && slot.adapter.deactivate) slot.adapter.deactivate(slot.adapter.context);
    }
    [[nodiscard]] bool set_bypass(std::uint64_t effect_id, bool bypass) noexcept {
        auto* slot=find(effect_id); if(!slot)return false; slot->bypassed.store(bypass,std::memory_order_release); return true;
    }
    [[nodiscard]] bool process(float* const* channels, std::uint32_t channel_count, std::uint32_t frames, std::uint64_t show_ns) noexcept {
        if (!channels || channel_count==0 || frames==0) return false;
        bool healthy=true;
        for (auto& slot:slots_) {
            if (!slot.registered.load(std::memory_order_acquire) || !slot.active.load(std::memory_order_acquire) || slot.bypassed.load(std::memory_order_acquire)) continue;
            if (!slot.adapter.process(slot.adapter.context,channels,channel_count,frames,show_ns)) {
                slot.failures.fetch_add(1,std::memory_order_relaxed); failures_.fetch_add(1,std::memory_order_relaxed);
                slot.bypassed.store(true,std::memory_order_release); healthy=false; continue;
            }
            slot.processed_blocks.fetch_add(1,std::memory_order_relaxed); slot.processed_frames.fetch_add(frames,std::memory_order_relaxed);
        }
        processed_blocks_.fetch_add(1,std::memory_order_relaxed); return healthy;
    }
    [[nodiscard]] bool slot_status(std::uint64_t effect_id, CoreEffectSlotStatus& out) const noexcept {
        const auto* s=find_const(effect_id); if(!s)return false; out.descriptor=s->descriptor;
        out.processed_blocks=s->processed_blocks.load(std::memory_order_relaxed); out.processed_frames=s->processed_frames.load(std::memory_order_relaxed);
        out.failures=s->failures.load(std::memory_order_relaxed); out.registered=s->registered.load(std::memory_order_acquire);
        out.active=s->active.load(std::memory_order_acquire); out.bypassed=s->bypassed.load(std::memory_order_acquire); return true;
    }
    [[nodiscard]] CoreEffectChainStatus status() const noexcept {
        CoreEffectChainStatus out{}; out.processed_blocks=processed_blocks_.load(std::memory_order_relaxed); out.failures=failures_.load(std::memory_order_relaxed);
        for (const auto& s : slots_) {
            if (!s.registered.load(std::memory_order_acquire)) continue;
            ++out.registered;
            if (s.active.load(std::memory_order_acquire)) ++out.active;
            if (s.bypassed.load(std::memory_order_acquire)) ++out.bypassed;
            out.total_latency_frames += s.descriptor.latency_frames;
        }
        return out;
    }
private:
    struct Slot { CoreEffectDescriptor descriptor{}; CoreEffectAdapter adapter{}; std::atomic<bool> registered{false},active{false},bypassed{false}; std::atomic<std::uint64_t> processed_blocks{0},processed_frames{0},failures{0}; };
    Slot* find(std::uint64_t id) noexcept {for(auto& s:slots_)if(s.registered.load(std::memory_order_acquire)&&s.descriptor.effect_id==id)return &s;return nullptr;}
    const Slot* find_const(std::uint64_t id)const noexcept{for(const auto& s:slots_)if(s.registered.load(std::memory_order_acquire)&&s.descriptor.effect_id==id)return &s;return nullptr;}
    std::array<Slot,Capacity> slots_{}; std::atomic<std::uint64_t> processed_blocks_{0},failures_{0};
};
} // namespace stagemesh
