#pragma once
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include "stagemesh/plugin_delay_compensation.hpp"
namespace stagemesh {
template<std::size_t Paths=16,std::size_t MaxDelayFrames=65536> class PluginDelayGraph final{
public:
 struct Status{std::uint64_t active_generation{0},prepared_generation{0},activation_show_ns{0},swaps{0},rejected{0},processed_frames{0};std::uint32_t paths{0},maximum_latency_frames{0};bool prepared{false},physical_outputs_armed{false};};
 bool prepare(std::uint64_t generation,const std::uint32_t*latencies,std::size_t count,std::uint64_t activation_show_ns)noexcept{
  if(generation<=active_generation_.load()||generation<=prepared_generation_.load()||!banks_[inactive()].configure(latencies,count)){rejected_.fetch_add(1);return false;}
  prepared_paths_=static_cast<std::uint32_t>(count);prepared_max_=0;for(std::size_t i=0;i<count;++i)if(latencies[i]>prepared_max_)prepared_max_=latencies[i];activation_show_ns_=activation_show_ns;prepared_generation_.store(generation,std::memory_order_release);return true;}
 bool activate(std::uint64_t show_ns)noexcept{const auto generation=prepared_generation_.load(std::memory_order_acquire);if(!generation||show_ns<activation_show_ns_)return false;active_.store(inactive(),std::memory_order_release);active_generation_.store(generation,std::memory_order_release);paths_.store(prepared_paths_);maximum_.store(prepared_max_);prepared_generation_.store(0,std::memory_order_release);swaps_.fetch_add(1);return true;}
 bool process(std::size_t path,float*l,float*r,std::uint32_t frames)noexcept{if(!banks_[active_.load(std::memory_order_acquire)].process(path,l,r,frames))return false;processed_frames_.fetch_add(frames,std::memory_order_relaxed);return true;}
 Status status()const noexcept{return{active_generation_.load(),prepared_generation_.load(),activation_show_ns_,swaps_.load(),rejected_.load(),processed_frames_.load(),paths_.load(),maximum_.load(),prepared_generation_.load()!=0,false};}
private:std::size_t inactive()const noexcept{return 1-active_.load(std::memory_order_acquire);}std::array<PluginDelayCompensator<Paths,MaxDelayFrames>,2>banks_{};std::atomic<std::size_t>active_{0};std::atomic<std::uint64_t>active_generation_{0},prepared_generation_{0},swaps_{0},rejected_{0},processed_frames_{0};std::atomic<std::uint32_t>paths_{0},maximum_{0};std::uint64_t activation_show_ns_{0};std::uint32_t prepared_paths_{0},prepared_max_{0};};
}
