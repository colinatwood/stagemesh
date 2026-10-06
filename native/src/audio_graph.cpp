#include "stagemesh/audio_graph.hpp"

#include <algorithm>
#include <cmath>
#include <thread>

namespace stagemesh {

AudioGraph::AudioGraph() noexcept {
    for (auto& matrix : route_slots_) for (auto& source : matrix) source.fill(0.0F);
}

float AudioGraph::clamp_gain(float gain) noexcept {
    if (!std::isfinite(gain)) return 0.0F;
    return std::clamp(gain, 0.0F, 4.0F);
}
float AudioGraph::db_to_linear(float db) noexcept {
    if (!std::isfinite(db)) db = -1.0F;
    db = std::clamp(db, -60.0F, 0.0F);
    return std::pow(10.0F, db / 20.0F);
}
float AudioGraph::linear_to_db(float linear) noexcept {
    if (!(linear > 0.000001F) || !std::isfinite(linear)) return -120.0F;
    return 20.0F * std::log10(linear);
}

std::uint8_t AudioGraph::pin_routes() const noexcept {
    for (;;) {
        const auto slot=active_route_slot_.load(std::memory_order_acquire);
        route_readers_[slot].fetch_add(1,std::memory_order_acquire);
        if(active_route_slot_.load(std::memory_order_acquire)==slot) return slot;
        route_readers_[slot].fetch_sub(1,std::memory_order_release);
    }
}
void AudioGraph::unpin_routes(std::uint8_t slot) const noexcept { route_readers_[slot].fetch_sub(1,std::memory_order_release); }

bool AudioGraph::apply_route_transaction(std::span<const AudioRouteChange> changes) noexcept {
    for(const auto& c:changes) if(c.source>=audio_graph_max_sources||c.output>=audio_graph_max_outputs||!std::isfinite(c.linear_gain)) return false;
    while(route_writer_.test_and_set(std::memory_order_acquire)) std::this_thread::yield();
    const auto current=active_route_slot_.load(std::memory_order_acquire);
    const auto next=static_cast<std::uint8_t>(1U-current);
    while(route_readers_[next].load(std::memory_order_acquire)!=0) std::this_thread::yield();
    route_slots_[next]=route_slots_[current];
    for(const auto& c:changes) route_slots_[next][c.source][c.output]=clamp_gain(c.linear_gain);
    active_route_slot_.store(next,std::memory_order_release);
    route_writer_.clear(std::memory_order_release);
    return true;
}

void AudioGraph::set_route_gain(std::uint8_t source,std::uint8_t output,float gain) noexcept {
    const AudioRouteChange c{source,output,gain}; (void)apply_route_transaction(std::span<const AudioRouteChange>(&c,1));
}
float AudioGraph::route_gain(std::uint8_t source,std::uint8_t output) const noexcept {
    if(source>=audio_graph_max_sources||output>=audio_graph_max_outputs)return 0.0F;
    const auto slot=pin_routes(); const float v=route_slots_[slot][source][output]; unpin_routes(slot); return v;
}
void AudioGraph::set_output_master(std::uint8_t output,float gain) noexcept {if(output<audio_graph_max_outputs)outputs_[output].master.store(clamp_gain(gain),std::memory_order_release);}
float AudioGraph::output_master(std::uint8_t output) const noexcept{return output<audio_graph_max_outputs?outputs_[output].master.load(std::memory_order_acquire):0.0F;}
void AudioGraph::set_limiter_ceiling_db(std::uint8_t output,float db) noexcept {if(output>=audio_graph_max_outputs)return;if(!std::isfinite(db))db=-1.0F;outputs_[output].ceiling_db.store(std::clamp(db,-24.0F,0.0F),std::memory_order_release);}
float AudioGraph::limiter_ceiling_db(std::uint8_t output) const noexcept{return output<audio_graph_max_outputs?outputs_[output].ceiling_db.load(std::memory_order_acquire):-120.0F;}

void AudioGraph::process(std::span<const AudioSourceBlock> sources,std::span<AudioOutputBlock> output_blocks,std::size_t frames,AudioOutputEffectFn effect,void* effect_context) noexcept {
    const auto route_slot=pin_routes(); const auto& routes=route_slots_[route_slot];
    for(auto& output:output_blocks){
        if(output.output>=audio_graph_max_outputs||!output.left||!output.right||frames==0)continue;
        std::fill_n(output.left,frames,0.0F);std::fill_n(output.right,frames,0.0F);
        for(const auto& source:sources){if(source.source>=audio_graph_max_sources||!source.left)continue;const float route=routes[source.source][output.output];if(route==0.0F)continue;const float*right=source.right?source.right:source.left;for(std::size_t frame=0;frame<frames;++frame){output.left[frame]+=source.left[frame]*route;output.right[frame]+=right[frame]*route;}}
        if(effect)effect(effect_context,output.output,output.left,output.right,frames);
        auto& state=outputs_[output.output];const float master=state.master.load(std::memory_order_acquire);const float ceiling=db_to_linear(state.ceiling_db.load(std::memory_order_acquire));float peak=0.0F,minimum_gain=1.0F;
        for(std::size_t frame=0;frame<frames;++frame){float left=output.left[frame]*master,right=output.right[frame]*master;const float frame_peak=std::max(std::abs(left),std::abs(right));peak=std::max(peak,frame_peak);const bool limiting=frame_peak>ceiling&&frame_peak>0.0F;const float required=limiting?ceiling/frame_peak:1.0F;if(limiting)state.limiter_gain=std::min(state.limiter_gain,required);else state.limiter_gain=std::min(1.0F,state.limiter_gain+0.002F*(1.0F-state.limiter_gain));minimum_gain=std::min(minimum_gain,state.limiter_gain);output.left[frame]=left*state.limiter_gain;output.right[frame]=right*state.limiter_gain;}
        state.peak.store(peak,std::memory_order_release);state.gain_reduction_db.store(std::min(0.0F,linear_to_db(minimum_gain)),std::memory_order_release);
    }
    unpin_routes(route_slot);
}
AudioGraphOutputMeter AudioGraph::meter(std::uint8_t output) const noexcept {if(output>=audio_graph_max_outputs)return{};return{outputs_[output].peak.load(std::memory_order_acquire),outputs_[output].gain_reduction_db.load(std::memory_order_acquire)};}
} // namespace stagemesh
