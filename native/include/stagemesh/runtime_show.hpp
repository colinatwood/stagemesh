#pragma once
#include "stagemesh/parameter_registry.hpp"
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <thread>

namespace stagemesh {
struct CoreRuntimeRole { std::uint64_t id{0}; std::uint32_t capability_mask{0}; };
struct CoreRuntimeCue { std::uint64_t id{0}; std::uint64_t name_hash{0}; };
struct CoreRuntimeRoute { std::uint64_t from_id{0}; std::uint64_t to_id{0}; std::uint16_t channels{0}; std::uint8_t timing_class{0}; bool enabled{true}; };
struct CoreRuntimeShowSnapshot {
    std::uint64_t generation{0}, source_revision{0}, content_hash{0}, activated_show_ns{0};
    std::uint16_t role_count{0}, cue_count{0}, route_count{0}, parameter_count{0};
    std::array<CoreRuntimeRole,64> roles{}; std::array<CoreRuntimeCue,128> cues{}; std::array<CoreRuntimeRoute,128> routes{};
    std::array<CoreParameterDescriptor,256> parameters{};
};
struct CoreRuntimeShowStatus { std::uint64_t active_generation{0}, pending_generation{0}, source_revision{0}, swaps{0}, rejected{0}; bool pending{false}; };

class CoreRuntimeShow final {
public:
    void begin(std::uint64_t source_revision, std::uint64_t content_hash) noexcept { staging_={}; staging_.source_revision=source_revision; staging_.content_hash=content_hash; staging_open_=true; }
    [[nodiscard]] bool add_role(CoreRuntimeRole v) noexcept { if(!staging_open_||v.id==0||staging_.role_count>=staging_.roles.size()) return false; staging_.roles[staging_.role_count++]=v; return true; }
    [[nodiscard]] bool add_cue(CoreRuntimeCue v) noexcept { if(!staging_open_||v.id==0||staging_.cue_count>=staging_.cues.size()) return false; staging_.cues[staging_.cue_count++]=v; return true; }
    [[nodiscard]] bool add_route(CoreRuntimeRoute v) noexcept { if(!staging_open_||v.from_id==0||v.to_id==0||staging_.route_count>=staging_.routes.size()) return false; staging_.routes[staging_.route_count++]=v; return true; }
    [[nodiscard]] bool add_parameter(CoreParameterDescriptor v) noexcept { if(!staging_open_||v.target_id==0||v.parameter_id==0||staging_.parameter_count>=staging_.parameters.size()) return false; staging_.parameters[staging_.parameter_count++]=v; return true; }
    [[nodiscard]] bool queue_publish(std::uint64_t boundary_show_ns) noexcept {
        if(!staging_open_||pending_ready_.load(std::memory_order_acquire)){++rejected_;return false;}
        staging_open_=false; staging_.generation=next_generation_.fetch_add(1,std::memory_order_acq_rel); pending_=staging_; pending_boundary_=boundary_show_ns;
        pending_ready_.store(true,std::memory_order_release); return true;
    }
    [[nodiscard]] bool activate_if_due(std::uint64_t show_ns) noexcept {
        if(!pending_ready_.load(std::memory_order_acquire)||show_ns<pending_boundary_) return false;
        const auto current=active_slot_.load(std::memory_order_acquire); const auto next=static_cast<std::uint8_t>(1U-current);
        while(readers_[next].load(std::memory_order_acquire)!=0) std::this_thread::yield();
        pending_.activated_show_ns=show_ns; slots_[next]=pending_; active_slot_.store(next,std::memory_order_release);
        pending_ready_.store(false,std::memory_order_release); ++swaps_; return true;
    }
    [[nodiscard]] CoreRuntimeShowSnapshot snapshot() const noexcept {
        for(;;){ const auto slot=active_slot_.load(std::memory_order_acquire); readers_[slot].fetch_add(1,std::memory_order_acquire);
            if(active_slot_.load(std::memory_order_acquire)!=slot){readers_[slot].fetch_sub(1,std::memory_order_release);continue;}
            auto out=slots_[slot]; readers_[slot].fetch_sub(1,std::memory_order_release); return out; }
    }
    [[nodiscard]] CoreRuntimeShowStatus status() const noexcept { const auto s=snapshot(); return {s.generation,pending_ready_.load()?pending_.generation:0,s.source_revision,swaps_.load(),rejected_.load(),pending_ready_.load()}; }
private:
    CoreRuntimeShowSnapshot staging_{}, pending_{}; bool staging_open_{false}; std::uint64_t pending_boundary_{0};
    std::array<CoreRuntimeShowSnapshot,2> slots_{}; mutable std::array<std::atomic<std::uint32_t>,2> readers_{}; std::atomic<std::uint8_t> active_slot_{0};
    std::atomic<bool> pending_ready_{false}; std::atomic<std::uint64_t> next_generation_{1},swaps_{0},rejected_{0};
};
} // namespace stagemesh
