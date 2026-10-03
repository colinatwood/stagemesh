#include "stageforge/audio_device.hpp"
#include "stageforge/audio_device_manager.hpp"
#include "stageforge/audio_graph.hpp"
#include "stageforge/alsa_audio_output.hpp"
#include "stageforge/alsa_audio_input.hpp"
#include "stageforge/audio_input_ring.hpp"
#include "stageforge/audio_fanout_ring.hpp"
#include "stageforge/adaptive_drift_resampler.hpp"
#include "stageforge/artnet_udp_output.hpp"
#include "stageforge/artnet.hpp"
#include "stageforge/sacn_udp_output.hpp"
#include "stageforge/sacn.hpp"
#include "stageforge/automation_state.hpp"
#include "stageforge/parameter_registry.hpp"
#include "stageforge/cue_action_graph.hpp"
#include "stageforge/runtime_show.hpp"
#include "stageforge/routing_transaction.hpp"
#include "stageforge/core_journal.hpp"
#include "stageforge/shadow_render_planner.hpp"
#include "stageforge/shadow_prebuffer.hpp"
#include "stageforge/planned_handoff.hpp"
#include "stageforge/effect_chain.hpp"
#include "stageforge/effect_delay_transaction.hpp"
#include "stageforge/canonical_audio.hpp"
#include "stageforge/le_uwb_hub.hpp"
#include "stageforge/le_uwb_hardware_manager.hpp"
#include "stageforge/user_profile.hpp"
#include "stageforge/interoperability_handshake.hpp"
#include "stageforge/authenticated_interop_session.hpp"
#include "stageforge/profile_projection.hpp"
#include "stageforge/session_channel.hpp"
#include "stageforge/daw_playback_queue.hpp"
#include "stageforge/daw_recording_queue.hpp"
#include "stageforge/lighting_scheduler.hpp"
#include "stageforge/clock_discipline.hpp"
#include "stageforge/core_state.hpp"
#include "stageforge/latency_resolver.hpp"
#include "stageforge/midi_scheduler.hpp"
#include "stageforge/show_event_dispatcher.hpp"
#include "stageforge/show_execution_loop.hpp"
#include "stageforge/cue_state.hpp"
#include "stageforge/midi_input.hpp"
#include "stageforge/midi_input_owner.hpp"
#include "stageforge/midi_learn_router.hpp"
#include "stageforge/midi_mapped_action_dispatcher.hpp"
#include "stageforge/midi_clock.hpp"
#include "stageforge/sampler_voice_engine.hpp"
#include "stageforge/streaming_voice_engine.hpp"
#include "stageforge/plugin_delay_graph.hpp"
#include "stageforge/realtime_audit.hpp"
#include "stageforge/realtime_qualification.hpp"
#include "stageforge/capture_ingress_audit.hpp"
#include "stageforge/capture_ingress.hpp"
#include "stageforge/lighting_ingress_audit.hpp"
#include "stageforge/monitor_bus.hpp"
#include "stageforge/monitor_graph_router.hpp"
#include "stageforge/notation_quantizer.hpp"
#include "stageforge/transport_clock.hpp"
#include "stageforge/transport_discipline.hpp"
#if defined(_WIN32) || defined(__APPLE__)
#include "native_capture.h"
#include "native_capture_service.h"
#include "native_playback.h"
#include "native_playback_service.h"
#include "stageforge/capture_service_owner.hpp"
#endif

#include <algorithm>
#include <atomic>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdlib>
#include <cstdint>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <random>
#include <string>
#include <string_view>
#include <vector>

namespace {

constexpr std::string_view kEngineVersion{"5.0"};
constexpr std::size_t kAudioInputSlots = 4;
constexpr std::size_t kAudioOutputSlots = 4;
using EngineEffectDelayTransaction=stageforge::EffectDelayTransaction<kAudioOutputSlots,16,65536>;
constexpr std::size_t kSamplerAssetFrames = 65536;

struct EngineSamplerAsset {
    std::uint64_t sample_id{0};
    std::uint32_t total_frames{0},written_frames{0},loop_begin{0},loop_end{0};
    std::uint16_t crossfade_frames{0};
    std::uint8_t choke_group{0};
    bool looped{false},staging{false},published{false};
    std::array<float,kSamplerAssetFrames> left{},right{};
};

using EngineInputRing = stageforge::AudioFanoutRing<32768, kAudioOutputSlots>;

struct EngineAudioInputState {
    EngineInputRing ring{};
    std::atomic<std::uint8_t> source{24};
    std::atomic<bool> enabled{false};
    std::atomic<double> sample_rate{stageforge::canonical_audio_sample_rate};
    stageforge::DawRecordingQueue<8,256,64>* daw_recording{nullptr};
    std::uint8_t recording_track{0};
    std::atomic<std::uint64_t> recording_sequence{0},recording_frame{0},recording_generation{0};
    stageforge::CaptureIngressAudit audit{};
};

using EngineShowLoop = stageforge::ShowExecutionLoop<2048, 4096>;

bool submit_midi_mapped_event(void* raw, const stageforge::ShowEvent& event) noexcept {
    auto* loop = static_cast<EngineShowLoop*>(raw);
    return loop && loop->submit(event);
}

std::uint64_t stable_token_id(std::string_view value) noexcept {
    std::uint64_t hash = 14695981039346656037ULL;
    for (const unsigned char byte : value) { hash ^= byte; hash *= 1099511628211ULL; }
    return hash ? hash : 1;
}

struct EngineShowDispatchContext {
    stageforge::CoreControlState* core{nullptr};
    stageforge::SpscQueue<stageforge::MidiEvent, 1024>* midi_ingress{nullptr};
    stageforge::SpscQueue<stageforge::LightingEvent, 2048>* lighting_ingress{nullptr};
    stageforge::CoreCueState* cues{nullptr};
    stageforge::CoreAutomationState<256>* automation{nullptr};
    stageforge::CoreCueActionGraph<128>* cue_graph{nullptr};
    EngineShowLoop* show_loop{nullptr};
    stageforge::CoreJournal<4096>* journal{nullptr};
    stageforge::SpscQueue<stageforge::ShowEvent, 256>* cue_events{nullptr};
    stageforge::SpscQueue<stageforge::ShowEvent, 256>* automation_events{nullptr};
    stageforge::SamplerVoiceEngine<64,32,1025>* sampler{nullptr};
    stageforge::LightingIngressAudit* lighting_audit{nullptr};
};

struct EngineParameterEndpointContext {
    enum class Kind : std::uint8_t { none=0, audio_master=1, audio_route=2, monitor_master=3, monitor_channel=4, lighting=5 };
    Kind kind{Kind::none};
    stageforge::AudioGraph* graph{nullptr};
    stageforge::CoreControlState* core{nullptr};
    stageforge::MonitorGraphRouter* monitor_router{nullptr};
    std::array<stageforge::DmxUniverseState, 16>* dmx{nullptr};
    std::array<char, 64> player{};
    std::uint8_t source{0};
    std::uint8_t output{0};
    stageforge::MonitorChannel monitor_channel{stageforge::MonitorChannel::self};
    std::uint16_t universe{0};
    std::uint16_t channel{1};
};

void apply_engine_parameter(void* raw, float value) noexcept {
    auto* ctx = static_cast<EngineParameterEndpointContext*>(raw);
    if (!ctx) return;
    switch (ctx->kind) {
        case EngineParameterEndpointContext::Kind::audio_master:
            if (ctx->graph) ctx->graph->set_output_master(ctx->output, value);
            return;
        case EngineParameterEndpointContext::Kind::audio_route:
            if (ctx->graph) ctx->graph->set_route_gain(ctx->source, ctx->output, value);
            return;
        case EngineParameterEndpointContext::Kind::monitor_master:
        case EngineParameterEndpointContext::Kind::monitor_channel: {
            if (!ctx->core || !ctx->monitor_router || !ctx->graph) return;
            const std::string_view player(ctx->player.data());
            auto* bus = ctx->core->monitors().find(player);
            if (!bus) return;
            if (ctx->kind == EngineParameterEndpointContext::Kind::monitor_master) bus->set_master(value);
            else bus->set_level(ctx->monitor_channel, value);
            (void)ctx->monitor_router->sync(player, *bus, *ctx->graph);
            return;
        }
        case EngineParameterEndpointContext::Kind::lighting:
            if (ctx->dmx && ctx->universe < ctx->dmx->size()) {
                const auto rounded = static_cast<int>(std::lround(value));
                (*ctx->dmx)[ctx->universe].set(ctx->channel, static_cast<std::uint8_t>(std::clamp(rounded, 0, 255)));
            }
            return;
        case EngineParameterEndpointContext::Kind::none:
            return;
    }
}

struct EngineCoreTickContext {
    stageforge::CoreAutomationState<256>* automation{nullptr};
    stageforge::CoreParameterRegistry<256>* parameters{nullptr};
    stageforge::CoreRuntimeShow* runtime_show{nullptr};
    stageforge::CoreJournal<4096>* journal{nullptr};
};

void route_show_tick(void* raw, std::uint64_t show_ns) noexcept {
    auto* ctx = static_cast<EngineCoreTickContext*>(raw);
    if (!ctx) return;
    if (ctx->automation && ctx->parameters) ctx->parameters->apply_control(*ctx->automation, show_ns);
    if (ctx->runtime_show && ctx->runtime_show->activate_if_due(show_ns)) {
        const auto snapshot = ctx->runtime_show->snapshot();
        if (ctx->journal) (void)ctx->journal->append(stageforge::CoreJournalKind::runtime_swap, show_ns, 0, snapshot.generation, snapshot.source_revision);
    }
}

bool route_show_event(void* raw, const stageforge::ShowEvent& event, bool) noexcept {
    auto* context = static_cast<EngineShowDispatchContext*>(raw);
    if (!context || !context->core || !context->midi_ingress || !context->lighting_ingress || !context->cues ||
        !context->automation || !context->cue_graph || !context->journal || !context->cue_events || !context->automation_events) return false;
    switch (event.type) {
        case stageforge::ShowEventType::transport: {
            const auto action = static_cast<stageforge::CoreTransportAction>(event.payload.transport.action);
            const auto result = context->core->mutate_transport_scoped(
                stageforge::CoreCommandDomain::show_event,
                event.event_id, stageforge::core_any_revision, action, event.payload.transport.value);
            const bool ok = result.status == stageforge::CoreMutationStatus::applied || result.status == stageforge::CoreMutationStatus::duplicate;
            if (ok) (void)context->journal->append(stageforge::CoreJournalKind::transport, event.show_time_ns, event.event_id, 0, result.revision);
            return ok;
        }
        case stageforge::ShowEventType::midi: {
            const bool ok = context->midi_ingress->try_push(stageforge::MidiEvent{
                event.event_id, event.show_time_ns, event.payload.midi.status,
                event.payload.midi.data1, event.payload.midi.data2});
            if (ok) (void)context->journal->append(stageforge::CoreJournalKind::midi, event.show_time_ns, event.event_id, event.payload.midi.port, 0);
            return ok;
        }
        case stageforge::ShowEventType::lighting: {
            const bool ok = context->lighting_ingress->try_push(stageforge::LightingEvent{
                event.event_id, event.show_time_ns, event.payload.lighting.universe,
                event.payload.lighting.channel, event.payload.lighting.value});
            if(context->lighting_audit)context->lighting_audit->note_handoff(ok);
            if (ok) (void)context->journal->append(stageforge::CoreJournalKind::lighting, event.show_time_ns, event.event_id, event.payload.lighting.universe, 0);
            return ok;
        }
        case stageforge::ShowEventType::cue: {
            context->cues->apply(event);
            (void)context->journal->append(stageforge::CoreJournalKind::cue, event.show_time_ns, event.event_id, event.payload.cue.cue_id, context->cues->snapshot().transitions);
            if (context->show_loop) {
                (void)context->cue_graph->expand(event.payload.cue.cue_id, event.event_id, event.show_time_ns,
                    [&](const stageforge::ShowEvent& derived) noexcept { return context->show_loop->schedule_derived(derived); });
            }
            return context->cue_events->try_push(event);
        }
        case stageforge::ShowEventType::automation: {
            const auto applied = context->automation->apply(event);
            if (!applied.applied()) return false;
            (void)context->journal->append(stageforge::CoreJournalKind::automation, event.show_time_ns, event.event_id,
                                           event.payload.automation.parameter_id, applied.revision);
            (void)context->automation_events->try_push(event); // compatibility observation queue only
            return true;
        }
        case stageforge::ShowEventType::sampler: {
            if(!context->sampler)return false;
            stageforge::SamplerCommandKind action=stageforge::SamplerCommandKind::trigger;
            if(event.payload.sampler.action==stageforge::ShowSamplerAction::stop_sample)action=stageforge::SamplerCommandKind::stop_sample;
            else if(event.payload.sampler.action==stageforge::ShowSamplerAction::stop_all)action=stageforge::SamplerCommandKind::stop_all;
            const bool ok=context->sampler->submit({action,event.event_id,event.payload.sampler.sample_id,event.payload.sampler.velocity,event.payload.sampler.note});
            if(ok)(void)context->journal->append(stageforge::CoreJournalKind::sampler,event.show_time_ns,event.event_id,event.payload.sampler.sample_id,0);
            return ok;
        }
    }
    return false;
}

struct EngineAudioRenderContext {
    stageforge::AudioGraph* graph{nullptr};
    stageforge::TransportClock* clock{nullptr};
    stageforge::CoreAutomationState<256>* automation{nullptr};
    stageforge::CoreParameterRegistry<256>* parameters{nullptr};
    stageforge::CoreEffectChain<16>* effects{nullptr};
    EngineEffectDelayTransaction* effect_delay_transaction{nullptr};
    std::uint8_t delay_path{0};
    stageforge::DawPlaybackQueue<8192,32>* daw_playback{nullptr};
    stageforge::SamplerVoiceEngine<64,32,1025>* sampler{nullptr};
    stageforge::StreamingVoiceEngine<16,256,9>* streaming_voices{nullptr};
    stageforge::RealtimeAudit* realtime_audit{nullptr};
    std::array<EngineAudioInputState*, kAudioInputSlots> inputs{};
    std::uint8_t reader{0};
    std::atomic<std::uint8_t> output{0};
    std::atomic<std::uint64_t> drift_start_ns{0};
    std::atomic<std::uint64_t> drift_last_ns{0};
    std::atomic<std::uint64_t> drift_frames{0};
    std::atomic<double> expected_sample_rate{0.0};
    std::atomic<double> measured_rate_ppm{0.0};
    std::atomic<double> correction_ppm{0.0};
    std::atomic<bool> drift_enabled{true};
    std::atomic<double> max_correction_ppm{2000.0};
    std::atomic<double> queue_gain_ppm{1000.0};
    std::atomic<std::uint32_t> source_frames_last{0};
    std::atomic<std::uint64_t> compensated_blocks{0};
    std::atomic<std::uint64_t> first_render_show_ns{0};
    std::atomic<std::uint64_t> last_render_show_ns{0};
    std::atomic<std::uint64_t> last_block_end_show_ns{0};
    stageforge::AdaptiveDriftController drift_controller{};
    double canonical_frame_fraction{0.0};
    std::array<double, kAudioInputSlots> input_frame_fraction{};
    std::array<float, 8192> left{};
    std::array<float, 8192> right{};
    std::array<float, 8192> sink_left{};
    std::array<float, 8192> sink_right{};
    std::array<float, 8192> playback_left{};
    std::array<float, 8192> playback_right{};
    std::array<float, 8192> sampler_left{};
    std::array<float, 8192> sampler_right{};
    std::array<float, 8192> streaming_left{};
    std::array<float, 8192> streaming_right{};
    std::array<std::array<float, 8192>, kAudioInputSlots> input_left{};
    std::array<std::array<float, 8192>, kAudioInputSlots> input_right{};
    std::array<std::array<float, 16384>, kAudioInputSlots> raw_input_left{};
    std::array<std::array<float, 16384>, kAudioInputSlots> raw_input_right{};
};

void capture_audio_packet(void* raw, const float* interleaved, std::uint32_t frames,
                          std::uint32_t channels, const stageforge::CapturePacketInfo& info) noexcept {
    const auto started=std::chrono::steady_clock::now();
    auto* state = static_cast<EngineAudioInputState*>(raw);
    if (!state)return;
    const auto result=stageforge::submit_capture_packet(
        state->ring,state->daw_recording,state->recording_track,state->recording_sequence,
        state->recording_frame,state->recording_generation,interleaved,frames,channels,info);
    const auto duration=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count());
    state->audit.finish(frames,result.blocks,result.rejected,result.nonfinite_samples,duration);
}

void capture_audio(void* raw, const float* interleaved, std::uint32_t frames, std::uint32_t channels) noexcept {
    capture_audio_packet(raw,interleaved,frames,channels,stageforge::CapturePacketInfo{});
}

#if defined(_WIN32) || defined(__APPLE__)
void capture_native_audio(const float* interleaved, std::uint32_t frames,
                          std::uint32_t channels, const stageforge::CapturePacketInfo& info,
                          void* raw) noexcept {
    capture_audio_packet(raw,interleaved,frames,channels,info);
}
#endif

struct EngineEffectProcessContext { stageforge::CoreEffectChain<16>* chain; std::uint64_t show_ns; };
void process_output_effects(void* raw, std::uint8_t, float* left, float* right, std::size_t frames) noexcept {
    auto* context=static_cast<EngineEffectProcessContext*>(raw);if(!context||!context->chain)return;
    float* channels[2]{left,right};(void)context->chain->process(channels,2,static_cast<std::uint32_t>(frames),context->show_ns);
}

void render_audio(void* raw, float* interleaved, std::uint32_t frames, std::uint32_t channels) noexcept {
    auto* context = static_cast<EngineAudioRenderContext*>(raw);
    if (!context || !context->graph || !interleaved || frames == 0 || channels == 0 || frames > context->left.size()) {
        if (interleaved && frames && channels) {
            std::fill_n(interleaved, static_cast<std::size_t>(frames) * channels, 0.0F);
        }
        return;
    }
    stageforge::RealtimeQualificationScope qualification_scope(context->realtime_audit);
    const auto callback_begin_ns=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());
    const double sink_rate=context->expected_sample_rate.load(std::memory_order_relaxed);
    const double internal_exact=sink_rate>0.0?static_cast<double>(frames)*stageforge::canonical_audio_sample_rate/sink_rate+context->canonical_frame_fraction:0.0;
    const auto internal_frames=internal_exact>0.0?static_cast<std::uint32_t>(std::floor(internal_exact)):0U;
    context->canonical_frame_fraction=internal_exact-static_cast<double>(internal_frames);
    if(internal_frames==0||internal_frames>context->left.size()){
        std::fill_n(interleaved,static_cast<std::size_t>(frames)*channels,0.0F);return;
    }
    const auto now_ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
    std::uint64_t render_show_ns = 0;
    if (context->clock) {
        const auto show = context->clock->snapshot();
        const auto show_ns = static_cast<std::uint64_t>(std::max(0.0, show.show_seconds) * 1'000'000'000.0);
        render_show_ns = show_ns;
        if (context->automation && context->parameters) context->parameters->apply_realtime(*context->automation, show_ns);
        std::uint64_t expected_zero = 0;
        context->first_render_show_ns.compare_exchange_strong(expected_zero, show_ns, std::memory_order_relaxed);
        context->last_render_show_ns.store(show_ns, std::memory_order_relaxed);
        const auto block_ns = static_cast<std::uint64_t>((static_cast<double>(internal_frames) / stageforge::canonical_audio_sample_rate) * 1'000'000'000.0);
        context->last_block_end_show_ns.store(show_ns + block_ns, std::memory_order_relaxed);
    }
    std::uint64_t start_ns = context->drift_start_ns.load(std::memory_order_relaxed);
    if (start_ns == 0) {
        context->drift_start_ns.compare_exchange_strong(start_ns, now_ns, std::memory_order_relaxed);
    } else {
        context->drift_frames.fetch_add(frames, std::memory_order_relaxed);
    }
    context->drift_last_ns.store(now_ns, std::memory_order_relaxed);

    double measured_rate_ppm = context->measured_rate_ppm.load(std::memory_order_relaxed);
    bool rate_measured = false;
    const auto origin_ns = context->drift_start_ns.load(std::memory_order_relaxed);
    const auto measured_frames = context->drift_frames.load(std::memory_order_relaxed);
    const auto expected_rate = context->expected_sample_rate.load(std::memory_order_relaxed);
    if (origin_ns > 0 && now_ns > origin_ns && measured_frames > 0 && expected_rate > 0.0) {
        const double elapsed = static_cast<double>(now_ns - origin_ns) / 1'000'000'000.0;
        if (elapsed >= 0.05) {
            const double observed_rate = static_cast<double>(measured_frames) / elapsed;
            measured_rate_ppm = std::clamp(((observed_rate / expected_rate) - 1.0) * 1'000'000.0, -10000.0, 10000.0);
            context->measured_rate_ppm.store(measured_rate_ppm, std::memory_order_relaxed);
            rate_measured = true;
        }
    }

    std::size_t queued_total = 0;
    std::size_t active_inputs = 0;
    for (const auto* input : context->inputs) {
        if (!input || !input->enabled.load(std::memory_order_acquire)) continue;
        queued_total += input->ring.queued(context->reader);
        ++active_inputs;
    }
    const auto queue_target = static_cast<std::size_t>(internal_frames) * std::max<std::size_t>(1, active_inputs);
    if(context->realtime_audit&&queue_target&&queued_total>queue_target*4)context->realtime_audit->note_queue_pressure();
    double correction_ppm = 0.0;
    std::uint32_t source_frames = internal_frames;
    if (context->drift_enabled.load(std::memory_order_relaxed)) {
        correction_ppm = context->drift_controller.update(measured_rate_ppm, rate_measured, queued_total, queue_target);
        source_frames = context->drift_controller.source_frames_for(internal_frames);
    }
    context->correction_ppm.store(correction_ppm, std::memory_order_relaxed);
    context->source_frames_last.store(source_frames, std::memory_order_relaxed);
    context->compensated_blocks.store(context->drift_controller.compensated_blocks(), std::memory_order_relaxed);

    const std::uint8_t output_id = context->output.load(std::memory_order_acquire);
    stageforge::AudioOutputBlock output{output_id, context->left.data(), context->right.data()};
    std::array<stageforge::AudioSourceBlock, kAudioInputSlots+2> sources{};
    std::size_t source_count = 0;
    if(context->daw_playback){context->daw_playback->render(context->playback_left.data(),context->playback_right.data(),internal_frames);sources[source_count++]={23,context->playback_left.data(),context->playback_right.data()};}
    if(context->sampler){context->sampler->render(context->sampler_left.data(),context->sampler_right.data(),internal_frames);sources[source_count++]={22,context->sampler_left.data(),context->sampler_right.data()};}
    if(context->streaming_voices){context->streaming_voices->render(context->streaming_left.data(),context->streaming_right.data(),internal_frames);sources[source_count++]={23,context->streaming_left.data(),context->streaming_right.data()};}
    for (std::size_t slot = 0; slot < kAudioInputSlots; ++slot) {
        auto* input = context->inputs[slot];
        if (!input || !input->enabled.load(std::memory_order_acquire)) continue;
        const double input_rate=input->sample_rate.load(std::memory_order_acquire);
        const double input_exact=static_cast<double>(source_frames)*input_rate/stageforge::canonical_audio_sample_rate+context->input_frame_fraction[slot];
        const auto input_frames=static_cast<std::uint32_t>(std::floor(input_exact));
        context->input_frame_fraction[slot]=input_exact-static_cast<double>(input_frames);
        if(input_frames==0||input_frames>context->raw_input_left[slot].size()){
            std::fill_n(context->input_left[slot].data(),internal_frames,0.0F);
            std::fill_n(context->input_right[slot].data(),internal_frames,0.0F);
            sources[source_count++]={input->source.load(std::memory_order_acquire),context->input_left[slot].data(),context->input_right[slot].data()};
            continue;
        }
        if (input_frames == internal_frames) {
            input->ring.pop_planar(context->reader, context->input_left[slot].data(), context->input_right[slot].data(), internal_frames);
        } else {
            input->ring.pop_planar(context->reader, context->raw_input_left[slot].data(), context->raw_input_right[slot].data(), input_frames);
            stageforge::resample_planar_sinc(
                context->raw_input_left[slot].data(), context->raw_input_right[slot].data(), input_frames,
                context->input_left[slot].data(), context->input_right[slot].data(), internal_frames);
        }
        sources[source_count++] = stageforge::AudioSourceBlock{
            input->source.load(std::memory_order_acquire),
            context->input_left[slot].data(),
            context->input_right[slot].data()};
    }
    EngineEffectProcessContext effect_context{context->effects,render_show_ns};
    // Overload is advisory here. No effect descriptor currently grants permission
    // to shed processing or provides a latency-preserving bypass transition.
    // Skipping the whole chain could remove essential processing from the show.
    const bool transaction_pinned=!context->effect_delay_transaction||context->effect_delay_transaction->begin(context->delay_path,render_show_ns);
    context->graph->process(std::span<const stageforge::AudioSourceBlock>(sources.data(), source_count), std::span<stageforge::AudioOutputBlock>(&output, 1), internal_frames,
                            context->effects ? &process_output_effects : nullptr, &effect_context);
    if(context->effect_delay_transaction&&transaction_pinned)(void)context->effect_delay_transaction->end(context->delay_path,context->left.data(),context->right.data(),internal_frames);
    if(internal_frames==frames){std::copy_n(context->left.data(),frames,context->sink_left.data());std::copy_n(context->right.data(),frames,context->sink_right.data());}
    else{stageforge::resample_planar_sinc(context->left.data(),context->right.data(),internal_frames,context->sink_left.data(),context->sink_right.data(),frames);}
    for (std::uint32_t frame = 0; frame < frames; ++frame) {
        const std::size_t base = static_cast<std::size_t>(frame) * channels;
        float left= context->sink_left[frame],right=context->sink_right[frame];std::uint64_t invalid=0;if(!std::isfinite(left)){left=0;invalid++;}if(!std::isfinite(right)){right=0;invalid++;}if(invalid&&context->realtime_audit)context->realtime_audit->note_nonfinite(invalid);
        if (channels == 1) {
            // v1 stereo-to-mono matrix: equal-power is intentionally not
            // invented here; use the deterministic arithmetic mean declared
            // by the explicit conversion contract.
            interleaved[base] = 0.5F * (left + right);
        } else {
            // v1 explicit multichannel matrix: canonical L/R feed device
            // channels 0/1 and all additional device channels are silent.
            interleaved[base] = left;
            interleaved[base + 1] = right;
            for (std::uint32_t channel = 2; channel < channels; ++channel) interleaved[base + channel] = 0.0F;
        }
    }
    if(context->realtime_audit){const auto callback_end_ns=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());const double deadline_rate=sink_rate>0?sink_rate:stageforge::canonical_audio_sample_rate;const auto deadline_ns=static_cast<std::uint64_t>(static_cast<double>(frames)/deadline_rate*1'000'000'000.0);context->realtime_audit->finish(callback_end_ns-callback_begin_ns,deadline_ns);}
}

#if defined(_WIN32) || defined(__APPLE__)
void render_native_audio(float* interleaved, std::uint32_t frames,
                         std::uint32_t channels, void* raw) noexcept {
    render_audio(raw, interleaved, frames, channels);
}
#endif

template <typename T>
bool parse_number(std::string_view text, T& value) {
    const auto* first = text.data();
    const auto* last = text.data() + text.size();
    auto result = std::from_chars(first, last, value);
    return result.ec == std::errc{} && result.ptr == last;
}

template <>
bool parse_number<double>(std::string_view text, double& value) {
    try {
        std::size_t used = 0;
        value = std::stod(std::string(text), &used);
        return used == text.size();
    } catch (...) {
        return false;
    }
}

template <>
bool parse_number<float>(std::string_view text, float& value) {
    double parsed = 0.0;
    if (!parse_number(text, parsed)) {
        return false;
    }
    value = static_cast<float>(parsed);
    return true;
}

std::vector<std::string> split(const std::string& line) {
    std::istringstream stream(line);
    std::vector<std::string> parts;
    std::string part;
    while (stream >> part) {
        parts.push_back(part);
    }
    return parts;
}

bool decode_hex_pcm(std::string_view text,float* left,float* right,std::uint32_t frames) {
    const std::size_t bytes=static_cast<std::size_t>(frames)*2U*sizeof(float);if(!left||!right||text.size()!=bytes*2U)return false;
    auto nibble=[](char ch)->int{if(ch>='0'&&ch<='9')return ch-'0';if(ch>='a'&&ch<='f')return ch-'a'+10;if(ch>='A'&&ch<='F')return ch-'A'+10;return -1;};
    std::array<std::uint8_t,8192*2*sizeof(float)> raw{};for(std::size_t i=0;i<bytes;++i){const int high=nibble(text[i*2]),low=nibble(text[i*2+1]);if(high<0||low<0)return false;raw[i]=static_cast<std::uint8_t>((high<<4)|low);}
    for(std::uint32_t i=0;i<frames;++i){std::memcpy(&left[i],raw.data()+(i*2)*sizeof(float),sizeof(float));std::memcpy(&right[i],raw.data()+(i*2+1)*sizeof(float),sizeof(float));if(!std::isfinite(left[i])||!std::isfinite(right[i]))return false;}return true;
}
std::string encode_hex_pcm(const float*left,const float*right,std::uint32_t frames){static constexpr char digits[]="0123456789abcdef";std::string result;result.reserve(static_cast<std::size_t>(frames)*2*sizeof(float)*2);for(std::uint32_t i=0;i<frames;++i)for(float value:{left[i],right[i]}){std::array<std::uint8_t,sizeof(float)>bytes{};std::memcpy(bytes.data(),&value,sizeof(float));for(auto byte:bytes){result.push_back(digits[byte>>4]);result.push_back(digits[byte&15]);}}return result;}

void ok(std::string_view payload = {}) {
    std::cout << "OK";
    if (!payload.empty()) {
        std::cout << ' ' << payload;
    }
    std::cout << '\n' << std::flush;
}

void error(std::string_view code, std::string_view message) {
    std::cout << "ERR code=" << code << " message=";
    for (char ch : message) {
        std::cout << (ch == ' ' ? '_' : ch);
    }
    std::cout << '\n' << std::flush;
}

std::string token_safe(std::string_view value) {
    std::string result(value);
    for (auto& ch : result) {
        if (ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r') {
            ch = '_';
        }
    }
    return result;
}

std::string_view clock_state_name(stageforge::ClockDisciplineState state) {
    switch (state) {
        case stageforge::ClockDisciplineState::free_running: return "free";
        case stageforge::ClockDisciplineState::locked: return "locked";
        case stageforge::ClockDisciplineState::holdover: return "holdover";
    }
    return "free";
}

void write_time(const stageforge::TransportClock& clock) {
    const auto snapshot = clock.snapshot();
    std::cout << "OK running=" << (clock.running() ? 1 : 0)
              << " seconds=" << std::fixed << std::setprecision(6) << snapshot.show_seconds
              << " bpm=" << std::setprecision(3) << snapshot.bpm
              << " sample=" << snapshot.sample_position
              << " monotonicNs=" << snapshot.monotonic_ns << '\n' << std::flush;
}

struct EngineMidiClockSink {stageforge::MidiScheduler<1024>* scheduler{nullptr};};
bool schedule_midi_clock_pulse(void* raw,std::uint64_t sequence,std::uint64_t show_ns) noexcept {
    auto* context=static_cast<EngineMidiClockSink*>(raw);
    return context&&context->scheduler&&context->scheduler->schedule({0xD000000000000000ULL|sequence,show_ns,0xF8,0,0});
}

void write_monitor(std::string_view player_id, const stageforge::MonitorBus& bus) {
    const auto snapshot = bus.snapshot();
    std::cout << "OK player=" << player_id
              << " master=" << snapshot.master
              << " self=" << snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::self)]
              << " vocals=" << snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::vocals)]
              << " band=" << snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::band)]
              << " click=" << snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::click)]
              << " talkback=" << snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::talkback)]
              << " ambient=" << snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::ambient)]
              << " muted=" << (snapshot.muted ? 1 : 0) << '\n' << std::flush;
}

} // namespace

int main(int argc, char** argv) {
    if (argc > 1 && std::string_view(argv[1]) != "--stdio") {
        std::cerr << "usage: stageforge_engine [--stdio]\n";
        return 2;
    }

    const char* expected_ipc_token_env = std::getenv("STAGEFORGE_IPC_TOKEN");
    const std::string expected_ipc_token = expected_ipc_token_env ? expected_ipc_token_env : "";
    bool ipc_authenticated = expected_ipc_token.empty();

    stageforge::CoreControlState core(stageforge::canonical_audio_sample_rate, 120.0);
    auto& clock = core.transport();
    stageforge::ClockDiscipline clock_discipline;
    stageforge::TransportDiscipline transport_discipline;
    stageforge::MidiClock24Ppqn midi_clock;
    std::string clock_source{"local"};
    auto& monitors = core.monitors();
    stageforge::MonitorGraphRouter monitor_router;
    stageforge::MidiScheduler<1024> midi;
    EngineMidiClockSink midi_clock_sink{&midi};
    stageforge::LightingScheduler<2048> lighting;
    stageforge::SpscQueue<stageforge::MidiEvent, 1024> midi_event_ingress;
    stageforge::SpscQueue<stageforge::LightingEvent, 2048> lighting_event_ingress;
    stageforge::CoreCueState cue_state;
    stageforge::CoreAutomationState<256> automation_state;
    stageforge::CoreParameterRegistry<256> parameter_registry;
    stageforge::CoreCueActionGraph<128> cue_graph;
    stageforge::CoreRuntimeShow runtime_show;
    stageforge::CoreRoutingState<128> routing_state;
    stageforge::CoreJournal<4096> core_journal;
    stageforge::CoreShadowRenderPlanner<64> shadow_planner;
    stageforge::CoreShadowPrebuffer<64> shadow_prebuffer;
    stageforge::CorePlannedHandoff planned_handoff;
    stageforge::LeUwbHub<64> le_uwb_hub;
    stageforge::LeUwbHardwareManager<64> le_uwb_hardware(le_uwb_hub);
    stageforge::UserProfileCustomization<128> user_profile;
    stageforge::InteroperabilityHandshake<64,32> interoperability;
    stageforge::AuthenticatedInteropSession interop_session;
    stageforge::SessionChannelGuard<64> session_channel;
    static stageforge::DawPlaybackQueue<8192,32> daw_playback;
    static stageforge::DawRecordingQueue<8,256,64> daw_recording;
    static stageforge::SamplerVoiceEngine<64,32,1025> sampler;
    static stageforge::StreamingVoiceEngine<16,256,9> streaming_voices;
    static std::array<EngineSamplerAsset,32> sampler_assets{};
    EngineSamplerAsset* staged_sampler_asset=nullptr;
    std::array<std::uint64_t,64> staged_channel_capabilities{};std::size_t staged_channel_capability_count=0;
    std::uint64_t staged_channel_high=0,staged_channel_low=0,staged_channel_epoch=0;
    stageforge::HandshakeOffer<64> staged_local_offer{},staged_remote_offer{};
    stageforge::SpscQueue<stageforge::ShowEvent, 256> cue_events;
    stageforge::SpscQueue<stageforge::ShowEvent, 256> automation_events;
    stageforge::LightingIngressAudit lighting_ingress_audit;
    EngineShowDispatchContext show_dispatch_context{&core, &midi_event_ingress, &lighting_event_ingress, &cue_state, &automation_state, &cue_graph, nullptr, &core_journal, &cue_events, &automation_events,&sampler,&lighting_ingress_audit};
    EngineCoreTickContext core_tick_context{&automation_state, &parameter_registry, &runtime_show, &core_journal};
    EngineShowLoop show_loop(clock, &route_show_event, &show_dispatch_context, &route_show_tick, &core_tick_context);
    show_dispatch_context.show_loop = &show_loop;
    stageforge::MidiLearnRouter<512,1024> midi_mapping;
    midi_mapping.configure_master(120.0,0,0x0AB5);
    stageforge::MidiMappedActionDispatcher midi_action_dispatcher(&submit_midi_mapped_event,&show_loop,stable_token_id("midi-learn"));
    stageforge::SpscQueue<stageforge::CapturedMidiInput,2049> midi_observer_queue;
    std::array<stageforge::DmxUniverseState, 16> dmx_universes{};
    std::array<EngineParameterEndpointContext, 256> parameter_endpoint_contexts{};
    std::size_t parameter_endpoint_context_count = 0;
    std::array<std::uint8_t, 16> artnet_sequences{};
    stageforge::ArtNetUdpOutput artnet_output;
    std::array<std::uint8_t, 16> sacn_sequences{};
    stageforge::SacnUdpOutput sacn_output;
    std::array<std::uint8_t, 16> sacn_cid{};
    {
        std::random_device random;
        for (auto& byte : sacn_cid) byte = static_cast<std::uint8_t>(random());
        sacn_cid[6] = static_cast<std::uint8_t>((sacn_cid[6] & 0x0fu) | 0x40u);
        sacn_cid[8] = static_cast<std::uint8_t>((sacn_cid[8] & 0x3fu) | 0x80u);
    }
    enum class LightingNetworkProtocol : std::uint8_t { artnet = 0, sacn = 1 };
    LightingNetworkProtocol lighting_network_protocol = LightingNetworkProtocol::artnet;
    std::uint16_t sacn_universe_base = 1;
    stageforge::MidiInputOwner midi_inputs;
    stageforge::AudioDeviceManager audio_devices;
    audio_devices.scan();
    std::array<std::string, kAudioOutputSlots> selected_audio_outputs{};
    selected_audio_outputs[0] = "null-audio";
    stageforge::NullAudioDevice audio;
    stageforge::AudioGraph audio_graph;
    std::array<stageforge::CoreEffectChain<16>, kAudioOutputSlots> effect_chains{};
    static EngineEffectDelayTransaction effect_delay_transaction(effect_chains);
    std::array<stageforge::RealtimeAudit,kAudioOutputSlots> realtime_audits{};
    std::array<EngineAudioInputState, kAudioInputSlots> audio_inputs{};
    std::array<EngineAudioRenderContext, kAudioOutputSlots> audio_render_contexts{};
    for (std::size_t output_slot = 0; output_slot < kAudioOutputSlots; ++output_slot) {
        auto& context = audio_render_contexts[output_slot];
        context.graph = &audio_graph;
        context.clock = &clock;
        context.automation = &automation_state;
        context.parameters = &parameter_registry;
        context.effects = &effect_chains[output_slot];
        context.effect_delay_transaction=&effect_delay_transaction;
        context.delay_path=static_cast<std::uint8_t>(output_slot);
        context.realtime_audit=&realtime_audits[output_slot];
        context.daw_playback = output_slot==0 ? &daw_playback : nullptr;
        context.sampler = output_slot==0 ? &sampler : nullptr;
        context.streaming_voices = output_slot==0 ? &streaming_voices : nullptr;
        context.reader = static_cast<std::uint8_t>(output_slot);
        context.output.store(static_cast<std::uint8_t>(output_slot == 0 ? 0 : output_slot), std::memory_order_relaxed);
        for (std::size_t input_slot = 0; input_slot < kAudioInputSlots; ++input_slot) context.inputs[input_slot] = &audio_inputs[input_slot];
    }
    for (std::size_t slot = 0; slot < kAudioInputSlots; ++slot) {
        audio_inputs[slot].source.store(static_cast<std::uint8_t>(24 + slot), std::memory_order_relaxed);
        audio_inputs[slot].enabled.store(false, std::memory_order_relaxed);
        audio_inputs[slot].daw_recording=&daw_recording;
        audio_inputs[slot].recording_track=static_cast<std::uint8_t>(slot);
    }
    std::array<stageforge::AlsaAudioOutput, kAudioOutputSlots> alsa_outputs{};
    std::array<stageforge::AlsaAudioInput, kAudioInputSlots> alsa_inputs{};
#if defined(_WIN32) || defined(__APPLE__)
    using NativeInputOwner = stageforge::CaptureServiceOwner<stageforge::NativeCaptureService>;
    using NativeOutputOwner = stageforge::CaptureServiceOwner<stageforge::NativePlaybackService>;
    std::array<std::unique_ptr<NativeInputOwner>, kAudioInputSlots> native_inputs{};
    std::array<std::unique_ptr<NativeOutputOwner>, kAudioOutputSlots> native_outputs{};
#endif
    std::array<std::string, kAudioInputSlots> selected_audio_inputs{};
    std::array<std::string, kAudioOutputSlots> execution_audio_backends{};
    execution_audio_backends.fill("none");
    execution_audio_backends[0] = "null-audio";
    std::array<std::string, kAudioInputSlots> execution_audio_input_backends{};
    execution_audio_input_backends.fill("none");
    audio_graph.set_route_gain(0, 0, 1.0F);
    audio_graph.set_route_gain(23, 0, 1.0F);
    audio_graph.set_route_gain(22, 0, 1.0F);
    audio_graph.set_output_master(0, 1.0F);
    audio_graph.set_limiter_ceiling_db(0, -1.0F);
    audio.open({stageforge::canonical_audio_sample_rate, 0, 2, 256});
    audio.start();

    std::uint64_t next_core_command_id = 1;
    std::vector<std::string> staged_monitor_players;
    std::uint64_t staged_cue_graph_id = 0;
    std::array<stageforge::CueAction, 32> staged_cue_actions{};
    std::size_t staged_cue_action_count = 0;
    std::array<stageforge::AudioRouteChange, 128> staged_audio_route_changes{};
    std::size_t staged_audio_route_change_count = 0;

    auto allocate_parameter_context = [&]() noexcept -> EngineParameterEndpointContext* {
        if (parameter_endpoint_context_count >= parameter_endpoint_contexts.size()) return nullptr;
        return &parameter_endpoint_contexts[parameter_endpoint_context_count++];
    };

    auto ingest_midi_domain = [&]() noexcept {
        std::size_t count = 0;
        stageforge::MidiEvent event{};
        while (midi_event_ingress.try_pop(event)) {
            if (!midi.schedule(event)) break;
            ++count;
        }
Warning: truncated output (original token count: 6331)
Total output lines: 250

        return count;
    };
    auto ingest_lighting_domain = [&]() noexcept {
        const auto started=std::chrono::steady_clock::now();
        std::size_t count = 0;
        stageforge::LightingEvent event{};
        while (lighting_event_ingress.try_pop(event)) {
            if (!lighting.schedule(event)) break;
            ++count;
        }
        const auto duration=static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-started).count());lighting_ingress_audit.note_drain(count,duration);return count;
    };
    auto route_captured_midi = [&]() noexcept {
        std::size_t captured = 0, mapped = 0;
        stageforge::CapturedMidiInput input{};
        while (midi_inputs.pop(input)) {
            ++captured;
            (void)midi_observer_queue.try_push(input);
            midi_mapping.process(stable_token_id(input.device_id.data()),input.message.status,input.message.data1,input.message.data2,input.message.show_time_ns);
            stageforge::MidiMappedAction action{};
            while (midi_mapping.pop(action)) {
                if (midi_action_dispatcher.dispatch(action,core.metrics().revision)) ++mapped;
            }
        }
        return std::pair<std::size_t,std::size_t>{captured,mapped};
    };

    if (!show_loop.start()) {
        std::cerr << "failed to start Core show execution loop\n";
        return 3;
    }

    std::string line;
    while (std::getline(std::cin, line)) {
        const auto parts = split(line);
        if (parts.empty()) {
            continue;
        }
        const auto& command = parts[0];

        if (!ipc_authenticated) {
            if (command == "AUTH" && parts.size() == 2 && parts[1] == expected_ipc_token) {
                ipc_authenticated = true;
                ok("authenticated=1");
            } else {
                error("permission", "native IPC authentication required");
            }
            continue;
        }

        // Each handled command ends this iteration; avoid a compiler-depth-limited else chain.
        if (command == "AUTH") {
            ok("authenticated=1");
            continue;
        }
        if (command == "HELLO") {
            ok(std::string("engineVersion=") + std::string(kEngineVersion) + " protocol=1 coreControl=1 showEvents=1 showLoop=1 cueState=1 automationState=1 parameterRegistry=1 cueActions=1 runtimeShow=1 routingTx=1 coreJournal=1 shadowPlanner=1 shadowPrebuffer=1 plannedHandoff=1 effectChain=1 canonicalAudio=1 physicalPcmConversion=1 leUwbHub=1 leIsoHardware=1 uwbHardwareBridge=1 userProfile=1 interoperabilityHandshake=1 authenticatedInteropSession=1 profileProjection=1 hardwareBench=1 sessionChannel=1 localIpc=1 persistentSecurity=1 isolatedPluginHost=1 platformQualification=1 realtimeAudit=1 realtimeQualification=" + std::string(stageforge::RealtimeAudit::qualification_enabled()?"1":"0") + " ingressAudit=1 dawSession=1 dawRenderPlan=1 dawMedia=1 dawEditHistory=1 dawRenderer=1 dawRecording=1 dawTempoMap=1 dawMediaLibrary=1 dawPluginCatalog=1 dawRecovery=1 dawStreamRenderer=1 dawPlaybackPrefetch=1 dawRecordingSpool=1 dawPlaybackQueue=1 dawMultitrackCapture=1 dawArrangementProducer=1 dawPcmBlockTransfer=1 dawCaptureDrain=1 dawPunchLoopCapture=1 pluginDelayCompensation=1 pluginDelayGraph=1 midiLearnMapping=1 masterMusicalSync=1 nativeMidiPerformance=1 samplerVoiceEngine=1 transportDiscipline=1 midiClock24Ppqn=1 engineRate=192000 sampleFormat=float32");
            continue;
        }
        if (command == "PING") {
            ok("pong=1");
            continue;
        }
        if(command=="SAMPLER_LOAD_BEGIN"&&parts.size()==8){
            std::uint64_t sample_id=0;unsigned int total=0,choke=0,looped=0,loop_begin=0,loop_end=0,crossfade=0;
            if(!parse_number(parts[1],sample_id)||!parse_number(parts[2],total)||!parse_number(parts[3],choke)||!parse_number(parts[4],looped)||
               !parse_number(parts[5],loop_begin)||!parse_number(parts[6],loop_end)||!parse_number(parts[7],crossfade)||sample_id==0||total==0||total>kSamplerAssetFrames||
               choke>255||looped>1||loop_begin>=total||loop_end>total||(looped&&loop_end<=loop_begin)||crossfade>65535||staged_sampler_asset){error("argument","invalid sampler asset");continue;}
            EngineSamplerAsset*slot=nullptr;for(auto&candidate:sampler_assets)if(candidate.sample_id==0&&!candidate.staging&&!candidate.published){slot=&candidate;break;}
            if(!slot){error("capacity","sampler asset capacity");continue;}slot->sample_id=sample_id;slot->total_frames=total;slot->written_frames=0;slot->choke_group=static_cast<std::uint8_t>(choke);
            slot->looped=looped!=0;slot->loop_begin=loop_begin;slot->loop_end=looped?loop_end:total;slot->crossfade_frames=static_cast<std::uint16_t>(crossfade);slot->staging=true;staged_sampler_asset=slot;ok("staging=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="SAMPLER_LOAD_PCM"&&parts.size()==4){
            unsigned int offset=0,frames=0;if(!staged_sampler_asset||!parse_number(parts[1],offset)||!parse_number(parts[2],frames)||frames==0||frames>8192||
               offset!=staged_sampler_asset->written_frames||offset+frames>staged_sampler_asset->total_frames||
               !decode_hex_pcm(parts[3],staged_sampler_asset->left.data()+offset,staged_sampler_asset->right.data()+offset,frames)){error("argument","invalid sampler PCM block");continue;}
            staged_sampler_asset->written_frames+=frames;ok(std::string("writtenFrames=")+std::to_string(staged_sampler_asset->written_frames));
            continue;
        }
        if(command=="SAMPLER_LOAD_COMMIT"&&parts.size()==1){
            if(!staged_sampler_asset||staged_sampler_asset->written_frames!=staged_sampler_asset->total_frames){error("state","sampler asset incomplete");continue;}
            const stageforge::SamplerSampleDescriptor descriptor{staged_sampler_asset->sample_id,staged_sampler_asset->left.data(),staged_sampler_asset->right.data(),staged_sampler_asset->total_frames,
                staged_sampler_asset->loop_begin,staged_sampler_asset->loop_end,staged_sampler_asset->crossfade_frames,staged_sampler_asset->choke_group,staged_sampler_asset->looped};
            if(!sampler.register_sample(descriptor)){error("conflict","sampler asset refused");continue;}staged_sampler_asset->staging=false;staged_sampler_asset->published=true;staged_sampler_asset=nullptr;ok("committed=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="SAMPLER_TRIGGER"&&parts.size()==6){
            stageforge::ShowEvent event{};unsigned int note=0;float velocity=0;
            if(!parse_number(parts[1],event.event_id)||!parse_number(parts[2],event.show_time_ns)||!parse_number(parts[3],event.payload.sampler.sample_id)||
               !parse_number(parts[4],velocity)||!parse_number(parts[5],note)||note>127||!std::isfinite(velocity)){error("argument","invalid sampler trigger");continue;}
            event.type=stageforge::ShowEventType::sampler;event.priority=SF_PRIORITY_SHOW;event.revision=core.metrics().revision;event.payload.sampler.velocity=velocity;event.payload.sampler.note=static_cast<std::uint8_t>(note);event.payload.sampler.action=stageforge::ShowSamplerAction::trigger;
            if(!show_loop.submit(event)){error("busy","sampler trigger ingress full");continue;}ok("queued=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="SAMPLER_STOP"&&(parts.size()==3||parts.size()==4)){
            stageforge::ShowEvent event{};if(!parse_number(parts[1],event.event_id)||!parse_number(parts[2],event.show_time_ns)||(parts.size()==4&&!parse_number(parts[3],event.payload.sampler.sample_id))){error("argument","invalid sampler stop");continue;}
            event.type=stageforge::ShowEventType::sampler;event.priority=SF_PRIORITY_SHOW;event.revision=core.metrics().revision;event.payload.sampler.action=parts.size()==3?stageforge::ShowSamplerAction::stop_all:stageforge::ShowSamplerAction::stop_sample;
            if(!show_loop.submit(event)){error("busy","sampler stop ingress full");continue;}ok("queued=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="SAMPLER_STATUS"&&parts.size()==1){
            const auto status=sampler.status();std::cout<<"OK samples="<<status.samples<<" activeVoices="<<status.active_voices<<" pendingVoices="<<status.pending_voices<<" queued="<<status.queued
                <<" submitted="<<status.submitted<<" renderedFrames="<<status.rendered_frames<<" completedVoices="<<status.completed_voices<<" stolenVoices="<<status.stolen_voices
                <<" chokedVoices="<<status.choked_voices<<" rejected="<<status.rejected_commands<<" overflows="<<status.queue_overflows<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="STREAM_VOICE_START"&&parts.size()==5){unsigned int slot=0,loop=0;std::uint64_t generation=0;float gain=0;if(!parse_number(parts[1],slot)||!parse_number(parts[2],generation)||!parse_number(parts[3],gain)||!parse_number(parts[4],loop)||slot>=16||loop>1||!streaming_voices.start(slot,generation,gain,loop!=0)){error("argument","streaming voice start refused");continue;}ok("queued=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="STREAM_VOICE_BLOCK"&&parts.size()==7){unsigned int slot=0,frames=0,terminal=0;stageforge::StreamingVoiceBlock<256>block{};if(!parse_number(parts[1],slot)||!parse_number(parts[2],block.generation)||!parse_number(parts[3],block.sequence)||!parse_number(parts[4],frames)||!parse_number(parts[5],terminal)||slot>=16||frames==0||frames>256||terminal>1||!decode_hex_pcm(parts[6],block.left.data(),block.right.data(),frames)){error("argument","invalid streaming voice block");continue;}block.frames=frames;block.terminal=terminal!=0;if(!streaming_voices.push(slot,block)){error("busy","streaming voice feed full");continue;}ok("queued=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="STREAM_VOICE_STOP"&&parts.size()==3){unsigned int slot=0;std::uint64_t generation=0;if(!parse_number(parts[1],slot)||!parse_number(parts[2],generation)||!streaming_voices.stop(slot,generation)){error("argument","streaming voice stop refused");continue;}ok("queued=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="STREAM_VOICE_STOP_ALL"&&parts.size()==1){if(!streaming_voices.stop_all()){error("busy","streaming voice command queue full");continue;}ok("queued=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="STREAM_VOICE_SLOT"&&parts.size()==2){unsigned int slot=0;std::uint64_t generation=0;bool active=false;if(!parse_number(parts[1],slot)||!streaming_voices.slot_status(slot,generation,active)){error("argument","invalid streaming voice slot");continue;}std::cout<<"OK slot="<<slot<<" generation="<<generation<<" active="<<(active?1:0)<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="STREAM_VOICE_STATUS"&&parts.size()==1){const auto status=streaming_voices.status();std::cout<<"OK activeVoices="<<status.active_voices<<" activeMask="<<status.active_mask<<" queuedBlocks="<<status.queued_blocks<<" starts="<<status.starts<<" stops="<<status.stops<<" renderedFrames="<<status.rendered_frames<<" starvedBlocks="<<status.starved_blocks<<" staleBlocks="<<status.stale_blocks<<" discontinuities="<<status.discontinuities<<" completedVoices="<<status.completed_voices<<" overflows="<<status.queue_overflows<<" diskIoInAudioCallback=0 physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="DAW_PLAYBACK_PUSH"&&parts.size()==6){std::uint64_t generation=0,start=0;std::uint32_t frames=0;float left=0,right=0;if(!parse_number(parts[1],generation)||!parse_number(parts[2],start)||!parse_number(parts[3],frames)||!parse_number(parts[4],left)||!parse_number(parts[5],right)||frames>8192){error("argument","invalid playback blo…331 tokens truncated…;
            continue;
        }
        if(command=="DAW_PLAYBACK_SEEK"&&parts.size()==2){std::uint64_t frame=0;if(!parse_number(parts[1],frame)){error("argument","invalid seek frame");continue;}daw_playback.seek(frame);ok("seeked=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="DAW_PLAYBACK_LOOP"&&parts.size()==3){std::uint64_t begin=0,end=0;if(!parse_number(parts[1],begin)||!parse_number(parts[2],end)||!daw_playback.set_loop(begin,end)){error("argument","invalid loop range");continue;}ok("looping=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="DAW_PLAYBACK_LOOP_CLEAR"){daw_playback.clear_loop();ok("looping=0 physicalOutputsArmed=0");
            continue;
        }
        if(command=="DAW_PLAYBACK_STATUS"){const auto s=daw_playback.status();std::cout<<"OK generation="<<s.generation<<" playheadFrame="<<s.playhead_frame<<" queuedBlocks="<<s.queued_blocks<<" renderedBlocks="<<s.rendered_blocks<<" renderedFrames="<<s.rendered_frames<<" underrunBlocks="<<s.underrun_blocks<<" discontinuities="<<s.discontinuities<<" seeks="<<s.seeks<<" loopWraps="<<s.loop_wraps<<" running="<<(s.running?1:0)<<" looping="<<(s.looping?1:0)<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="DAW_RECORD_ARM"&&parts.size()==3){unsigned int track=0,ack=0;if(!parse_number(parts[1],track)||!parse_number(parts[2],ack)||!daw_recording.arm(track,ack!=0)){error("permission","record arm refused");continue;}const auto generation=daw_recording.generation(track);for(auto&input:audio_inputs)if(input.recording_track==track){input.recording_generation.store(generation,std::memory_order_release);input.recording_sequence.store(0);input.recording_frame.store(0);}std::cout<<"OK armed=1 generation="<<generation<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="DAW_RECORD_DISARM"&&parts.size()==2){unsigned int track=0;if(!parse_number(parts[1],track)||track>=8){error("argument","invalid record track");continue;}daw_recording.disarm(track);ok("armed=0 physicalOutputsArmed=0");
            continue;
        }
        if(command=="DAW_RECORD_STATUS"&&parts.size()==2){unsigned int track=0;if(!parse_number(parts[1],track)||track>=8){error("argument","invalid record track");continue;}const auto s=daw_recording.status(track);std::cout<<"OK generation="<<s.generation<<" submitted="<<s.submitted<<" written="<<s.written<<" dropped="<<s.dropped<<" stale="<<s.stale<<" sequenceGaps="<<s.sequence_gaps<<" queued="<<s.queued<<" armed="<<(s.armed?1:0)<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="DAW_RECORD_POP"&&parts.size()==2){unsigned int track=0;if(!parse_number(parts[1],track)||track>=8){error("argument","invalid record track");continue;}stageforge::DawRecordingQueue<8,256,64>::Block block{};if(!daw_recording.pop(track,block)){error("empty","record queue empty");continue;}std::cout<<"OK generation="<<block.generation<<" sequence="<<block.sequence<<" showFrame="<<block.show_frame<<" frames="<<block.frames<<" pcm="<<encode_hex_pcm(block.left.data(),block.right.data(),block.frames)<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "PROFILE_CONFIG" && parts.size() == 3) {
            std::uint64_t profile_id=0,epoch=0;
            if(!parse_number(parts[1],profile_id)||!parse_number(parts[2],epoch)||!user_profile.configure(profile_id,epoch)){error("conflict","profile configuration refused");continue;}
            ok(std::string("profileId=")+std::to_string(profile_id)+" authorityEpoch="+std::to_string(epoch)+" physicalOutputsArmed=0");
            continue;
        }
        if (command == "PROFILE_SET" && parts.size() == 7) {
            stageforge::ProfilePreference preference{};unsigned int layer=0,type=0;
            if(!parse_number(parts[1],preference.namespace_id)||!parse_number(parts[2],preference.key_id)||!parse_number(parts[3],layer)||
               !parse_number(parts[4],preference.revision)||!parse_number(parts[5],type)||layer>4||type>3){error("argument","invalid profile preference");continue;}
            preference.layer=static_cast<stageforge::ProfileLayer>(layer);preference.type=static_cast<stageforge::ProfileValueType>(type);
            bool parsed=false;
            if(type<=1){parsed=parse_number(parts[6],preference.integer_value);if(type==0&&(preference.integer_value<0||preference.integer_value>1))parsed=false;}
            else if(type==2)parsed=parse_number(parts[6],preference.scalar_value);
            else parsed=parse_number(parts[6],preference.token_value);
            if(!parsed||!user_profile.set(preference)){error("conflict","profile preference refused");continue;}
            ok(std::string("revision=")+std::to_string(preference.revision)+" physicalOutputsArmed=0");
            continue;
        }
        if (command == "PROFILE_GET" && parts.size() == 3) {
            std::uint64_t namespace_id=0,key_id=0;stageforge::ProfilePreference preference{};
            if(!parse_number(parts[1],namespace_id)||!parse_number(parts[2],key_id)||!user_profile.resolve(namespace_id,key_id,preference)){error("not_found","profile preference unavailable");continue;}
            std::cout<<"OK namespaceId="<<preference.namespace_id<<" keyId="<<preference.key_id<<" layer="<<static_cast<unsigned int>(preference.layer)
                     <<" type="<<static_cast<unsigned int>(preference.type)<<" revision="<<preference.revision<<" integer="<<preference.integer_value
                     <<" scalar="<<preference.scalar_value<<" token="<<preference.token_value<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "PROFILE_CLEAR_LAYER" && parts.size() == 2) {
            unsigned int layer=0;if(!parse_number(parts[1],layer)||layer>4){error("argument","invalid profile layer");continue;}
            ok(std::string("removed=")+std::to_string(user_profile.clear_layer(static_cast<stageforge::ProfileLayer>(layer)))+" physicalOutputsArmed=0");
            continue;
        }
        if (command == "PROFILE_STATUS" && parts.size() == 1) {
            const auto status=user_profile.status();std::cout<<"OK configured="<<(status.configured?1:0)<<" profileId="<<status.profile_id<<" authorityEpoch="<<status.authority_epoch
                     <<" revision="<<status.revision<<" preferences="<<status.stored_preferences<<" accepted="<<status.accepted_updates<<" rejected="<<status.rejected_updates
                     <<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if ((command == "INTEROP_LOCAL_BEGIN"||command == "INTEROP_REMOTE_BEGIN") && parts.size() == 8) {
            stageforge::HandshakeOffer<64> offer{};unsigned int preserve=0,offline=0;
            if(!parse_number(parts[1],offer.participant_id)||!parse_number(parts[2],offer.protocol_min)||!parse_number(parts[3],offer.protocol_max)||
               !parse_number(parts[4],offer.profile_schema_min)||!parse_number(parts[5],offer.profile_schema_max)||!parse_number(parts[6],preserve)||
               !parse_number(parts[7],offline)||preserve>1||offline>1){error("argument","invalid interoperability offer");continue;}
            offer.preserves_unknown=preserve!=0;offer.offline_capable=offline!=0;
            if(command=="INTEROP_LOCAL_BEGIN")staged_local_offer=offer;else staged_remote_offer=offer;
            ok(std::string("staged=")+(command=="INTEROP_LOCAL_BEGIN"?"local":"remote")+" physicalOutputsArmed=0");
            continue;
        }
        if ((command == "INTEROP_LOCAL_CAP"||command == "INTEROP_REMOTE_CAP") && parts.size() == 3) {
            std::uint64_t capability=0;unsigned int required=0;auto& offer=command=="INTEROP_LOCAL_CAP"?staged_local_offer:staged_remote_offer;
            if(!parse_number(parts[1],capability)||!parse_number(parts[2],required)||capability==0||required>1||offer.capability_count>=offer.capabilities.size()){error("argument","invalid interoperability capability");continue;}
            offer.capabilities[offer.capability_count++]={capability,required!=0};ok(std::string("capabilities=")+std::to_string(offer.capability_count));
            continue;
        }
        if (command == "INTEROP_LOCAL_COMMIT" && parts.size() == 1) {
            if(!interoperability.configure_local(staged_local_offer)){error("argument","invalid local interoperability offer");continue;}ok("localCommitted=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "INTEROP_ADAPTER" && parts.size() == 4) {
            stageforge::HandshakeAdapter adapter{};unsigned int quality=0;
            if(!parse_number(parts[1],adapter.from)||!parse_number(parts[2],adapter.to)||!parse_number(parts[3],quality)||quality==0||quality>100){error("argument","invalid interoperability adapter");continue;}
            adapter.quality=static_cast<std::uint8_t>(quality);if(!interoperability.add_adapter(adapter)){error("busy","interoperability adapter refused");continue;}ok("adapterRegistered=1");
            continue;
        }
        if (command == "INTEROP_PLAN" && parts.size() == 1) {
            const auto plan=interoperability.negotiate(staged_remote_offer);
            std::cout<<"OK compatible="<<(plan.compatible?1:0)<<" protocolVersion="<<plan.protocol_version<<" profileSchemaVersion="<<plan.profile_schema_version
                     <<" direct="<<plan.direct_capabilities<<" translated="<<plan.translated_capabilities<<" unknownPreserved="<<plan.preserved_unknown_capabilities
                     <<" missingRequired="<<plan.missing_required<<" adapterQuality="<<static_cast<unsigned int>(plan.minimum_adapter_quality)
                     <<" unknownPreservation="<<(plan.unknown_preservation?1:0)<<" offlineCompatible="<<(plan.offline_compatible?1:0)<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "SESSION_OFFER" && parts.size() == 7) {
            std::uint64_t id=0,transcript=0,nonce=0,epoch=0,sequence=0,expires=0;
            if(!parse_number(parts[1],id)||!parse_number(parts[2],transcript)||!parse_number(parts[3],nonce)||!parse_number(parts[4],epoch)||!parse_number(parts[5],sequence)||!parse_number(parts[6],expires)||!interop_session.offer(id,transcript,nonce,epoch,sequence,expires)){error("conflict","session offer refused");continue;}ok("state=offered physicalOutputsArmed=0");
            continue;
        }
        if (command == "SESSION_AUTH" && parts.size() == 5) {
            unsigned int verified=0;std::uint64_t now=0,epoch=0,minimum_sequence=0;
            if(!parse_number(parts[1],verified)||verified>1||!parse_number(parts[2],now)||!parse_number(parts[3],epoch)||!parse_number(parts[4],minimum_sequence)||!interop_session.authenticate(verified!=0,now,epoch,minimum_sequence)){error("permission","session authentication refused");continue;}ok("state=authenticated physicalOutputsArmed=0");
            continue;
        }
        if (command == "SESSION_NEGOTIATE" && parts.size() == 6) {
            unsigned int compatible=0,protocol=0,schema=0;std::uint64_t profile_revision=0,registry_revision=0;
            if(!parse_number(parts[1],compatible)||compatible>1||!parse_number(parts[2],protocol)||!parse_number(parts[3],schema)||!parse_number(parts[4],profile_revision)||!parse_number(parts[5],registry_revision)||!interop_session.negotiate(compatible!=0,protocol,schema,profile_revision,registry_revision)){error("conflict","session negotiation refused");continue;}ok("state=negotiated physicalOutputsArmed=0");
            continue;
        }
        if (command == "SESSION_CONSENT" && parts.size() == 3) {
            unsigned int accepted=0;std::uint64_t projection=0;if(!parse_number(parts[1],accepted)||accepted>1||!parse_number(parts[2],projection)||!interop_session.consent(accepted!=0,projection)){error("permission","session consent refused");continue;}ok("state=consented physicalOutputsArmed=0");
            continue;
        }
        if (command == "SESSION_ACTIVATE" && parts.size() == 5) {
            std::uint64_t now=0,epoch=0,profile_revision=0,registry_revision=0;
            if(!parse_number(parts[1],now)||!parse_number(parts[2],epoch)||!parse_number(parts[3],profile_revision)||!parse_number(parts[4],registry_revision)||!interop_session.activate(now,epoch,profile_revision,registry_revision)){error("conflict","session activation refused");continue;}ok("state=active physicalOutputsArmed=0");
            continue;
        }
        if (command == "SESSION_INVALIDATE" && parts.size() == 4) {
            std::uint64_t epoch=0,profile_revision=0,registry_revision=0;if(!parse_number(parts[1],epoch)||!parse_number(parts[2],profile_revision)||!parse_number(parts[3],registry_revision)){error("argument","invalid session state identity");continue;}interop_session.invalidate_if_changed(epoch,profile_revision,registry_revision);ok("checked=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "SESSION_STATUS" && parts.size() == 1) {
            const auto status=interop_session.status();std::cout<<"OK sessionId="<<status.session_id<<" state="<<static_cast<unsigned int>(status.state)<<" authenticated="<<(status.authenticated?1:0)<<" compatible="<<(status.compatible?1:0)
                     <<" transcriptHash="<<status.transcript_hash<<" nonce="<<status.nonce<<" authorityEpoch="<<status.authority_epoch<<" sequence="<<status.sequence<<" expiresUnixMs="<<status.expires_unix_ms
                     <<" protocolVersion="<<status.protocol_version<<" profileSchemaVersion="<<status.profile_schema_version<<" profileRevision="<<status.profile_revision<<" registryRevision="<<status.registry_revision
                     <<" consentDigest="<<status.consent_digest<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "CHANNEL_BEGIN" && parts.size() == 4) {
            if(!parse_number(parts[1],staged_channel_high)||!parse_number(parts[2],staged_channel_low)||!parse_number(parts[3],staged_channel_epoch)||
               (staged_channel_high==0&&staged_channel_low==0)||staged_channel_epoch==0){error("argument","invalid session channel identity");continue;}
            staged_channel_capability_count=0;ok("staged=channel physicalOutputsArmed=0");
            continue;
        }
        if (command == "CHANNEL_CAP" && parts.size() == 2) {
            std::uint64_t capability=0;if(!parse_number(parts[1],capability)||capability==0||staged_channel_capability_count>=staged_channel_capabilities.size()){error("argument","invalid session channel capability");continue;}
            staged_channel_capabilities[staged_channel_capability_count++]=capability;ok(std::string("capabilities=")+std::to_string(staged_channel_capability_count));
            continue;
        }
        if (command == "CHANNEL_COMMIT" && parts.size() == 1) {
            if(!session_channel.configure(staged_channel_high,staged_channel_low,staged_channel_epoch,staged_channel_capabilities.data(),staged_channel_capability_count)){error("conflict","session channel configuration refused");continue;}ok("channelConfigured=1 authenticated=1 confidential=0 physicalOutputsArmed=0");
            continue;
        }
        if (command == "CHANNEL_OUT" && parts.size() == 3) {
            std::uint64_t capability=0;std::uint32_t size=0;stageforge::SessionFrameHeader frame{};
            if(!parse_number(parts[1],capability)||!parse_number(parts[2],size)||!session_channel.next_outbound(capability,size,frame)){error("permission","outbound session frame refused");continue;}
            std::cout<<"OK keyEpoch="<<frame.key_epoch<<" sequence="<<frame.sequence<<" capabilityId="<<frame.capability_id<<" payloadSize="<<frame.payload_size<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "CHANNEL_IN" && parts.size() == 8) {
            stageforge::SessionFrameHeader frame{};unsigned int verified=0;
            if(!parse_number(parts[1],frame.session_id_high)||!parse_number(parts[2],frame.session_id_low)||!parse_number(parts[3],frame.key_epoch)||!parse_number(parts[4],frame.sequence)||!parse_number(parts[5],frame.capability_id)||!parse_number(parts[6],frame.payload_size)||!parse_number(parts[7],verified)||verified>1||!session_channel.authorize_inbound(frame,verified!=0)){error("permission","inbound session frame refused");continue;}ok("accepted=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "CHANNEL_ROTATE" && parts.size() == 3) {
            std::uint64_t epoch=0;std::uint32_t grace=0;if(!parse_number(parts[1],epoch)||!parse_number(parts[2],grace)||!session_channel.rotate(epoch,grace)){error("conflict","session channel rotation refused");continue;}ok(std::string("keyEpoch=")+std::to_string(epoch)+" physicalOutputsArmed=0");
            continue;
        }
        if (command == "CHANNEL_RESTORE" && parts.size() == 5) {
            std::uint64_t epoch=0,outbound=0,inbound=0;unsigned int verified=0;if(!parse_number(parts[1],epoch)||!parse_number(parts[2],outbound)||!parse_number(parts[3],inbound)||!parse_number(parts[4],verified)||verified>1||!session_channel.restore_sequences(epoch,outbound,inbound,verified!=0)){error("permission","session channel checkpoint refused");continue;}ok("restored=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "CHANNEL_STATUS" && parts.size() == 1) {
            const auto status=session_channel.status();std::cout<<"OK sessionHigh="<<status.session_id_high<<" sessionLow="<<status.session_id_low<<" keyEpoch="<<status.key_epoch<<" previousKeyEpoch="<<status.previous_key_epoch
                     <<" outboundSequence="<<status.outbound_sequence<<" inboundSequence="<<status.inbound_sequence<<" accepted="<<status.accepted<<" rejected="<<status.rejected<<" capabilities="<<status.capability_count
                     <<" authenticated="<<(status.authenticated?1:0)<<" confidential=0 physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "CORE_STATUS") {
            const auto metrics = core.metrics();
            std::cout << "OK revision=" << metrics.revision
                      << " externalRevision=" << metrics.external_revision
                      << " transportRevision=" << metrics.transport_revision
                      << " appliedCommands=" << metrics.applied_commands
                      << " duplicateCommands=" << metrics.duplicate_commands
                      << " conflicts=" << metrics.conflicts
                      << " snapshotCommits=" << metrics.snapshot_commits
                      << " staleSnapshots=" << metrics.stale_snapshots
                      << " invalidCommands=" << metrics.invalid_commands
                      << '\n' << std::flush;
            continue;
        }
        if (command == "CORE_SYNC_BEGIN" && parts.size() == 2) {
            std::uint64_t revision = 0;
            if (!parse_number(parts[1], revision)) { error("argument", "invalid snapshot revision"); continue; }
            staged_monitor_players.clear();
            if (!core.begin_snapshot(revision)) { error("conflict", "snapshot begin refused"); continue; }
            ok(std::string("externalRevision=") + std::to_string(revision));
            continue;
        }
        if (command == "CORE_SYNC_TRANSPORT" && parts.size() == 4) {
            double bpm = 0.0, seconds = 0.0; int running = 0;
            if (!parse_number(parts[1], bpm) || !parse_number(parts[2], seconds) || !parse_number(parts[3], running) ||
                !core.stage_transport(bpm, seconds, running != 0)) {
                error("argument", "invalid staged transport"); continue;
            }
            ok("staged=transport");
            continue;
        }
        if (command == "CORE_SYNC_MONITOR" && parts.size() == 10) {
            stageforge::MonitorBusSnapshot snapshot{};
            int muted = 0;
            if (!parse_number(parts[2], snapshot.master) ||
                !parse_number(parts[3], snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::self)]) ||
                !parse_number(parts[4], snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::vocals)]) ||
                !parse_number(parts[5], snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::band)]) ||
                !parse_number(parts[6], snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::click)]) ||
                !parse_number(parts[7], snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::talkback)]) ||
                !parse_number(parts[8], snapshot.levels[static_cast<std::size_t>(stageforge::MonitorChannel::ambient)]) ||
                !parse_number(parts[9], muted)) {
                error("argument", "invalid staged monitor"); continue;
            }
            snapshot.muted = muted != 0;
            if (!core.stage_monitor(parts[1], snapshot)) { error("busy", "monitor snapshot stage refused"); continue; }
            if (std::find(staged_monitor_players.begin(), staged_monitor_players.end(), parts[1]) == staged_monitor_players.end())
                staged_monitor_players.push_back(parts[1]);
            ok(std::string("staged=monitor player=") + parts[1]);
            continue;
        }
        if (command == "CORE_SYNC_COMMIT") {
            const auto result = core.commit_snapshot();
            if (result.status == stageforge::CoreMutationStatus::applied || result.status == stageforge::CoreMutationStatus::duplicate) {
                for (const auto& player_id : staged_monitor_players) {
                    if (auto* bus = monitors.find(player_id)) monitor_router.sync(player_id, *bus, audio_graph);
                }
                staged_monitor_players.clear();
                show_loop.wake();
                std::cout << "OK state=" << stageforge::core_mutation_status_name(result.status)
                          << " revision=" << result.revision
                          << " externalRevision=" << result.external_revision
                          << " transportRevision=" << result.resource_revision << '\n' << std::flush;
            } else {
                staged_monitor_players.clear();
                error("conflict", stageforge::core_mutation_status_name(result.status));
            }
            continue;
        }
        if (command == "CORE_SYNC_ABORT") {
            core.abort_snapshot();
            staged_monitor_players.clear();
            ok("aborted=1");
            continue;
        }
        if (command == "TIME") {
            write_time(clock);
            continue;
        }
        if (command == "CLOCK_SOURCE" && parts.size() == 2) {
            if (parts[1].empty() || parts[1].size() > 63) { error("argument", "invalid clock source"); continue; }
            clock_source = parts[1];
            clock_discipline.reset();
            clock.set_clock_rate(1.0);
            show_loop.wake();
            ok(std::string("source=") + clock_source);
            continue;
        }
        if (command == "CLOCK_OBSERVE" && parts.size() == 3) {
            std::uint64_t local_ns = 0, source_ns = 0;
            if (!parse_number(parts[1], local_ns) || !parse_number(parts[2], source_ns)) {
                error("argument", "invalid clock observation"); continue;
            }
            if (clock_source == "local") { clock_source = "external"; }
            clock_discipline.observe(local_ns, source_ns);
            const auto status = clock_discipline.snapshot(local_ns);
            clock.set_clock_rate(1.0 + status.drift_ppm / 1'000'000.0);
            show_loop.wake();
            std::cout << "OK source=" << token_safe(clock_source)
                      << " state=" << clock_state_name(status.state)
                      << " offsetNs=" << status.offset_ns
                      << " driftPpm=" << std::fixed << std::setprecision(6) << status.drift_ppm
                      << " ageNs=" << status.source_age_ns
                      << " projectedNs=" << status.projected_time_ns
                      << " observations=" << status.observations << '\n' << std::flush;
            continue;
        }
        if (command == "CLOCK_STATUS") {
            std::uint64_t local_ns = clock.snapshot().monotonic_ns;
            if (parts.size() == 2 && !parse_number(parts[1], local_ns)) { error("argument", "invalid local clock time"); continue; }
            if (parts.size() > 2) { error("argument", "clock status takes zero or one timestamp"); continue; }
            const auto status = clock_discipline.snapshot(local_ns);
            std::cout << "OK source=" << token_safe(clock_source)
                      << " state=" << clock_state_name(status.state)
                      << " offsetNs=" << status.offset_ns
                      << " driftPpm=" << std::fixed << std::setprecision(6) << status.drift_ppm
                      << " ageNs=" << status.source_age_ns
                      << " projectedNs=" << status.projected_time_ns
                      << " observations=" << status.observations << '\n' << std::flush;
            continue;
        }
        if(command=="TRANSPORT_DISCIPLINE_CONFIG"&&parts.size()==6){
            std::uint64_t source=0,epoch=0,holdover=0,recovery=0;double slew=0;
            if(!parse_number(parts[1],source)||!parse_number(parts[2],epoch)||!parse_number(parts[3],holdover)||!parse_number(parts[4],slew)||!parse_number(parts[5],recovery)||!transport_discipline.configure(source,epoch,holdover,slew,recovery)){error("argument","invalid transport discipline policy");continue;}
            clock.set_clock_rate(1);show_loop.wake();ok("configured=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="TRANSPORT_DISCIPLINE_OBSERVE"&&parts.size()==7){
            std::uint64_t sequence=0,epoch=0,local=0,source=0,local_show=0,source_show=0;
            if(!parse_number(parts[1],sequence)||!parse_number(parts[2],epoch)||!parse_number(parts[3],local)||!parse_number(parts[4],source)||!parse_number(parts[5],local_show)||!parse_number(parts[6],source_show)||!transport_discipline.observe(sequence,epoch,local,source,local_show,source_show)){error("conflict","transport discipline observation refused");continue;}
            clock.set_clock_rate(transport_discipline.update(local));show_loop.wake();const auto s=transport_discipline.status(local);std::cout<<"OK state="<<clock_state_name(s.state)<<" phaseErrorNs="<<s.phase_error_ns<<" driftPpm="<<s.drift_ppm<<" correctionPpm="<<s.correction_ppm<<" appliedRate="<<s.applied_rate<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="TRANSPORT_DISCIPLINE_STATUS"&&(parts.size()==1||parts.size()==2)){
            std::uint64_t local=clock.snapshot().monotonic_ns;if(parts.size()==2&&!parse_number(parts[1],local)){error("argument","invalid discipline status time");continue;}clock.set_clock_rate(transport_discipline.update(local));const auto s=transport_discipline.status(local);
            std::cout<<"OK configured="<<(s.configured?1:0)<<" state="<<clock_state_name(s.state)<<" sourceId="<<s.source_id<<" authorityEpoch="<<s.authority_epoch<<" lastSequence="<<s.last_sequence<<" phaseErrorNs="<<s.phase_error_ns<<" driftPpm="<<s.drift_ppm<<" correctionPpm="<<s.correction_ppm<<" appliedRate="<<s.applied_rate<<" sourceAgeNs="<<s.source_age_ns<<" observations="<<s.observations<<" rejected="<<s.rejected<<" holdoverEntries="<<s.holdover_entries<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="MIDI_CLOCK_CONFIG"&&parts.size()==4){std::uint64_t epoch=0,boundary=0;double bpm=0;if(!parse_number(parts[1],epoch)||!parse_number(parts[2],bpm)||!parse_number(parts[3],boundary)||!midi_clock.configure(epoch,bpm,boundary)){error("argument","invalid MIDI Clock configuration");continue;}ok("configured=1 ppqn=24 physicalOutputsArmed=0");
            continue;
        }
        if(command=="MIDI_CLOCK_START"&&parts.size()==3){std::uint64_t epoch=0,boundary=0;if(!parse_number(parts[1],epoch)||!parse_number(parts[2],boundary)||!midi_clock.start(epoch,boundary)||!midi.schedule({0xC000000000000000ULL|epoch,boundary,0xFA,0,0})){error("conflict","MIDI Clock start refused");continue;}ok("running=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="MIDI_CLOCK_STOP"&&parts.size()==3){std::uint64_t epoch=0,show=0;if(!parse_number(parts[1],epoch)||!parse_number(parts[2],show)||!midi_clock.stop(epoch)||!midi.schedule({0xC100000000000000ULL|epoch,show,0xFC,0,0})){error("conflict","MIDI Clock stop refused");continue;}ok("running=0 physicalOutputsArmed=0");
            continue;
        }
        if(command=="MIDI_CLOCK_TEMPO"&&parts.size()==4){std::uint64_t epoch=0,boundary=0;double bpm=0;if(!parse_number(parts[1],epoch)||!parse_number(parts[2],bpm)||!parse_number(parts[3],boundary)||!midi_clock.set_tempo(epoch,bpm,boundary)){error("conflict","MIDI Clock tempo boundary refused");continue;}ok("tempo=updated physicalOutputsArmed=0");
            continue;
        }
        if(command=="MIDI_CLOCK_OBSERVE"&&parts.size()==4){std::uint64_t epoch=0,sequence=0,show=0;if(!parse_number(parts[1],epoch)||!parse_number(parts[2],sequence)||!parse_number(parts[3],show)||!midi_clock.observe(epoch,sequence,show)){error("conflict","MIDI Clock pulse refused");continue;}ok("observed=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="MIDI_CLOCK_EMIT"&&(parts.size()==2||parts.size()==3)){std::uint64_t until=0;unsigned int maximum=4096;if(!parse_number(parts[1],until)||(parts.size()==3&&!parse_number(parts[2],maximum))||maximum==0||maximum>4096){error("argument","invalid MIDI Clock emit range");continue;}const auto emitted=midi_clock.emit_until(until,&schedule_midi_clock_pulse,&midi_clock_sink,maximum);std::cout<<"OK emitted="<<emitted<<" queued="<<midi.size()<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="MIDI_CLOCK_STATUS"&&parts.size()==1){const auto s=midi_clock.status();std::cout<<"OK configured="<<(s.configured?1:0)<<" running="<<(s.running?1:0)<<" ppqn=24 authorityEpoch="<<s.authority_epoch<<" bpm="<<s.bpm<<" emitted="<<s.emitted<<" received="<<s.received<<" rejected="<<s.rejected<<" lastSequence="<<s.last_sequence<<" lastPulseShowNs="<<s.last_pulse_show_ns<<" maximumJitterNs="<<s.maximum_jitter_ns<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "TRANSPORT" && parts.size() == 2) {
            stageforge::CoreTransportAction action{};
            if (parts[1] == "play") action = stageforge::CoreTransportAction::play;
            else if (parts[1] == "pause") action = stageforge::CoreTransportAction::pause;
            else if (parts[1] == "stop") action = stageforge::CoreTransportAction::stop;
            else if (parts[1] == "rewind") action = stageforge::CoreTransportAction::rewind;
            else { error("argument", "unknown transport action"); continue; }
            const auto result = core.mutate_transport(next_core_command_id++, stageforge::core_any_revision, action);
            if (!result.applied()) { error("core", stageforge::core_mutation_status_name(result.status)); continue; }
            show_loop.wake();
            write_time(clock);
            continue;
        }
        if (command == "SET_BPM" && parts.size() == 2) {
            double bpm = 0.0;
            if (!parse_number(parts[1], bpm)) { error("argument", "invalid bpm"); continue; }
            const auto result = core.mutate_transport(next_core_command_id++, stageforge::core_any_revision, stageforge::CoreTransportAction::set_bpm, bpm);
            if (!result.applied()) { error("core", stageforge::core_mutation_status_name(result.status)); continue; }
            show_loop.wake();
            write_time(clock);
            continue;
        }
        if (command == "SEEK" && parts.size() == 2) {
            double seconds = 0.0;
            if (!parse_number(parts[1], seconds)) { error("argument", "invalid seconds"); continue; }
            const auto result = core.mutate_transport(next_core_command_id++, stageforge::core_any_revision, stageforge::CoreTransportAction::seek_seconds, seconds);
            if (!result.applied()) { error("core", stageforge::core_mutation_status_name(result.status)); continue; }
            show_loop.wake();
            write_time(clock);
            continue;
        }
        if (command == "AUDIO_SCAN") {
            const auto count = audio_devices.scan();
            ok(std::string("count=") + std::to_string(count) + " selected=" + selected_audio_outputs[0]);
            continue;
        }
        if (command == "AUDIO_DEVICE" && parts.size() == 2) {
            std::size_t index = 0;
            if (!parse_number(parts[1], index)) { error("argument", "invalid audio device index"); continue; }
            const auto* device = audio_devices.device(index);
            if (!device) { error("not_found", "unknown audio device index"); continue; }
            std::cout << "OK index=" << index
                      << " id=" << token_safe(device->id.data())
                      << " name=" << token_safe(device->name.data())
                      << " backend=" << token_safe(device->backend.data())
                      << " address=" << token_safe(device->backend_address.data())
                      << " input=" << (device->input ? 1 : 0)
                      << " output=" << (device->output ? 1 : 0)
                      << " connected=" << (device->connected ? 1 : 0)
                      << " selected=" << (std::any_of(selected_audio_outputs.begin(), selected_audio_outputs.end(), [&](const std::string& value){ return value == device->id.data(); }) ? 1 : 0)
                      << " inputSelected=" << (std::any_of(selected_audio_inputs.begin(), selected_audio_inputs.end(), [&](const std::string& value){ return value == device->id.data(); }) ? 1 : 0)
                      << '\n' << std::flush;
            continue;
        }
        if (command == "AUDIO_SELECT" && (parts.size() == 2 || parts.size() == 3)) {
            std::size_t slot = 0;
            const std::string* device_id = nullptr;
            if (parts.size() == 2) device_id = &parts[1];
            else {
                if (!parse_number(parts[1], slot) || slot >= kAudioOutputSlots) { error("argument", "invalid audio output slot"); continue; }
                device_id = &parts[2];
            }
            const auto* device = audio_devices.find(*device_id);
            if (!device || !device->connected || !device->output) { error("not_found", "audio output unavailable"); continue; }
            selected_audio_outputs[slot] = device->id.data();
            ok(std::string("slot=") + std::to_string(slot) + " selected=" + selected_audio_outputs[slot] + " execution=" + execution_audio_backends[slot]);
            continue;
        }
        if (command == "AUDIO_INPUT_SELECT" && (parts.size() == 2 || parts.size() == 3)) {
            std::size_t slot = 0;
            const std::string* device_id = nullptr;
            if (parts.size() == 2) {
                device_id = &parts[1];
            } else {
                if (!parse_number(parts[1], slot) || slot >= kAudioInputSlots) { error("argument", "invalid audio input slot"); continue; }
                device_id = &parts[2];
            }
            const auto* device = audio_devices.find(*device_id);
            if (!device || !device->connected || !device->input) { error("not_found", "audio input unavailable"); continue; }
            selected_audio_inputs[slot] = device->id.data();
            ok(std::string("slot=") + std::to_string(slot) + " selected=" + selected_audio_inputs[slot] + " execution=" + execution_audio_input_backends[slot]);
            continue;
        }
        if (command == "AUDIO_INPUT_BIND_PLAYER" && (parts.size() == 2 || parts.size() == 3)) {
            std::size_t slot = 0;
            const std::string* player = nullptr;
            if (parts.size() == 2) player = &parts[1];
            else {
                if (!parse_number(parts[1], slot) || slot >= kAudioInputSlots) { error("argument", "invalid audio input slot"); continue; }
                player = &parts[2];
            }
            const int output = monitor_router.ensure_player(*player);
            const int source = monitor_router.self_source_for(*player);
            if (output < 0 || source < 0) { error("capacity", "unable to allocate player audio source"); continue; }
            audio_inputs[slot].source.store(static_cast<std::uint8_t>(source), std::memory_order_release);
            std::cout << "OK slot=" << slot << " player=" << token_safe(*player) << " source=" << source << " monitorOutput=" << output << '\n' << std::flush;
            continue;
        }
        if (command == "AUDIO_INPUT_ACTIVATE" && (parts.size() == 5 || parts.size() == 6 || parts.size() == 7 || parts.size() == 8)) {
            std::size_t slot = 0;
            std::size_t base = 1;
            if (parts.size() >= 6) {
                if (!parse_number(parts[1], slot) || slot >= kAudioInputSlots) { error("argument", "invalid audio input slot"); continue; }
                base = 2;
            }
            double sample_rate = 0.0;
            unsigned int buffer_frames = 0, channels = 0, source_index = 0, conversion_flags = 0;
            std::string sample_format{"FLOAT_LE"};
            if (!parse_number(parts[base], sample_rate) || !parse_number(parts[base + 1], buffer_frames) || !parse_number(parts[base + 2], channels) || !parse_number(parts[base + 3], source_index) ||
                sample_rate < 8000.0 || sample_rate > 384000.0 || buffer_frames < 16 || buffer_frames > 8192 ||
                channels < 1 || channels > 32 || source_index >= stageforge::audio_graph_max_sources) {
                error("argument", "invalid audio input activation configuration"); continue;
            }
            if(parts.size()>=7&&(!parse_number(parts[6],conversion_flags)||conversion_flags>7)){error("argument","invalid audio conversion flags");continue;}
            if(parts.size()==8) sample_format=parts[7];
            stageforge::CanonicalAudioSampleFormat requested_input_format{};
            if(!stageforge::canonical_audio_sample_format_from_name(sample_format,requested_input_format)){error("argument","invalid audio input sample format");continue;}
            if(sample_format!="FLOAT_LE"&&(conversion_flags&4U)==0){error("argument","integer audio input requires sample-format conversion permission");continue;}
            if(channels!=2&&(conversion_flags&2U)==0){error("argument","audio input channel conversion permission is required");continue;}
#if defined(_WIN32) || defined(__APPLE__)
            native_inputs[slot].reset();
#endif
            alsa_inputs[slot].close();
            audio_inputs[slot].enabled.store(false, std::memory_order_release);
            audio_inputs[slot].ring.reset();
            execution_audio_input_backends[slot] = "none";
            const auto* device = audio_devices.find(selected_audio_inputs[slot]);
#if defined(_WIN32) || defined(__APPLE__)
            if (device && device->input && device->connected &&
                (std::string_view(device->backend.data()) == "wasapi" || std::string_view(device->backend.data()) == "coreaudio")) {
                if (sample_rate != static_cast<unsigned>(sample_rate) || sample_format != "FLOAT_LE") {
                    error("unsupported", "native capture requires integral rate and float32 client format"); continue;
                }
                stageforge::AudioRequest request;
                request.direction = stageforge::AudioDirection::Capture;
                request.sample_rate_hz = static_cast<unsigned>(sample_rate);
                request.period_frames = buffer_frames; request.channels = channels;
                request.allow_rate_conversion = (conversion_flags & 1U) != 0;
                request.allow_channel_conversion = (conversion_flags & 2U) != 0;
                request.allow_format_conversion = (conversion_flags & 4U) != 0;
                audio_inputs[slot].source.store(static_cast<std::uint8_t>(source_index), std::memory_order_release);
                try {
                    auto owner = std::make_unique<NativeInputOwner>([&audio_inputs, slot] {
                        return std::make_unique<stageforge::NativeCaptureService>(capture_native_audio, &audio_inputs[slot]);
                    });
                    const std::string token = device->backend_address.data();
                    if (!owner->execute([request, token](auto& service) { return service.activate_endpoint(request, token); })) {
                        error("audio", "selected native input could not be armed"); continue;
                    }
                    const auto verified = owner->execute([](auto& service) { return service.stats(); }).last_verified_configuration;
                    audio_inputs[slot].sample_rate.store(verified.configured_sample_rate_hz, std::memory_order_release);
                    audio_inputs[slot].enabled.store(true, std::memory_order_release);
                    native_inputs[slot] = std::move(owner);
                    execution_audio_input_backends[slot] = device->backend.data();
                    ok("slot=" + std::to_string(slot) + " execution=" + execution_audio_input_backends[slot] +
                       " running=1 device=" + selected_audio_inputs[slot] + " source=" + std::to_string(source_index) +
                       " actualRate=" + std::to_string(verified.configured_sample_rate_hz) +
                       " actualPeriodFrames=" + std::to_string(verified.configured_period_frames) +
                       " actualChannels=" + std::to_string(verified.configured_channels) + " actualFormat=FLOAT_LE");
                } catch (const std::exception&) { error("audio", "native capture owner activation failed"); }
                continue;
            }
#endif
            if (!device || std::string_view(device->backend.data()) != "alsa" || !device->input || !device->connected) {
                error("unsupported", "selected input has no installed capture adapter"); continue;
            }
            stageforge::AudioDeviceConfig config{sample_rate, channels, 0, buffer_frames};
            if (!alsa_inputs[slot].open(device->backend_address.data(), config, capture_audio, &audio_inputs[slot], sample_format)) {
                const std::string message = alsa_inputs[slot].last_error().empty() ? "unable to start ALSA input" : std::string(alsa_inputs[slot].last_error());
                alsa_inputs[slot].close(); error("audio", message); continue;
            }
            const auto actual_input=alsa_inputs[slot].status().config;
            const bool rate_conversion=actual_input.sample_rate!=stageforge::canonical_audio_sample_rate;
            const bool channel_conversion=actual_input.input_channels!=2;
            const bool format_conversion=alsa_inputs[slot].sample_format()!="FLOAT_LE";
            if((rate_conversion&&(conversion_flags&1U)==0)||(channel_conversion&&(conversion_flags&2U)==0)||(format_conversion&&(conversion_flags&4U)==0)||!alsa_inputs[slot].start()){
                alsa_inputs[slot].close();error("audio","configured ALSA input parameters exceed engine bounds");continue;
            }
            audio_inputs[slot].source.store(static_cast<std::uint8_t>(source_index), std::memory_order_release);
            audio_inputs[slot].sample_rate.store(actual_input.sample_rate, std::memory_order_release);
            audio_inputs[slot].enabled.store(true, std::memory_order_release);
            execution_audio_input_backends[slot] = "alsa";
            ok(std::string("slot=") + std::to_string(slot) + " execution=alsa running=1 device=" + selected_audio_inputs[slot] + " source=" + std::to_string(source_index) + " actualRate=" + std::to_string(actual_input.sample_rate) + " actualPeriodFrames=" + std::to_string(actual_input.frames_per_buffer) + " actualChannels=" + std::to_string(actual_input.input_channels) + " actualFormat=" + std::string(alsa_inputs[slot].sample_format()));
            continue;
        }
        if (command == "AUDIO_INPUT_DEACTIVATE" && (parts.size() == 1 || parts.size() == 2)) {
            std::size_t slot = 0;
            if (parts.size() == 2 && (!parse_number(parts[1], slot) || slot >= kAudioInputSlots)) { error("argument", "invalid audio input slot"); continue; }
            audio_inputs[slot].enabled.store(false, std::memory_order_release);
#if defined(_WIN32) || defined(__APPLE__)
            native_inputs[slot].reset();
#endif
            alsa_inputs[slot].close();
            audio_inputs[slot].ring.reset();
            execution_audio_input_backends[slot] = "none";
            ok(std::string("slot=") + std::to_string(slot) + " execution=none running=0");
            continue;
        }
        if (command == "AUDIO_INPUT_STATUS" && (parts.size() == 1 || parts.size() == 2)) {
            std::size_t slot = 0;
            if (parts.size() == 2 && (!parse_number(parts[1], slot) || slot >= kAudioInputSlots)) { error("argument", "invalid audio input slot"); continue; }
#if defined(_WIN32) || defined(__APPLE__)
            if (native_inputs[slot]) {
                const auto stats = native_inputs[slot]->execute([](auto& service) { return service.stats(); });
                std::cout << "OK slot=" << slot << " execution=" << execution_audio_input_backends[slot]
                          << " selected=" << selected_audio_inputs[slot] << " running=" << stats.native_running
                          << " state=" << static_cast<int>(stats.lifecycle.state) << " callbacks=" << stats.callbacks
                          << " discontinuities=" << stats.discontinuities
                          << " sampleRate=" << audio_inputs[slot].sample_rate.load(std::memory_order_acquire)
                          << " configuredRate=" << stats.last_verified_configuration.configured_sample_rate_hz
                          << " periodFrames=" << stats.last_verified_configuration.configured_period_frames
                          << " channels=" << stats.last_verified_configuration.configured_channels
                          << " explicitRearmRequired=" << stats.lifecycle.explicit_rearm_required
                          << " source=" << static_cast<unsigned>(audio_inputs[slot].source.load(std::memory_order_acquire))
                          << '\n' << std::flush;
                continue;
            }
#endif
            const auto stream = alsa_inputs[slot].status();
            const auto requested = alsa_inputs[slot].requested_config();
            std::cout << "OK slot=" << slot
                      << " execution=" << execution_audio_input_backends[slot]
                      << " selected=" << (selected_audio_inputs[slot].empty() ? "none" : selected_audio_inputs[slot])
                      << " state=" << static_cast<int>(stream.state)
                      << " callbacks=" << stream.callback_count
                      << " xruns=" << stream.xruns
                      << " sampleRate=" << audio_inputs[slot].sample_rate.load(std::memory_order_acquire)
                      << " requestedRate=" << requested.sample_rate
                      << " configuredRate=" << stream.config.sample_rate
                      << " periodFrames=" << stream.config.frames_per_buffer
                      << " channels=" << stream.config.input_channels
                      << " requestedPeriodFrames=" << requested.frames_per_buffer
                      << " requestedChannels=" << requested.input_channels
                      << " sampleFormat=" << token_safe(alsa_inputs[slot].sample_format())
                      << " source=" << static_cast<unsigned int>(audio_inputs[slot].source.load(std::memory_order_acquire))
                      << " queued=" << ([&](){ std::uint64_t total=0; for(std::size_t reader=0; reader<kAudioOutputSlots; ++reader) total += audio_inputs[slot].ring.queued(reader); return total; })()
                      << " dropped=" << ([&](){ std::uint64_t total=0; for(std::size_t reader=0; reader<kAudioOutputSlots; ++reader) total += audio_inputs[slot].ring.dropped(reader); return total; })()
                      << " underruns=" << ([&](){ std::uint64_t total=0; for(std::size_t reader=0; reader<kAudioOutputSlots; ++reader) total += audio_inputs[slot].ring.underruns(reader); return total; })()
                      << " error=" << token_safe(alsa_inputs[slot].last_error().empty() ? "none" : alsa_inputs[slot].last_error())
                      << '\n' << std::flush;
            continue;
        }
        if (command == "AUDIO_INPUT_ROUTE" && (parts.size() == 3 || parts.size() == 4)) {
            std::size_t slot = 0;
            std::size_t base = 1;
            if (parts.size() == 4) {
                if (!parse_number(parts[1], slot) || slot >= kAudioInputSlots) { error("argument", "invalid audio input slot"); continue; }
                base = 2;
            }
            unsigned int output = 0; float gain = 0.0F;
            if (!parse_number(parts[base], output) || !parse_number(parts[base + 1], gain) || output >= stageforge::audio_graph_max_outputs) {
                error("argument", "invalid audio input route"); continue;
            }
            const auto source = audio_inputs[slot].source.load(std::memory_order_acquire);
            audio_graph.set_route_gain(source, static_cast<std::uint8_t>(output), gain);
            std::cout << "OK slot=" << slot << " source=" << static_cast<unsigned int>(source) << " output=" << output
                      << " gain=" << audio_graph.route_gain(source, static_cast<std::uint8_t>(output)) << '\n' << std::flush;
            continue;
        }
        if (command == "AUDIO_OUTPUT_BIND_PLAYER" && parts.size() == 3) {
            std::size_t slot = 0;
            if (!parse_number(parts[1], slot) || slot >= kAudioOutputSlots) { error("argument", "invalid audio output slot"); continue; }
            const int graph_output = monitor_router.ensure_player(parts[2]);
            auto* bus = monitors.find(parts[2]);
            if (!bus) bus = &monitors.get_or_create(parts[2]);
            if (graph_output < 0 || !monitor_router.sync(parts[2], *bus, audio_graph)) { error("capacity", "unable to allocate monitor output"); continue; }
            audio_render_contexts[slot].output.store(static_cast<std::uint8_t>(graph_output), std::memory_order_release);
            std::cout << "OK slot=" << slot << " player=" << token_safe(parts[2]) << " output=" << graph_output << '\n' << std::flush;
            continue;
        }
        if (command == "AUDIO_DRIFT_CONFIG" && parts.size() == 5) {
            std::size_t slot = 0; int enabled = 0; double max_ppm = 0.0, queue_gain_ppm = 0.0;
            if (!parse_number(parts[1], slot) || slot >= kAudioOutputSlots || !parse_number(parts[2], enabled) ||
                !parse_number(parts[3], max_ppm) || !parse_number(parts[4], queue_gain_ppm) ||
                max_ppm < 0.0 || max_ppm > 10000.0 || queue_gain_ppm < 0.0 || queue_gain_ppm > 10000.0) {
                error("argument", "invalid audio drift configuration"); continue;
            }
            if (alsa_outputs[slot].status().state == stageforge::AudioDeviceState::running) {
                error("busy", "audio drift configuration requires stopped output"); continue;
            }
            auto& context = audio_render_contexts[slot];
            context.drift_enabled.store(enabled != 0, std::memory_order_relaxed);
            context.max_correction_ppm.store(max_ppm, std::memory_order_relaxed);
            context.queue_gain_ppm.store(queue_gain_ppm, std::memory_order_relaxed);
            context.drift_controller.configure({max_ppm, queue_gain_ppm, 0.05});
            context.correction_ppm.store(0.0, std::memory_order_relaxed);
            context.compensated_blocks.store(0, std::memory_order_relaxed);
            std::cout << "OK slot=" << slot << " enabled=" << (enabled != 0 ? 1 : 0)
                      << " maxPpm=" << max_ppm << " queueGainPpm=" << queue_gain_ppm << '\n' << std::flush;
            continue;
        }
        if (command == "AUDIO_ACTIVATE" && (parts.size() == 4 || parts.size() == 5 || parts.size() == 6 || parts.size() == 8)) {
            std::size_t slot = 0;
            std::size_t base = 1;
            if (parts.size() >= 5) {
                if (!parse_number(parts[1], slot) || slot >= kAudioOutputSlots) { error("argument", "invalid audio output slot"); continue; }
                base = 2;
            }
            double sample_rate = 0.0;
            unsigned int buffer_frames = 0, output_index = 0, conversion_flags = 0, channels = 2;
            std::string sample_format{"FLOAT_LE"};
            if (!parse_number(parts[base], sample_rate) || !parse_number(parts[base + 1], buffer_frames) || !parse_number(parts[base + 2], output_index) ||
                sample_rate < 8000.0 || sample_rate > 384000.0 || buffer_frames < 16 || buffer_frames > 8192 ||
                output_index >= stageforge::audio_graph_max_outputs ||
                static_cast<double>(buffer_frames)*stageforge::canonical_audio_sample_rate/sample_rate>8192.0) {
                error("argument", "invalid audio activation configuration"); continue;
            }
            if(parts.size()>=6&&(!parse_number(parts[5],conversion_flags)||conversion_flags>7)){error("argument","invalid audio conversion flags");continue;}
            if(parts.size()==8){sample_format=parts[6];if(!parse_number(parts[7],channels)||channels<1||channels>32){error("argument","invalid audio output channel count");continue;}}
            stageforge::CanonicalAudioSampleFormat requested_output_format{};
            if(!stageforge::canonical_audio_sample_format_from_name(sample_format,requested_output_format)){error("argument","invalid audio output sample format");continue;}
            if(sample_format!="FLOAT_LE"&&(conversion_flags&4U)==0){error("argument","integer audio output requires sample-format conversion permission");continue;}
            if(channels!=2&&(conversion_flags&2U)==0){error("argument","audio output channel conversion permission is required");continue;}
#if defined(_WIN32) || defined(__APPLE__)
            native_outputs[slot].reset();
#endif
            alsa_outputs[slot].close();
            execution_audio_backends[slot] = slot == 0 ? "null-audio" : "none";
            audio_render_contexts[slot].output.store(static_cast<std::uint8_t>(output_index), std::memory_order_release);
            audio_render_contexts[slot].drift_start_ns.store(0, std::memory_order_relaxed);
            audio_render_contexts[slot].drift_last_ns.store(0, std::memory_order_relaxed);
            audio_render_contexts[slot].drift_frames.store(0, std::memory_order_relaxed);
            audio_render_contexts[slot].expected_sample_rate.store(sample_rate, std::memory_order_relaxed);
            audio_render_contexts[slot].measured_rate_ppm.store(0.0, std::memory_order_relaxed);
            audio_render_contexts[slot].correction_ppm.store(0.0, std::memory_order_relaxed);
            audio_render_contexts[slot].source_frames_last.store(buffer_frames, std::memory_order_relaxed);
            audio_render_contexts[slot].compensated_blocks.store(0, std::memory_order_relaxed);
            audio_render_contexts[slot].first_render_show_ns.store(0, std::memory_order_relaxed);
            audio_render_contexts[slot].last_render_show_ns.store(0, std::memory_order_relaxed);
            audio_render_contexts[slot].last_block_end_show_ns.store(0, std::memory_order_relaxed);
            audio_render_contexts[slot].drift_controller.reset();
            audio_render_contexts[slot].canonical_frame_fraction = 0.0;
            audio_render_contexts[slot].input_frame_fraction.fill(0.0);
            for (auto& input : audio_inputs) input.ring.set_reader_active(slot, true);
            if (selected_audio_outputs[slot].empty() || selected_audio_outputs[slot] == "null-audio") {
                for (auto& input : audio_inputs) input.ring.set_reader_active(slot, false);
                execution_audio_backends[slot] = slot == 0 ? "null-audio" : "none";
                ok(std::string("slot=") + std::to_string(slot) + " execution=" + execution_audio_backends[slot] + " running=1 output=" + std::to_string(output_index));
                continue;
            }
            const auto* device = audio_devices.find(selected_audio_outputs[slot]);
#if defined(_WIN32) || defined(__APPLE__)
            if (device && device->output && device->connected &&
                (std::string_view(device->backend.data()) == "wasapi" || std::string_view(device->backend.data()) == "coreaudio")) {
                if (sample_rate != static_cast<unsigned>(sample_rate) || sample_format != "FLOAT_LE") {
                    for (auto& input : audio_inputs) input.ring.set_reader_active(slot, false);
                    error("unsupported", "native playback requires integral rate and float32 client format"); continue;
                }
                stageforge::AudioRequest request;
                request.direction = stageforge::AudioDirection::Playback;
                request.sample_rate_hz = static_cast<unsigned>(sample_rate);
                request.period_frames = buffer_frames; request.channels = channels;
                request.allow_rate_conversion = (conversion_flags & 1U) != 0;
                request.allow_period_adaptation = false;
                request.allow_channel_conversion = (conversion_flags & 2U) != 0;
                request.allow_format_conversion = (conversion_flags & 4U) != 0;
                try {
                    auto owner = std::make_unique<NativeOutputOwner>([&audio_render_contexts, slot] {
                        return std::make_unique<stageforge::NativePlaybackService>(render_native_audio, &audio_render_contexts[slot]);
                    });
                    const std::string token = device->backend_address.data();
                    if (!owner->execute([request, token](auto& service) { return service.activate_endpoint(request, token); })) {
                        for (auto& input : audio_inputs) input.ring.set_reader_active(slot, false);
                        error("audio", "selected native output could not be armed"); continue;
                    }
                    const auto verified = owner->execute([](auto& service) { return service.stats(); }).last_verified_configuration;
                    audio_render_contexts[slot].expected_sample_rate.store(verified.configured_sample_rate_hz, std::memory_order_relaxed);
                    native_outputs[slot] = std::move(owner);
                    execution_audio_backends[slot] = device->backend.data();
                    ok("slot=" + std::to_string(slot) + " execution=" + execution_audio_backends[slot] +
                       " running=1 device=" + selected_audio_outputs[slot] + " output=" + std::to_string(output_index) +
                       " actualRate=" + std::to_string(verified.configured_sample_rate_hz) +
                       " actualPeriodFrames=" + std::to_string(verified.configured_period_frames) +
                       " actualChannels=" + std::to_string(verified.configured_channels) + " actualFormat=FLOAT_LE");
                } catch (const std::exception&) {
                    for (auto& input : audio_inputs) input.ring.set_reader_active(slot, false);
                    error("audio", "native playback owner activation failed");
                }
                continue;
            }
#endif
            if (!device || std::string_view(device->backend.data()) != "alsa" || !device->output || !device->connected) {
                for (auto& input : audio_inputs) input.ring.set_reader_active(slot, false);
                error("unsupported", "selected device has no installed playback adapter"); continue;
            }
            stageforge::AudioDeviceConfig config{sample_rate, 0, channels, buffer_frames};
            if (!alsa_outputs[slot].open(device->backend_address.data(), config, render_audio, &audio_render_contexts[slot], sample_format)) {
                const std::string message = alsa_outputs[slot].last_error().empty() ? "unable to start ALSA output" : std::string(alsa_outputs[slot].last_error());
                alsa_outputs[slot].close();
                for (auto& input : audio_inputs) input.ring.set_reader_active(slot, false);
                error("audio", message); continue;
            }
            const auto actual_output=alsa_outputs[slot].status().config;
            const bool rate_conversion=actual_output.sample_rate!=stageforge::canonical_audio_sample_rate;
            const bool channel_conversion=actual_output.output_channels!=2;
            const bool format_conversion=alsa_outputs[slot].sample_format()!="FLOAT_LE";
            if((rate_conversion&&(conversion_flags&1U)==0)||(channel_conversion&&(conversion_flags&2U)==0)||(format_conversion&&(conversion_flags&4U)==0)||static_cast<double>(actual_output.frames_per_buffer)*stageforge::canonical_audio_sample_rate/actual_output.sample_rate>8192.0||!alsa_outputs[slot].start()){
                alsa_outputs[slot].close();for(auto& input:audio_inputs)input.ring.set_reader_active(slot,false);error("audio","configured ALSA output parameters exceed engine bounds");continue;
            }
            audio_render_contexts[slot].expected_sample_rate.store(actual_output.sample_rate,std::memory_order_relaxed);
            execution_audio_backends[slot] = "alsa";
            ok(std::string("slot=") + std::to_string(slot) + " execution=alsa running=1 device=" + selected_audio_outputs[slot] + " output=" + std::to_string(output_index) + " actualRate=" + std::to_string(actual_output.sample_rate) + " actualPeriodFrames=" + std::to_string(actual_output.frames_per_buffer) + " actualChannels=" + std::to_string(actual_output.output_channels) + " actualFormat=" + std::string(alsa_outputs[slot].sample_format()));
            continue;
        }
        if (command == "AUDIO_DEACTIVATE" && (parts.size() == 1 || parts.size() == 2)) {
            std::size_t slot = 0;
            if (parts.size() == 2 && (!parse_number(parts[1], slot) || slot >= kAudioOutputSlots)) { error("argument", "invalid audio output slot"); continue; }
#if defined(_WIN32) || defined(__APPLE__)
            native_outputs[slot].reset();
#endif
            alsa_outputs[slot].close();
            execution_audio_backends[slot] = slot == 0 ? "null-audio" : "none";
            for (auto& input : audio_inputs) input.ring.set_reader_active(slot, false);
            ok(std::string("slot=") + std::to_string(slot) + " execution=" + execution_audio_backends[slot] + " running=0");
            continue;
        }
        if (command == "AUDIO_STREAM_STATUS" && (parts.size() == 1 || parts.size() == 2)) {
            std::size_t slot = 0;
            if (parts.size() == 2 && (!parse_number(parts[1], slot) || slot >= kAudioOutputSlots)) { error("argument", "invalid audio output slot"); continue; }
#if defined(_WIN32) || defined(__APPLE__)
            if (native_outputs[slot]) {
                const auto stats = native_outputs[slot]->execute([](auto& service) { return service.stats(); });
                std::uint64_t fanout_dropped = 0, fanout_underruns = 0, fanout_queued = 0;
                for (const auto& input : audio_inputs) {
                    fanout_dropped += input.ring.dropped(slot);
                    fanout_underruns += input.ring.underruns(slot);
                    fanout_queued += input.ring.queued(slot);
                }
                std::cout << "OK slot=" << slot
                          << " execution=" << execution_audio_backends[slot]
                          << " selected=" << selected_audio_outputs[slot]
                          << " running=" << (stats.native_running ? 1 : 0)
                          << " state=" << static_cast<int>(stats.lifecycle.state)
                          << " callbacks=" << stats.callbacks
                          << " xruns=0"
                          << " requestedRate=" << audio_render_contexts[slot].expected_sample_rate.load(std::memory_order_relaxed)
                          << " configuredRate=" << stats.last_verified_configuration.configured_sample_rate_hz
                          << " periodFrames=" << stats.last_verified_configuration.configured_period_frames
                          << " channels=" << stats.last_verified_configuration.configured_channels
                          << " requestedPeriodFrames=" << stats.last_verified_configuration.configured_period_frames
                          << " requestedChannels=" << stats.last_verified_configuration.configured_channels
                          << " sampleFormat=FLOAT_LE"
                          << " output=" << static_cast<unsigned int>(audio_render_contexts[slot].output.load(std::memory_order_acquire))
                          << " queued=" << fanout_queued
                          << " dropped=" << fanout_dropped
                          << " underruns=" << fanout_underruns
                          << " rateMeasured=0 ratePpm=0.00"
                          << " driftEnabled=" << (audio_render_contexts[slot].drift_enabled.load(std::memory_order_relaxed) ? 1 : 0)
                          << " maxCorrectionPpm=" << audio_render_contexts[slot].max_correction_ppm.load(std::memory_order_relaxed)
                          << " queueGainPpm=" << audio_render_contexts[slot].queue_gain_ppm.load(std::memory_order_relaxed)
                          << " correctionPpm=" << audio_render_contexts[slot].correction_ppm.load(std::memory_order_relaxed)
                          << " sourceFrames=" << audio_render_contexts[slot].source_frames_last.load(std::memory_order_relaxed)
                          << " compensatedBlocks=" << audio_render_contexts[slot].compensated_blocks.load(std::memory_order_relaxed)
                          << " firstWriteNs=0 lastWriteNs=0 maxExcessGapNs=0 framesWritten=" << stats.frames
                          << " firstRenderShowNs=" << audio_render_contexts[slot].first_render_show_ns.load(std::memory_order_relaxed)
                          << " lastRenderShowNs=" << audio_render_contexts[slot].last_render_show_ns.load(std::memory_order_relaxed)
                          << " lastBlockEndShowNs=" << audio_render_contexts[slot].last_block_end_show_ns.load(std::memory_order_relaxed)
                          << " error=none\n" << std::flush;
                continue;
            }
#endif
            const auto stream = alsa_outputs[slot].status();
            const auto requested = alsa_outputs[slot].requested_config();
            const bool alsa = execution_audio_backends[slot] == "alsa";
            std::uint64_t fanout_dropped = 0, fanout_underruns = 0, fanout_queued = 0;
            for (const auto& input : audio_inputs) {
                fanout_dropped += input.ring.dropped(slot);
                fanout_underruns += input.ring.underruns(slot);
                fanout_queued += input.ring.queued(slot);
            }
            const auto start_ns = audio_render_contexts[slot].drift_start_ns.load(std::memory_order_relaxed);
            const auto last_ns = audio_render_contexts[slot].drift_last_ns.load(std::memory_order_relaxed);
            const bool rate_measured = alsa && start_ns > 0 && last_ns > start_ns && (last_ns - start_ns) >= 50'000'000ULL;
            const double rate_ppm = audio_render_contexts[slot].measured_rate_ppm.load(std::memory_order_relaxed);
            const double correction_ppm = audio_render_contexts[slot].correction_ppm.load(std::memory_order_relaxed);
            const auto source_frames_last = audio_render_contexts[slot].source_frames_last.load(std::memory_order_relaxed);
            const auto compensated_blocks = audio_render_contexts[slot].compensated_blocks.load(std::memory_order_relaxed);
            std::cout << "OK slot=" << slot
                      << " execution=" << execution_audio_backends[slot]
                      << " selected=" << (selected_audio_outputs[slot].empty() ? "none" : selected_audio_outputs[slot])
                      << " state=" << static_cast<int>(alsa ? stream.state : (slot == 0 ? audio.status().state : stageforge::AudioDeviceState::closed))
                      << " callbacks=" << (alsa ? stream.callback_count : (slot == 0 ? audio.status().callback_count : 0))
                      << " xruns=" << (alsa ? stream.xruns : 0)
                      << " requestedRate=" << (alsa ? requested.sample_rate : (slot == 0 ? audio.status().config.sample_rate : 0.0))
                      << " configuredRate=" << (alsa ? stream.config.sample_rate : (slot == 0 ? audio.status().config.sample_rate : 0.0))
                      << " periodFrames=" << (alsa ? stream.config.frames_per_buffer : (slot == 0 ? audio.status().config.frames_per_buffer : 0))
                      << " channels=" << (alsa ? stream.config.output_channels : (slot == 0 ? audio.status().config.output_channels : 0))
                      << " requestedPeriodFrames=" << (alsa ? requested.frames_per_buffer : (slot == 0 ? audio.status().config.frames_per_buffer : 0))
                      << " requestedChannels=" << (alsa ? requested.output_channels : (slot == 0 ? audio.status().config.output_channels : 0))
                      << " sampleFormat=" << (alsa ? token_safe(alsa_outputs[slot].sample_format()) : "FLOAT_LE")
                      << " output=" << static_cast<unsigned int>(audio_render_contexts[slot].output.load(std::memory_order_acquire))
                      << " queued=" << fanout_queued
                      << " dropped=" << fanout_dropped
                      << " underruns=" << fanout_underruns
                      << " rateMeasured=" << (rate_measured ? 1 : 0)
                      << " ratePpm=" << std::fixed << std::setprecision(2) << rate_ppm
                      << " driftEnabled=" << (audio_render_contexts[slot].drift_enabled.load(std::memory_order_relaxed) ? 1 : 0)
                      << " maxCorrectionPpm=" << audio_render_contexts[slot].max_correction_ppm.load(std::memory_order_relaxed)
                      << " queueGainPpm=" << audio_render_contexts[slot].queue_gain_ppm.load(std::memory_order_relaxed)
                      << " correctionPpm=" << std::fixed << std::setprecision(2) << correction_ppm
                      << " sourceFrames=" << source_frames_last
                      << " compensatedBlocks=" << compensated_blocks
                      << " firstWriteNs=" << alsa_outputs[slot].first_write_ns()
                      << " lastWriteNs=" << alsa_outputs[slot].last_write_ns()
                      << " maxExcessGapNs=" << alsa_outputs[slot].max_excess_gap_ns()
                      << " framesWritten=" << alsa_outputs[slot].frames_written()
                      << " firstRenderShowNs=" << audio_render_contexts[slot].first_render_show_ns.load(std::memory_order_relaxed)
                      << " lastRenderShowNs=" << audio_render_contexts[slot].last_render_show_ns.load(std::memory_order_relaxed)
                      << " lastBlockEndShowNs=" << audio_render_contexts[slot].last_block_end_show_ns.load(std::memory_order_relaxed)
                      << " error=" << token_safe(alsa_outputs[slot].last_error().empty() ? "none" : alsa_outputs[slot].last_error())
                      << '\n' << std::flush;
            continue;
        }
        if (command == "AUDIO_ROUTE" && parts.size() == 4) {
            unsigned int source = 0, output = 0;
            float gain = 0.0F;
            if (!parse_number(parts[1], source) || !parse_number(parts[2], output) || !parse_number(parts[3], gain) ||
                source >= stageforge::audio_graph_max_sources || output >= stageforge::audio_graph_max_outputs) {
                error("argument", "invalid audio route"); continue;
            }
            audio_graph.set_route_gain(static_cast<std::uint8_t>(source), static_cast<std::uint8_t>(output), gain);
            std::cout << "OK source=" << source << " output=" << output
                      << " gain=" << audio_graph.route_gain(static_cast<std::uint8_t>(source), static_cast<std::uint8_t>(output))
                      << '\n' << std::flush;
            continue;
        }
        if (command == "AUDIO_OUTPUT" && parts.size() == 4) {
            unsigned int output = 0;
            float master = 0.0F, ceiling = 0.0F;
            if (!parse_number(parts[1], output) || !parse_number(parts[2], master) || !parse_number(parts[3], ceiling) ||
                output >= stageforge::audio_graph_max_outputs) {
                error("argument", "invalid audio output"); continue;
            }
Warning: truncated output (original token count: 6047)
Total output lines: 250

            audio_graph.set_output_master(static_cast<std::uint8_t>(output), master);
            audio_graph.set_limiter_ceiling_db(static_cast<std::uint8_t>(output), ceiling);
            std::cout << "OK output=" << output
                      << " master=" << audio_graph.output_master(static_cast<std::uint8_t>(output))
                      << " ceilingDb=" << audio_graph.limiter_ceiling_db(static_cast<std::uint8_t>(output))
                      << '\n' << std::flush;
            continue;
        }
        if (command == "HUB_HW_UWB_OPEN" && parts.size() == 3) {
            unsigned int baud=0;
            if(!parse_number(parts[2],baud)||parts[1].empty()||!le_uwb_hardware.open_uwb(parts[1].c_str(),baud)){
                const auto status=le_uwb_hardware.uwb_status();
                error("hardware",std::string("unable to open UWB bridge errno ")+std::to_string(status.last_errno));continue;
            }
            ok(std::string("uwbOpen=1 baud=")+std::to_string(baud)+" physicalOutputsArmed=0");
            continue;
        }
        if (command == "HUB_HW_UWB_CLOSE" && parts.size() == 1) {
            le_uwb_hardware.close_uwb();ok("uwbOpen=0 physicalOutputsArmed=0");
            continue;
        }
        if (command == "HUB_HW_LE_OPEN" && parts.size() == 5) {
            std::uint64_t node_id=0;unsigned int random_address=0;
            if(!parse_number(parts[1],node_id)||!parse_number(parts[4],random_address)||random_address>1||
               !le_uwb_hardware.connect_le(node_id,parts[2].c_str(),parts[3].c_str(),random_address!=0)){
                error("hardware","unable to open Linux LE ISO socket");continue;
            }
            ok(std::string("nodeId=")+std::to_string(node_id)+" leOpen=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "HUB_HW_LE_CLOSE" && parts.size() == 2) {
            std::uint64_t node_id=0;if(!parse_number(parts[1],node_id)){error("argument","invalid LE node id");continue;}
            le_uwb_hardware.close_le(node_id);ok(std::string("nodeId=")+std::to_string(node_id)+" leOpen=0 physicalOutputsArmed=0");
            continue;
        }
        if (command == "HUB_HW_POLL" && (parts.size() == 1 || parts.size() == 2)) {
            std::size_t budget=64;
            if(parts.size()==2&&(!parse_number(parts[1],budget)||budget==0||budget>1024)){error("argument","invalid hardware poll budget");continue;}
            const auto handled=le_uwb_hardware.poll(budget);const auto status=le_uwb_hardware.status();
            std::cout<<"OK handled="<<handled<<" polls="<<status.polls<<" acceptedUwb="<<status.accepted_uwb_frames
                     <<" rejectedUwb="<<status.rejected_uwb_frames<<" acceptedLe="<<status.accepted_le_frames
                     <<" rejectedLe="<<status.rejected_le_frames<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "HUB_HW_STATUS" && (parts.size() == 1 || parts.size() == 2)) {
            const auto status=le_uwb_hardware.status();const auto uwb=le_uwb_hardware.uwb_status();
            std::cout<<"OK kernelIsoSupported="<<(status.kernel_iso_supported?1:0)<<" uwbOpen="<<(status.uwb_open?1:0)
                     <<" leConfigured="<<status.configured_le_slots<<" leConnected="<<status.connected_le_slots
                     <<" polls="<<status.polls<<" acceptedUwb="<<status.accepted_uwb_frames<<" rejectedUwb="<<status.rejected_uwb_frames
                     <<" acceptedLe="<<status.accepted_le_frames<<" rejectedLe="<<status.rejected_le_frames
                     <<" uwbValidFrames="<<uwb.valid_frames<<" uwbInvalidFrames="<<uwb.invalid_frames
                     <<" uwbResyncBytes="<<uwb.resync_bytes<<" physicalOutputsArmed=0";
            if(parts.size()==2){
                std::uint64_t node_id=0;stageforge::LeIsoHardwareStatus le{};
                if(!parse_number(parts[1],node_id)||!le_uwb_hardware.le_status(node_id,le)){std::cout<<'\n'<<std::flush;continue;}
                std::cout<<" nodeId="<<node_id<<" leOpen="<<(le.open?1:0)<<" leConnecting="<<(le.connecting?1:0)
                         <<" leSocketConnected="<<(le.connected?1:0)<<" leReceivedSdus="<<le.received_sdus
                         <<" leTransmittedSdus="<<le.transmitted_sdus<<" leIoErrors="<<le.io_errors<<" leErrno="<<le.last_errno;
            }
            std::cout<<'\n'<<std::flush;
            continue;
        }
        if (command == "HUB_CONFIG" && parts.size() == 11) {
            std::uint64_t epoch=0,target_lead=0,max_end_to_end=0,fresh=0,holdover=0,max_clock=0,max_jitter=0;
            double max_range=0.0,max_drift=0.0;unsigned int require_auth=0;
            if(!parse_number(parts[1],epoch)||!parse_number(parts[2],target_lead)||!parse_number(parts[3],max_end_to_end)||
               !parse_number(parts[4],fresh)||!parse_number(parts[5],holdover)||!parse_number(parts[6],max_clock)||
               !parse_number(parts[7],max_jitter)||!parse_number(parts[8],max_range)||!parse_number(parts[9],max_drift)||
               !parse_number(parts[10],require_auth)||require_auth>1){error("argument","invalid LE-UWB hub policy");continue;}
            stageforge::LeUwbHubPolicy policy{};policy.target_presentation_lead_ns=target_lead;policy.max_end_to_end_ns=max_end_to_end;
            policy.fresh_observation_ns=fresh;policy.holdover_ns=holdover;policy.max_clock_uncertainty_ns=max_clock;
            policy.max_jitter_ns=max_jitter;policy.max_range_uncertainty_mm=max_range;policy.max_drift_ppm=max_drift;
            policy.require_authenticated_observations=require_auth!=0;
            if(!le_uwb_hub.configure(epoch,policy)){error("conflict","LE-UWB hub policy refused");continue;}
            ok(std::string("epoch=")+std::to_string(epoch)+" physicalOutputsArmed=0");
            continue;
        }
        if (command == "HUB_NODE" && parts.size() == 6) {
            std::uint64_t node_id=0,presentation_delay=0;unsigned int stream_id=0,role=0,required=0;
            if(!parse_number(parts[1],node_id)||!parse_number(parts[2],stream_id)||!parse_number(parts[3],role)||
               !parse_number(parts[4],presentation_delay)||!parse_number(parts[5],required)||role>4||required>1||
               !le_uwb_hub.register_node({node_id,stream_id,static_cast<stageforge::LeUwbNodeRole>(role),presentation_delay,required!=0})){
                error("argument","invalid LE-UWB node");continue;}
            ok(std::string("nodeId=")+std::to_string(node_id)+" registered=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "HUB_UWB" && parts.size() == 10) {
            std::uint64_t node_id=0,sequence=0,epoch=0,hub_ns=0,node_ns=0,clock_uncertainty=0;
            double distance_mm=0.0,range_uncertainty_mm=0.0;unsigned int authenticated=0;
            if(!parse_number(parts[1],node_id)||!parse_number(parts[2],sequence)||!parse_number(parts[3],epoch)||
               !parse_number(parts[4],hub_ns)||!parse_number(parts[5],node_ns)||!parse_number(parts[6],distance_mm)||
               !parse_number(parts[7],range_uncertainty_mm)||!parse_number(parts[8],clock_uncertainty)||
               !parse_number(parts[9],authenticated)||authenticated>1||
               !le_uwb_hub.observe_uwb(node_id,sequence,epoch,hub_ns,node_ns,distance_mm,range_uncertainty_mm,clock_uncertainty,authenticated!=0)){
                error("evidence","UWB observation refused");continue;}
            ok(std::string("nodeId=")+std::to_string(node_id)+" uwbSequence="+std::to_string(sequence));
            continue;
        }
        if (command == "HUB_LE" && parts.size() == 9) {
            std::uint64_t node_id=0,sequence=0,epoch=0,event_counter=0,hub_ns=0,latency_ns=0,jitter_ns=0;unsigned int authenticated=0;
            if(!parse_number(parts[1],node_id)||!parse_number(parts[2],sequence)||!parse_number(parts[3],epoch)||
               !parse_number(parts[4],event_counter)||!parse_number(parts[5],hub_ns)||!parse_number(parts[6],latency_ns)||
               !parse_number(parts[7],jitter_ns)||!parse_number(parts[8],authenticated)||authenticated>1||
               !le_uwb_hub.observe_le(node_id,sequence,epoch,event_counter,hub_ns,latency_ns,jitter_ns,authenticated!=0)){
                error("evidence","LE isochronous observation refused");continue;}
            ok(std::string("nodeId=")+std::to_string(node_id)+" leSequence="+std::to_string(sequence)+" eventCounter="+std::to_string(event_counter));
            continue;
        }
        if (command == "HUB_PLAN" && parts.size() == 4) {
            std::uint64_t hub_now=0,show_now=0,epoch=0;
            if(!parse_number(parts[1],hub_now)||!parse_number(parts[2],show_now)||!parse_number(parts[3],epoch)){
                error("argument","invalid LE-UWB plan request");continue;}
            const auto plan=le_uwb_hub.plan(hub_now,show_now,epoch);
            std::cout<<"OK generation="<<plan.generation<<" epoch="<<plan.authority_epoch<<" ready="<<(plan.ready?1:0)
                     <<" targetHubNs="<<plan.target_hub_ns<<" targetShowNs="<<plan.target_show_ns
                     <<" leadNs="<<plan.presentation_lead_ns<<" configured="<<plan.configured_nodes
                     <<" required="<<plan.required_nodes<<" readyNodes="<<plan.ready_nodes
                     <<" holdover="<<plan.holdover_nodes<<" blocked="<<plan.blocked_nodes
                     <<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "HUB_TARGET" && parts.size() == 3) {
            std::uint64_t node_id=0,generation=0,target=0;
            if(!parse_number(parts[1],node_id)||!parse_number(parts[2],generation)||
               !le_uwb_hub.target_for(node_id,generation,target)){error("not_ready","LE-UWB target unavailable");continue;}
            std::cout<<"OK nodeId="<<node_id<<" generation="<<generation<<" targetNodeNs="<<target<<"\n"<<std::flush;
            continue;
        }
        if (command == "HUB_STATUS" && parts.size() == 2) {
            std::uint64_t node_id=0;stageforge::LeUwbNodeStatus status{};
            if(!parse_number(parts[1],node_id)||!le_uwb_hub.status(node_id,status)){error("not_found","LE-UWB node unavailable");continue;}
            std::cout<<"OK nodeId="<<status.descriptor.node_id<<" streamId="<<status.descriptor.le_stream_id
                     <<" role="<<static_cast<unsigned int>(status.descriptor.role)<<" state="<<static_cast<unsigned int>(status.state)
                     <<" required="<<(status.descriptor.required?1:0)<<" epoch="<<status.authority_epoch
                     <<" uwbSequence="<<status.uwb_sequence<<" leSequence="<<status.le_sequence
                     <<" eventCounter="<<status.le_event_counter<<" distanceMm="<<status.distance_mm
                     <<" rangeUncertaintyMm="<<status.range_uncertainty_mm<<" clockUncertaintyNs="<<status.clock_uncertainty_ns
                     <<" clockOffsetNs="<<status.clock_offset_ns<<" driftPpm="<<status.drift_ppm
                     <<" transportLatencyNs="<<status.transport_latency_ns<<" jitterNs="<<status.jitter_ns
                     <<" authenticated="<<(status.authenticated?1:0)<<" rejected="<<status.rejected_observations
                     <<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if(command=="RT_AUDIT_STATUS"&&parts.size()==2){unsigned int slot=0;if(!parse_number(parts[1],slot)||slot>=kAudioOutputSlots){error("argument","invalid audit output slot");continue;}const auto s=realtime_audits[slot].status();std::cout<<"OK slot="<<slot<<" callbacks="<<s.callbacks<<" deadlineMisses="<<s.deadline_misses<<" consecutiveMisses="<<s.consecutive_misses<<" maxDurationNs="<<s.max_duration_ns<<" nonfiniteSamples="<<s.nonfinite_samples<<" queuePressureEvents="<<s.queue_pressure_events<<" optionalShedBlocks="<<s.optional_shed_blocks<<" recoveryTransitions="<<s.recovery_transitions<<" allocationAttempts="<<s.allocation_attempts<<" allocatedBytes="<<s.allocated_bytes<<" lockAttempts="<<…47 tokens truncated…      if(command=="PDC_PREPARE"&&parts.size()>=5){std::uint64_t generation=0,show_ns=0;unsigned int count=0;if(!parse_number(parts[1],generation)||!parse_number(parts[2],show_ns)||!parse_number(parts[3],count)||count==0||count>kAudioOutputSlots||parts.size()!=4+count){error("argument","invalid delay graph plan");continue;}std::array<std::uint32_t,kAudioOutputSlots>latencies{};bool valid=true;for(unsigned int i=0;i<count;++i)valid=valid&&parse_number(parts[4+i],latencies[i]);if(!valid||!effect_delay_transaction.prepare(generation,show_ns,latencies.data(),count,nullptr,0)){error("conflict","delay graph plan refused");continue;}ok("prepared=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="FXPDC_PREPARE"&&parts.size()>=6){
            std::uint64_t generation=0,show_ns=0;unsigned int paths=0;
            if(!parse_number(parts[1],generation)||!parse_number(parts[2],show_ns)||!parse_number(parts[3],paths)||paths==0||paths>kAudioOutputSlots||parts.size()<5+paths){error("argument","invalid effect/delay transaction");continue;}
            std::array<std::uint32_t,kAudioOutputSlots>latencies{};bool valid=true;for(unsigned int i=0;i<paths;++i)valid=valid&&parse_number(parts[4+i],latencies[i]);
            unsigned int changes=0;const auto change_count_index=4+paths;if(!valid||!parse_number(parts[change_count_index],changes)||changes>kAudioOutputSlots*16||parts.size()!=change_count_index+1+changes*3){error("argument","invalid effect/delay transaction");continue;}
            std::array<EngineEffectDelayTransaction::Change,kAudioOutputSlots*16>staged{};for(unsigned int i=0;i<changes;++i){unsigned int output=0,bypassed=0;const auto offset=change_count_index+1+i*3;if(!parse_number(parts[offset],output)||!parse_number(parts[offset+1],staged[i].effect_id)||!parse_number(parts[offset+2],bypassed)||output>=kAudioOutputSlots||bypassed>1){valid=false;break;}staged[i].output=static_cast<std::uint8_t>(output);staged[i].bypassed=bypassed!=0;}
            if(!valid||!effect_delay_transaction.prepare(generation,show_ns,latencies.data(),paths,staged.data(),changes)){error("conflict","effect/delay transaction refused");continue;}ok("prepared=1 atomicEffectDelay=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="FXPDC_ROLLBACK"&&parts.size()==3){std::uint64_t generation=0,show_ns=0;if(!parse_number(parts[1],generation)||!parse_number(parts[2],show_ns)||!effect_delay_transaction.prepare_rollback(generation,show_ns)){error("conflict","effect/delay rollback refused");continue;}ok("prepared=1 rollback=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="PDC_ACTIVATE"&&parts.size()==2){std::uint64_t show_ns=0;if(!parse_number(parts[1],show_ns)||!effect_delay_transaction.activate(show_ns)){error("not_ready","delay graph activation boundary not reached");continue;}ok("activated=1 physicalOutputsArmed=0");
            continue;
        }
        if(command=="PDC_STATUS"){const auto s=effect_delay_transaction.status();std::cout<<"OK activeGeneration="<<s.active_generation<<" preparedGeneration="<<s.prepared_generation<<" activationShowNs="<<s.activation_show_ns<<" paths="<<s.paths<<" changes="<<s.changes<<" maximumLatencyFrames="<<s.maximum_latency_frames<<" swaps="<<s.commits<<" rollbacks="<<s.rollbacks<<" rejected="<<s.rejected<<" processedFrames="<<s.processed_frames<<" prepared="<<(s.prepared?1:0)<<" transactionConnected=1 audioGraphConnected=1 pathBinding=output-slot-index physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "EFFECT_STATUS" && parts.size() == 2) {
            unsigned int output = 0;
            if (!parse_number(parts[1], output) || output >= kAudioOutputSlots) { error("argument", "invalid effect output slot"); continue; }
            const auto st = effect_chains[output].status();
            std::cout << "OK output=" << output << " registered=" << st.registered << " active=" << st.active
                      << " bypassed=" << st.bypassed << " latencyFrames=" << st.total_latency_frames
                      << " processedBlocks=" << st.processed_blocks << " failures=" << st.failures << '\n' << std::flush;
            continue;
        }
        if (command == "EFFECT_BYPASS" && parts.size() == 4) {
            unsigned int output = 0, enabled = 0; std::uint64_t effect_id = 0;
            if (!parse_number(parts[1], output) || !parse_number(parts[2], effect_id) || !parse_number(parts[3], enabled) ||
                output >= kAudioOutputSlots || !effect_chains[output].set_bypass(effect_id, enabled != 0)) {
                error("not_found", "effect bypass target unavailable"); continue;
            }
            ok(std::string("bypassed=") + (enabled ? "1" : "0"));
            continue;
        }
        if (command == "MONITOR_SET" && parts.size() == 4) {
            double value = 0.0;
            if (!parse_number(parts[3], value)) { error("argument", "invalid monitor value"); continue; }
            const auto result = core.mutate_monitor(next_core_command_id++, stageforge::core_any_revision, parts[1], parts[2], value);
            if (!result.applied()) { error("core", stageforge::core_mutation_status_name(result.status)); continue; }
            auto* bus = monitors.find(parts[1]);
            if (!bus) { error("not_found", "unknown player"); continue; }
            if (!monitor_router.sync(parts[1], *bus, audio_graph)) {
                error("busy", "no monitor graph output available"); continue;
            }
            write_monitor(parts[1], *bus);
            continue;
        }
        if (command == "MONITOR_GET" && parts.size() == 2) {
            auto* bus = monitors.find(parts[1]);
            if (!bus) { error("not_found", "unknown player"); continue; }
            write_monitor(parts[1], *bus);
            continue;
        }
        if (command == "PARAM_BIND_AUDIO_MASTER" && parts.size() == 7) {
            std::uint64_t target=0, parameter=0; unsigned int output=0; float minv=0, maxv=0, defv=0;
            if (!parse_number(parts[1],target)||!parse_number(parts[2],parameter)||!parse_number(parts[3],output)||
                !parse_number(parts[4],minv)||!parse_number(parts[5],maxv)||!parse_number(parts[6],defv)||output>=stageforge::audio_graph_max_outputs) {
                error("argument","invalid audio master parameter binding"); continue;
            }
            auto* ctx=allocate_parameter_context(); if(!ctx){error("capacity","parameter endpoint capacity");continue;}
            ctx->kind=EngineParameterEndpointContext::Kind::audio_master;ctx->graph=&audio_graph;ctx->output=static_cast<std::uint8_t>(output);
            stageforge::CoreParameterDescriptor d{target,parameter,stageforge::CoreParameterUnit::linear,stageforge::CoreParameterTiming::block,
                stageforge::CoreParameterSafety::normal,stageforge::CoreParameterEndpointKind::mixer_gain,minv,maxv,defv,0.0F,true,true,true};
            if(!parameter_registry.register_endpoint(d,&apply_engine_parameter,ctx)){--parameter_endpoint_context_count;error("conflict","parameter registration refused");continue;}
            (void)automation_state.seed(target,parameter,defv); ok("registered=1 endpoint=audio-master");
            continue;
        }
        if (command == "PARAM_BIND_AUDIO_ROUTE" && parts.size() == 8) {
            std::uint64_t target=0, parameter=0; unsigned int source=0,output=0; float minv=0,maxv=0,defv=0;
            if(!parse_number(parts[1],target)||!parse_number(parts[2],parameter)||!parse_number(parts[3],source)||!parse_number(parts[4],output)||
               !parse_number(parts[5],minv)||!parse_number(parts[6],maxv)||!parse_number(parts[7],defv)||source>=stageforge::audio_graph_max_sources||output>=stageforge::audio_graph_max_outputs){error("argument","invalid audio route parameter binding");continue;}
            auto* ctx=allocate_parameter_context();if(!ctx){error("capacity","parameter endpoint capacity");continue;}
            ctx->kind=EngineParameterEndpointContext::Kind::audio_route;ctx->graph=&audio_graph;ctx->source=static_cast<std::uint8_t>(source);ctx->output=static_cast<std::uint8_t>(output);
            stageforge::CoreParameterDescriptor d{target,parameter,stageforge::CoreParameterUnit::linear,stageforge::CoreParameterTiming::block,
                stageforge::CoreParameterSafety::normal,stageforge::CoreParameterEndpointKind::mixer_gain,minv,maxv,defv,0.0F,true,true,false};
            if(!parameter_registry.register_endpoint(d,&apply_engine_parameter,ctx)){--parameter_endpoint_context_count;error("conflict","parameter registration refused");continue;}
            (void)automation_state.seed(target,parameter,defv); ok("registered=1 endpoint=audio-route");
            continue;
        }
        if (command == "PARAM_BIND_MONITOR_MASTER" && parts.size() == 7) {
            std::uint64_t target=0,parameter=0;float minv=0,maxv=0,defv=0;
            if(!parse_number(parts[1],target)||!parse_number(parts[2],parameter)||parts[3].empty()||parts[3].size()>=64||!parse_number(parts[4],minv)||!parse_number(parts[5],maxv)||!parse_number(parts[6],defv)){error("argument","invalid monitor parameter binding");continue;}
            auto& bus=monitors.get_or_create(parts[3]);(void)monitor_router.sync(parts[3],bus,audio_graph);
            auto* ctx=allocate_parameter_context();if(!ctx){error("capacity","parameter endpoint capacity");continue;}ctx->kind=EngineParameterEndpointContext::Kind::monitor_master;ctx->graph=&audio_graph;ctx->core=&core;ctx->monitor_router=&monitor_router;std::strncpy(ctx->player.data(),parts[3].c_str(),ctx->player.size()-1);
            stageforge::CoreParameterDescriptor d{target,parameter,stageforge::CoreParameterUnit::percent,stageforge::CoreParameterTiming::show,stageforge::CoreParameterSafety::normal,stageforge::CoreParameterEndpointKind::monitor_gain,minv,maxv,defv,0.0F,true,true,false};
            if(!parameter_registry.register_endpoint(d,&apply_engine_parameter,ctx)){--parameter_endpoint_context_count;error("conflict","parameter registration refused");continue;}(void)automation_state.seed(target,parameter,defv); ok("registered=1 endpoint=monitor-master");
            continue;
        }
        if (command == "PARAM_BIND_MONITOR_CHANNEL" && parts.size() == 8) {
            std::uint64_t target=0,parameter=0;float minv=0,maxv=0,defv=0;stageforge::MonitorChannel channel{};
            if(!parse_number(parts[1],target)||!parse_number(parts[2],parameter)||parts[3].empty()||parts[3].size()>=64||!stageforge::MonitorBus::parse_channel(parts[4],channel)||!parse_number(parts[5],minv)||!parse_number(parts[6],maxv)||!parse_number(parts[7],defv)){error("argument","invalid monitor channel parameter binding");continue;}
            auto& bus=monitors.get_or_create(parts[3]);(void)monitor_router.sync(parts[3],bus,audio_graph);
            auto* ctx=allocate_parameter_context();if(!ctx){error("capacity","parameter endpoint capacity");continue;}ctx->kind=EngineParameterEndpointContext::Kind::monitor_channel;ctx->graph=&audio_graph;ctx->core=&core;ctx->monitor_router=&monitor_router;ctx->monitor_channel=channel;std::strncpy(ctx->player.data(),parts[3].c_str(),ctx->player.size()-1);
            stageforge::CoreParameterDescriptor d{target,parameter,stageforge::CoreParameterUnit::percent,stageforge::CoreParameterTiming::show,stageforge::CoreParameterSafety::normal,stageforge::CoreParameterEndpointKind::monitor_gain,minv,maxv,defv,0.0F,true,true,false};
            if(!parameter_registry.register_endpoint(d,&apply_engine_parameter,ctx)){--parameter_endpoint_context_count;error("conflict","parameter registration refused");continue;}(void)automation_state.seed(target,parameter,defv); ok("registered=1 endpoint=monitor-channel");
            continue;
        }
        if (command == "PARAM_BIND_LIGHT" && parts.size() == 8) {
            std::uint64_t target=0,parameter=0;unsigned int universe=0,channel=0;float minv=0,maxv=0,defv=0;
Warning: truncated output (original token count: 6312)
Total output lines: 250

            if(!parse_number(parts[1],target)||!parse_number(parts[2],parameter)||!parse_number(parts[3],universe)||!parse_number(parts[4],channel)||!parse_number(parts[5],minv)||!parse_number(parts[6],maxv)||!parse_number(parts[7],defv)||universe>=dmx_universes.size()||channel<1||channel>512){error("argument","invalid lighting parameter binding");continue;}
            auto* ctx=allocate_parameter_context();if(!ctx){error("capacity","parameter endpoint capacity");continue;}ctx->kind=EngineParameterEndpointContext::Kind::lighting;ctx->dmx=&dmx_universes;ctx->universe=static_cast<std::uint16_t>(universe);ctx->channel=static_cast<std::uint16_t>(channel);
            stageforge::CoreParameterDescriptor d{target,parameter,stageforge::CoreParameterUnit::dmx,stageforge::CoreParameterTiming::show,stageforge::CoreParameterSafety::physical_output,stageforge::CoreParameterEndpointKind::lighting,minv,maxv,defv,0.0F,true,true,false};
            if(!parameter_registry.register_endpoint(d,&apply_engine_parameter,ctx)){--parameter_endpoint_context_count;error("conflict","parameter registration refused");continue;}(void)automation_state.seed(target,parameter,defv); ok("registered=1 endpoint=lighting");
            continue;
        }
        if (command == "PARAM_STATUS") {
            const auto m=parameter_registry.metrics();std::cout<<"OK registered="<<m.registered<<" applications="<<m.applications<<" rejected="<<m.rejected<<" clamps="<<m.clamps<<'\n'<<std::flush;
            continue;
        }
        if (command == "PARAM_GET" && parts.size()==3) {
            std::uint64_t target=0,parameter=0;if(!parse_number(parts[1],target)||!parse_number(parts[2],parameter)){error("argument","invalid parameter identity");continue;}stageforge::CoreParameterStatus st{};if(!parameter_registry.status(target,parameter,st)){error("not_found","parameter not registered");continue;}
            std::cout<<"OK targetId="<<target<<" parameterId="<<parameter<<" value="<<std::setprecision(9)<<st.last_applied<<" applications="<<st.applications<<" automationRevision="<<st.automation_revision<<" timing="<<static_cast<unsigned>(st.descriptor.timing)<<" endpoint="<<static_cast<unsigned>(st.descriptor.endpoint_kind)<<'\n'<<std::flush;
            continue;
        }
        if (command == "CUE_GRAPH_BEGIN" && parts.size()==2) {
            if(!parse_number(parts[1],staged_cue_graph_id)||staged_cue_graph_id==0){error("argument","invalid cue id");continue;}staged_cue_action_count=0;ok("staged=1");
            continue;
        }
        if (command == "CUE_GRAPH_ADD_AUTOMATION" && parts.size()==7) {
            if(staged_cue_graph_id==0||staged_cue_action_count>=staged_cue_actions.size()){error("state","cue graph not open or full");continue;}std::uint64_t target=0,param=0,owner=0;float value=0;unsigned int duration=0,offset_ms=0;
            if(!parse_number(parts[1],target)||!parse_number(parts[2],param)||!parse_number(parts[3],value)||!parse_number(parts[4],duration)||!parse_number(parts[5],owner)||!parse_number(parts[6],offset_ms)){error("argument","invalid cue automation action");continue;}
            auto&a=staged_cue_actions[staged_cue_action_count++];a={};a.type=stageforge::CueActionType::automation;a.owner_id=owner;a.offset_ns=static_cast<std::uint64_t>(offset_ms)*1'000'000ULL;a.payload.automation={target,param,value,duration};ok("action=automation");
            continue;
        }
        if (command == "CUE_GRAPH_ADD_TRANSPORT" && parts.size()==4) {
            if(staged_cue_graph_id==0||staged_cue_action_count>=staged_cue_actions.size()){error("state","cue graph not open or full");continue;}sf_core_transport_action action{};if(parts[1]=="play")action=SF_CORE_TRANSPORT_PLAY;else if(parts[1]=="pause")action=SF_CORE_TRANSPORT_PAUSE;else if(parts[1]=="bpm")action=SF_CORE_TRANSPORT_SET_BPM;else if(parts[1]=="seek")action=SF_CORE_TRANSPORT_SEEK_SECONDS;else{error("argument","invalid transport action");continue;}double value=0;unsigned int offset_ms=0;if(!parse_number(parts[2],value)||!parse_number(parts[3],offset_ms)){error("argument","invalid transport cue action");continue;}auto&a=staged_cue_actions[staged_cue_action_count++];a={};a.type=stageforge::CueActionType::transport;a.offset_ns=static_cast<std::uint64_t>(offset_ms)*1'000'000ULL;a.payload.transport={action,value};ok("action=transport");
            continue;
        }
        if (command == "CUE_GRAPH_ADD_MIDI" && parts.size()==6) {
            if(staged_cue_graph_id==0||staged_cue_action_count>=staged_cue_actions.size()){error("state","cue graph not open or full");continue;}unsigned int status=0,d1=0,d2=0,port=0,offset_ms=0;if(!parse_number(parts[1],status)||!parse_number(parts[2],d1)||!parse_number(parts[3],d2)||!parse_number(parts[4],port)||!parse_number(parts[5],offset_ms)||status<0x80||status>255||d1>127||d2>127||port>255){error("argument","invalid MIDI cue action");continue;}auto&a=staged_cue_actions[staged_cue_action_count++];a={};a.type=stageforge::CueActionType::midi;a.offset_ns=static_cast<std::uint64_t>(offset_ms)*1'000'000ULL;a.payload.midi={static_cast<std::uint8_t>(status),static_cast<std::uint8_t>(d1),static_cast<std::uint8_t>(d2),static_cast<std::uint8_t>(port)};ok("action=midi");
            continue;
        }
        if (command == "CUE_GRAPH_ADD_LIGHT" && parts.size()==5) {
            if(staged_cue_graph_id==0||staged_cue_action_count>=staged_cue_actions.size()){error("state","cue graph not open or full");continue;}unsigned int universe=0,channel=0,value=0,offset_ms=0;if(!parse_number(parts[1],universe)||!parse_number(parts[2],channel)||!parse_number(parts[3],value)||!parse_number(parts[4],offset_ms)||channel<1||channel>512||value>255||universe>65535){error("argument","invalid lighting cue action");continue;}auto&a=staged_cue_actions[staged_cue_action_count++];a={};a.type=stageforge::CueActionType::lighting;a.offset_ns=static_cast<std::uint64_t>(offset_ms)*1'000'000ULL;a.payload.lighting={static_cast<std::uint16_t>(universe),static_cast<std::uint16_t>(channel),static_cast<std::uint8_t>(value),{0,0,0}};ok("action=lighting");
            continue;
        }
        if (command == "CUE_GRAPH_COMMIT") {
            if(staged_cue_graph_id==0||!cue_graph.define(staged_cue_graph_id,staged_cue_actions.data(),staged_cue_action_count)){error("state","cue graph commit refused");continue;}std::cout<<"OK cueId="<<staged_cue_graph_id<<" actions="<<staged_cue_action_count<<" revision="<<cue_graph.revision()<<'\n'<<std::flush;staged_cue_graph_id=0;staged_cue_action_count=0;
            continue;
        }
        if (command == "SHOW_COMPILE_BEGIN" && parts.size()==3) {
            std::uint64_t rev=0,hash=0;if(!parse_number(parts[1],rev)||!parse_number(parts[2],hash)){error("argument","invalid runtime show identity");continue;}runtime_show.begin(rev,hash);ok("compile=begin");
            continue;
        }
        if (command == "SHOW_COMPILE_ROLE" && parts.size()==3) {
            std::uint64_t id=0;unsigned int mask=0;if(!parse_number(parts[1],id)||!parse_number(parts[2],mask)||!runtime_show.add_role({id,mask})){error("argument","runtime role refused");continue;}ok("compile=role");
            continue;
        }
        if (command == "SHOW_COMPILE_CUE" && parts.size()==3) {
            std::uint64_t id=0,hash=0;if(!parse_number(parts[1],id)||!parse_number(parts[2],hash)||!runtime_show.add_cue({id,hash})){error("argument","runtime cue refused");continue;}ok("compile=cue");
            continue;
        }
        if (command == "SHOW_COMPILE_ROUTE" && parts.size()==5) {
            std::uint64_t from=0,to=0;unsigned int channels=0,timing=0;if(!parse_number(parts[1],from)||!parse_number(parts[2],to)||!parse_number(parts[3],channels)||!parse_number(parts[4],timing)||!runtime_show.add_route({from,to,static_cast<std::uint16_t>(channels),static_cast<std::uint8_t>(timing),true})){error("argument","runtime route refused");continue;}ok("compile=route");
            continue;
        }
        if (command == "SHOW_COMPILE_PARAM" && parts.size()==8) {
            std::uint64_t target=0,param=0;float minv=0,maxv=0,defv=0;unsigned int timing=0,unit=0;
            if(!parse_number(parts[1],target)||!parse_number(parts[2],param)||!parse_number(parts[3],minv)||!parse_number(parts[4],maxv)||!parse_number(parts[5],defv)||!parse_number(parts[6],timing)||!parse_number(parts[7],unit)){error("argument","invalid runtime parameter");continue;}
            stageforge::CoreParameterDescriptor d{};d.target_id=target;d.parameter_id=param;d.minimum=minv;d.maximum=maxv;d.default_value=defv;d.timing=static_cast<stageforge::CoreParameterTiming>(timing);d.unit=static_cast<stageforge::CoreParameterUnit>(unit);
            if(!runtime_show.add_parameter(d)){error("capacity","runtime parameter refused");continue;}ok("compile=parameter");
            continue;
        }
        if (command == "SHOW_COMPILE_COMMIT" && parts.size()==2) {
            std::uint64_t boundary=0;if(!parse_number(parts[1],boundary)||!runtime_show.queue_publish(boundary)){error("conflict","runtime generation publish refused");continue;}show_loop.wake();const auto st=runtime_show.status();std::cout<<"OK pendingGeneration="<<st.pending_generation<<" boundaryShowNs="<<boundary<<'\n'<<std::flush;
            continue;
        }
        if (command == "SHOW_RUNTIME_STATUS") {
            const auto st=runtime_show.status();const auto snap=runtime_show.snapshot();std::cout<<"OK generation="<<st.active_generation<<" pendingGeneration="<<st.pending_generation<<" sourceRevision="<<st.source_revision<<" pending="<<(st.pending?1:0)<<" swaps="<<st.swaps<<" rejected="<<st.rejected<<" roles="<<snap.role_count<<" cues="<<snap.cue_count<<" routes="<<snap.route_count<<" parameters="<<snap.parameter_count<<'\n'<<std::flush;
            continue;
        }
        if (command == "ROUTE_TX_BEGIN" && parts.size()==2) {
            std::uint64_t expected=0;if(!parse_number(parts[1],expected)||!routing_state.begin(expected)){error("conflict","routing transaction begin refused");continue;}staged_audio_route_change_count=0;ok("routing=staged");
            continue;
        }
        if (command == "ROUTE_TX_SET" && parts.size()==6) {
            std::uint64_t from=0,to=0;unsigned int channels=0,timing=0,enabled=0;if(!parse_number(parts[1],from)||!parse_number(parts[2],to)||!parse_number(parts[3],channels)||!parse_number(parts[4],timing)||!parse_number(parts[5],enabled)||!routing_state.set({from,to,static_cast<std::uint16_t>(channels),static_cast<std::uint8_t>(timing),enabled!=0})){error("argument","routing edge refused");continue;}ok("routing=edge");
            continue;
        }
        if (command == "ROUTE_TX_AUDIO" && parts.size()==5) {
            unsigned int source=0,output=0,enabled=0;float gain=0.0F;if(!parse_number(parts[1],source)||!parse_number(parts[2],output)||!parse_number(parts[3],gain)||!parse_number(parts[4],enabled)||source>=stageforge::audio_graph_max_sources||output>=stageforge::audio_graph_max_outputs||staged_audio_route_change_count>=staged_audio_route_changes.size()){error("argument","invalid audio routing transaction edge");continue;}
            const std::uint64_t from=1ULL+source;const std::uint64_t to=1001ULL+output;if(!routing_state.set({from,to,2,0,enabled!=0})){error("argument","audio routing graph edge refused");continue;}staged_audio_route_changes[staged_audio_route_change_count++]={static_cast<std::uint8_t>(source),static_cast<std::uint8_t>(output),enabled!=0?gain:0.0F};ok("routing=audio-edge");
            continue;
        }
        if (command == "ROUTE_TX_COMMIT") {
            if(!routing_state.commit()){error("invalid","routing graph contains cycle or transaction not open");continue;}
            if(staged_audio_route_change_count && !audio_graph.apply_route_transaction(std::span<const stageforge::AudioRouteChange>(staged_audio_route_changes.data(),staged_audio_route_change_count))){error("invalid","audio route publication refused");continue;}
            staged_audio_route_chan…312 tokens truncated…s="<<rec.show_ns<<" eventId="<<rec.event_id<<" subjectId="<<rec.subject_id<<" revision="<<rec.revision<<" previousHash="<<rec.previous_hash<<" hash="<<rec.hash<<'\n'<<std::flush;
            continue;
        }
        if (command == "SHADOW_DECLARE" && parts.size()==8) {
            stageforge::CoreShadowSource src{};unsigned int required=0,capable=0,asset=0;if(!parse_number(parts[1],src.id)||!parse_number(parts[2],src.show_revision)||!parse_number(parts[3],src.content_hash)||!parse_number(parts[4],src.generation)||!parse_number(parts[5],required)||!parse_number(parts[6],capable)||!parse_number(parts[7],asset)){error("argument","invalid shadow source");continue;}src.required=required!=0;src.capable=capable!=0;src.asset_ready=asset!=0;if(!shadow_planner.declare_source(src)){error("capacity","shadow source refused");continue;}ok("shadow=declared");
            continue;
        }
        if (command == "SHADOW_REPORT" && parts.size()==7) {
            std::uint64_t id=0,generation=0,rev=0,hash=0,until=0;unsigned int healthy=0;if(!parse_number(parts[1],id)||!parse_number(parts[2],generation)||!parse_number(parts[3],rev)||!parse_number(parts[4],hash)||!parse_number(parts[5],until)||!parse_number(parts[6],healthy)||!shadow_planner.report(id,generation,rev,hash,until,healthy!=0)){error("conflict","shadow report stale or unknown");continue;}ok("shadow=reported");
            continue;
        }
        if (command == "SHADOW_BLOCK" && parts.size()==9) {
            std::uint64_t id=0,generation=0,rev=0,hash=0,start=0,end=0;unsigned int frames=0,healthy=0;
            if(!parse_number(parts[1],id)||!parse_number(parts[2],generation)||!parse_number(parts[3],rev)||!parse_number(parts[4],hash)||!parse_number(parts[5],start)||!parse_number(parts[6],end)||!parse_number(parts[7],frames)||!parse_number(parts[8],healthy)){error("argument","invalid shadow block");continue;}
            if(!shadow_prebuffer.configure(id,generation,rev,hash)||!shadow_prebuffer.ingest_block(id,generation,rev,hash,start,end,frames,healthy!=0)){error("conflict","shadow block discontinuity or stale identity");continue;}
            stageforge::CoreShadowPrebufferStatus ps{};if(!shadow_prebuffer.status(id,ps)){error("state","shadow prebuffer status unavailable");continue;}
            if(!shadow_planner.report(id,generation,rev,hash,ps.buffered_until_show_ns,ps.healthy)){error("conflict","shadow planner rejected block evidence");continue;}
            std::cout<<"OK shadow=block bufferedUntilShowNs="<<ps.buffered_until_show_ns<<" renderedFrames="<<ps.rendered_frames<<" renderedBlocks="<<ps.rendered_blocks<<" discontinuities="<<ps.discontinuities<<'\n'<<std::flush;
            continue;
        }
        if (command == "SHADOW_INVALIDATE" && parts.size()==2) { std::uint64_t rev=0;if(!parse_number(parts[1],rev)){error("argument","invalid show revision");continue;}shadow_planner.invalidate_revision(rev);shadow_prebuffer.invalidate_revision(rev);ok("shadow=invalidated");
            continue;
        }
        if (command == "SHADOW_PLAN" && parts.size()==3) { std::uint64_t target=0,prebuffer=0;if(!parse_number(parts[1],target)||!parse_number(parts[2],prebuffer)){error("argument","invalid shadow plan");continue;}const auto st=shadow_planner.plan(target,prebuffer);std::cout<<"OK targetShowNs="<<st.target_show_ns<<" requiredUntilShowNs="<<st.required_until_show_ns<<" sources="<<st.sources<<" readySources="<<st.ready_sources<<" blockedSources="<<st.blocked_sources<<" ready="<<(st.ready?1:0)<<'\n'<<std::flush;
            continue;
        }
        if (command == "HANDOFF_TX_PREPARE" && parts.size()==6) {
            std::uint64_t id=0,source_epoch=0,target_epoch=0,target_show=0;unsigned int degraded=0;
            if(!parse_number(parts[1],id)||!parse_number(parts[2],source_epoch)||!parse_number(parts[3],target_epoch)||!parse_number(parts[4],target_show)||!parse_number(parts[5],degraded)||!planned_handoff.prepare(id,source_epoch,target_epoch,target_show,degraded!=0)){error("conflict","planned handoff prepare refused");continue;}ok("handoff=prepared");
            continue;
        }
        if (command == "HANDOFF_TX_ACK" && parts.size()==3) {
            std::uint64_t id=0;unsigned int ready=0;if(!parse_number(parts[1],id)||!parse_number(parts[2],ready)||!planned_handoff.acknowledge_target(id,ready!=0)){error("conflict","planned handoff acknowledgement refused");continue;}ok("handoff=target-ready");
            continue;
        }
        if (command == "HANDOFF_TX_COMMIT" && parts.size()==5) {
            std::uint64_t id=0,source_epoch=0,witness_epoch=0,show_ns=0;if(!parse_number(parts[1],id)||!parse_number(parts[2],source_epoch)||!parse_number(parts[3],witness_epoch)||!parse_number(parts[4],show_ns)||!planned_handoff.commit(id,source_epoch,witness_epoch,show_ns)){error("conflict","planned handoff commit refused");continue;}ok("handoff=committed physicalOutputsArmed=0");
            continue;
        }
        if (command == "HANDOFF_TX_ABORT" && parts.size()==2) {
            std::uint64_t id=0;if(!parse_number(parts[1],id)||!planned_handoff.abort(id)){error("conflict","planned handoff abort refused");continue;}ok("handoff=aborted");
            continue;
        }
        if (command == "HANDOFF_TX_STATUS") {
            const auto st=planned_handoff.status();std::cout<<"OK transactionId="<<st.transaction_id<<" state="<<static_cast<unsigned>(st.state)<<" sourceEpoch="<<st.source_epoch<<" targetEpoch="<<st.target_epoch<<" targetShowNs="<<st.target_show_ns<<" programReady="<<(st.program_ready?1:0)<<" authorityCommitted="<<(st.authority_committed?1:0)<<" physicalOutputsArmed=0 prepares="<<st.prepares<<" commits="<<st.commits<<" aborts="<<st.aborts<<" conflicts="<<st.conflicts<<'\n'<<std::flush;
            continue;
        }
        if (command == "EVENT_LOOP_STATUS") {
            const auto loop = show_loop.loop_metrics();
            const auto dispatch = show_loop.dispatch_metrics();
            std::cout << "OK running=" << (loop.running ? 1 : 0)
                      << " cycles=" << loop.cycles
                      << " wakeups=" << loop.wakeups
                      << " timedWaits=" << loop.timed_waits
                      << " loopDispatched=" << loop.dispatched
                      << " manualDrains=" << loop.manual_drains
                      << " cancelRequests=" << loop.cancel_requests
                      << " lastShowNs=" << loop.last_show_time_ns
                      << " pending=" << dispatch.pending
                      << " nextShowNs=" << dispatch.next_show_time_ns << '\n' << std::flush;
            continue;
        }
        if (command == "CUE_STATUS") {
            const auto cue = cue_state.snapshot();
            std::cout << "OK currentCueId=" << cue.current_cue_id
                      << " previousCueId=" << cue.previous_cue_id
                      << " lastEventId=" << cue.last_event_id
                      << " lastShowNs=" << cue.last_show_time_ns
                      << " transitions=" << cue.transitions << '\n' << std::flush;
            continue;
        }
        if (command == "AUTOMATION_STATUS") {
            const auto metrics = automation_state.metrics();
            std::cout << "OK revision=" << metrics.revision
                      << " registered=" << metrics.registered
                      << " applied=" << metrics.applied
                      << " ownerConflicts=" << metrics.owner_conflicts
                      << " capacityRejects=" << metrics.capacity_rejections
                      << " invalid=" << metrics.invalid
                      << " ownerReleases=" << metrics.owner_releases << '\n' << std::flush;
            continue;
        }
        if (command == "AUTOMATION_GET" && (parts.size() == 3 || parts.size() == 4)) {
            std::uint64_t target = 0, parameter = 0, show_ns = 0;
            if (!parse_number(parts[1], target) || !parse_number(parts[2], parameter) || target == 0 || parameter == 0) {
                error("argument", "invalid automation parameter"); continue;
            }
            if (parts.size() == 4) {
                if (!parse_number(parts[3], show_ns)) { error("argument", "invalid automation Show Time"); continue; }
            } else {
                const auto time = clock.snapshot();
                show_ns = static_cast<std::uint64_t>(std::max(0.0, time.show_seconds) * 1'000'000'000.0);
            }
            stageforge::AutomationParameterSnapshot state{};
            if (!automation_state.snapshot(target, parameter, show_ns, state)) { error("not_found", "automation parameter not registered"); continue; }
            std::cout << "OK targetId=" << state.target_id
                      << " parameterId=" << state.parameter_id
                      << " ownerId=" << state.owner_id
                      << " revision=" << state.revision
                      << " lastEventId=" << state.last_event_id
                      << " startShowNs=" << state.ramp_start_show_ns
                      << " endShowNs=" << state.ramp_end_show_ns
                      << " startValue=" << std::setprecision(9) << state.start_value
                      << " targetValue=" << std::setprecision(9) << state.target_value
                      << " value=" << std::setprecision(9) << state.current_value
                      << " ramping=" << (state.ramping ? 1 : 0)
                      << " updates=" << state.updates << '\n' << std::flush;
            continue;
        }
        if (command == "AUTOMATION_BLOCK" && parts.size() == 6) {
            std::uint64_t target = 0, parameter = 0, start_ns = 0, step_ns = 0;
            unsigned int frames = 0;
            if (!parse_number(parts[1], target) || !parse_number(parts[2], parameter) ||
                !parse_number(parts[3], start_ns) || !parse_number(parts[4], step_ns) ||
                !parse_number(parts[5], frames) || target == 0 || parameter == 0 || frames == 0 || frames > 256) {
                error("argument", "invalid automation block request"); continue;
            }
            std::array<float, 256> values{};
            if (!automation_state.render_block(target, parameter, start_ns, step_ns, values.data(), frames)) {
                error("not_found", "automation parameter not registered"); continue;
            }
            float minimum = values[0], maximum = values[0];
            for (unsigned int index = 1; index < frames; ++index) {
                minimum = std::min(minimum, values[index]);
                maximum = std::max(maximum, values[index]);
            }
            std::cout << "OK frames=" << frames << " first=" << std::setprecision(9) << values[0]
                      << " last=" << std::setprecision(9) << values[frames - 1]
                      << " min=" << std::setprecision(9) << minimum << " max=" << std::setprecision(9) << maximum << '\n' << std::flush;
            continue;
        }
        if (command == "EVENT_STATUS") {
            const auto metrics = show_loop.dispatch_metrics();
            std::cout << "OK submitted=" << metrics.submitted
                      << " accepted=" << metrics.accepted
                      << " dispatched=" << metrics.dispatched
                      << " pending=" << metrics.pending
                      << " nextShowNs=" << metrics.next_show_time_ns
                      << " duplicates=" << metrics.duplicates
                      << " invalid=" << metrics.invalid
                      << " ingressOverflow=" << metrics.ingress_overflow
                      << " timelineOverflow=" << metrics.timeline_overflow
                      << " late=" << metrics.late
                      << " droppedLate=" << metrics.dropped_late
                      << " failures=" << metrics.dispatch_failures
                      << " cancelled=" << metrics.cancelled << '\n' << std::flush;
            continue;
        }
        if (command == "EVENT_DRAIN" && parts.size() == 2) {
            std::uint64_t now_ns = 0;
            if (!parse_number(parts[1], now_ns)) { error("argument", "invalid event drain time"); continue; }
            const auto routed = show_loop.drain_until(now_ns);
            const auto metrics = show_loop.dispatch_metrics();
            std::cout << "OK routed=" << routed << " pending=" << metrics.pending
                      << " dispatched=" << metrics.dispatched << " late=" << metrics.late << '\n' << std::flush;
            continue;
        }
        if (command == "EVENT_CANCEL" && parts.size() == 3) {
            stageforge::ShowEventType type{};
            if (parts[1] == "TRANSPORT") type = stageforge::ShowEventType::transport;
            else if (parts[1] == "MIDI") type = stageforge::ShowEventType::midi;
            else if (parts[1] == "LIGHT") type = stageforge::ShowEventType::lighting;
            else if (parts[1] == "CUE") type = stageforge::ShowEventType::cue;
            else if (parts[1] == "AUTOMATION") type = stageforge::ShowEventType::automation;
            else { error("argument", "invalid event type"); continue; }
            std::uint64_t event_id = 0;
            if (!parse_number(parts[2], event_id)) { error("argument", "invalid event id"); continue; }
            if (!show_loop.cancel(type, event_id)) { error("not_found", "event not pending"); continue; }
            ok(std::string("cancelled=1 eventId=") + std::to_string(event_id));
            continue;
        }
        if (command == "EVENT_NEXT" && parts.size() == 2) {
            stageforge::ShowEvent event{};
            bool available = false;
            if (parts[1] == "CUE") available = cue_events.try_pop(event);
            else if (parts[1] == "AUTOMATION") available = automation_events.try_pop(event);
            else { error("argument", "EVENT_NEXT supports CUE or AUTOMATION"); continue; }
            if (!available) { ok("available=0"); continue; }
            std::cout << "OK available=1 eventId=" << event.event_id << " showNs=" << event.show_time_ns
                      << " type=" << parts[1];
            if (event.type == stageforge::ShowEventType::cue) std::cout << " cueId=" << event.payload.cue.cue_id;
            else std::cout << " targetId=" << event.payload.automation.target_id
                           << " parameterId=" << event.payload.automation.parameter_id
                           << " value=" << event.payload.automation.value
                           << " durationMs=" << event.payload.automation.duration_ms
                           << " ownerId=" << event.owner_id;
            std::cout << '\n' << std::flush;
            continue;
        }
        if (command == "EVENT_SUBMIT" && parts.size() >= 2) {
            stageforge::ShowEvent event{};
            event.revision = core.metrics().revision;
            unsigned int priority = SF_PRIORITY_SHOW;
            bool parsed = false;
            if (parts[1] == "MIDI" && parts.size() == 8) {
                unsigned int status = 0, data1 = 0, data2 = 0;
                parsed = parse_number(parts[2], event.event_id) && parse_number(parts[3], event.show_time_ns) &&
                         parse_number(parts[4], priority) && parse_number(parts[5], status) && parse_number(parts[6], data1) && parse_number(parts[7], data2) &&
                         priority <= SF_PRIORITY_BACKGROUND && status <= 255 && data1 <= 127 && data2 <= 127;
                event.type = stageforge::ShowEventType::midi;
                event.payload.midi = {static_cast<std::uint8_t>(status), static_cast<std::uint8_t>(data1), static_cast<std::uint8_t>(data2), 0};
            } else if (parts[1] == "LIGHT" && parts.size() == 8) {
                unsigned int universe = 0, channel = 0, value = 0;
                parsed = parse_number(parts[2], event.event_id) && parse_number(parts[3], event.show_time_ns) &&
                         parse_number(parts[4], priority) && parse_number(parts[5], universe) && parse_number(parts[6], channel) && parse_number(parts[7], value) &&
                         priority <= SF_PRIORITY_BACKGROUND && universe < dmx_universes.size() && channel >= 1 && channel <= 512 && value <= 255;
                event.type = stageforge::ShowEventType::lighting;
                event.payload.lighting = {static_cast<std::uint16_t>(universe), static_cast<std::uint16_t>(channel), static_cast<std::uint8_t>(value), {0,0,0}};
            } else if (parts[1] == "TRANSPORT" && parts.size() == 7) {
                double value = 0.0;
                sf_core_transport_action action{};
                if (parts[5] == "play") action = SF_CORE_TRANSPORT_PLAY;
                else if (parts[5] == "pause") action = SF_CORE_TRANSPORT_PAUSE;
                else if (parts[5] == "stop") action = SF_CORE_TRANSPORT_STOP;
                else if (parts[5] == "rewind") action = SF_CORE_TRANSPORT_REWIND;
                else if (parts[5] == "bpm") action = SF_CORE_TRANSPORT_SET_BPM;
                else if (parts[5] == "seek") action = SF_CORE_TRANSPORT_SEEK_SECONDS;
                else { error("argument", "invalid transport event action"); continue; }
                parsed = parse_number(parts[2], event.event_id) && parse_number(parts[3], event.show_time_ns) &&
                         parse_number(parts[4], priority) && parse_number(parts[6], value) && priority <= SF_PRIORITY_BACKGROUND;
                event.type = stageforge::ShowEventType::transport;
                event.flags = stageforge::show_event_authoritative;
                event.payload.transport = {action, value};
            } else if (parts[1] == "CUE" && parts.size() == 6) {
                std::uint64_t cue_id = 0;
                parsed = parse_number(parts[2], event.event_id) && parse_number(parts[3], event.show_time_ns) &&
                         parse_number(parts[4], priority) && parse_number(parts[5], cue_id) && priority <= SF_PRIORITY_BACKGROUND && cue_id != 0;
                event.type = stageforge::ShowEventType::cue;
                event.payload.cue = {cue_id};
            } else if (parts[1] == "AUTOMATION" && parts.size() >= 8 && parts.size() <= 10) {
                std::uint64_t target = 0, parameter = 0;
                std::uint64_t owner = 0;
                unsigned int duration_ms = 0;
                float value = 0.0F;
                parsed = parse_number(parts[2], event.event_id) && parse_number(parts[3], event.show_time_ns) &&
                         parse_number(parts[4], priority) && parse_number(parts[5], target) && parse_number(parts[6], parameter) && parse_number(parts[7], value) &&
                         priority <= SF_PRIORITY_BACKGROUND && target != 0 && parameter != 0;
                if (parsed && parts.size() >= 9) parsed = parse_number(parts[8], duration_ms);
                if (parsed && parts.size() == 10) parsed = parse_number(parts[9], owner);
                event.type = stageforge::ShowEventType::automation;
                event.owner_id = owner;
                event.payload.automation = {target, parameter, value, duration_ms};
            } else if (parts[1] == "AUTOMATION_RELEASE" && parts.size() == 8) {
                std::uint64_t target = 0, parameter = 0, owner = 0;
                parsed = parse_number(parts[2], event.event_id) && parse_number(parts[3], event.show_time_ns) &&
                         parse_number(parts[4], priority) && parse_number(parts[5], target) && parse_number(parts[6], parameter) && parse_number(parts[7], owner) &&
                         priority <= SF_PRIORITY_BACKGROUND && target != 0 && parameter != 0 && owner != 0;
                event.type = stageforge::ShowEventType::automation;
                event.owner_id = owner;
                event.flags = stageforge::show_event_automation_release_owner;
                event.payload.automation = {target, parameter, 0.0F, 0};
            }
            if (!parsed) { error("argument", "invalid typed show event"); continue; }
            event.priority = static_cast<sf_priority>(priority);
            if (!show_loop.submit(event)) { error("busy", "show event ingress rejected"); continue; }
            const auto metrics = show_loop.dispatch_metrics();
            ok(std::string("eventId=") + std::to_string(event.event_id) + " pending=" + std::to_string(metrics.pending));
            continue;
        }
        if (command == "MIDI_MAP_MASTER" && parts.size() == 4) {
            double bpm=0.0;unsigned int root=0,mask=0;
            if(!parse_number(parts[1],bpm)||!parse_number(parts[2],root)||!parse_number(parts[3],mask)||root>11||mask>0x0FFF){error("argument","invalid MIDI master mapping state");continue;}
            midi_mapping.configure_master(bpm,static_cast<std::uint8_t>(root),static_cast<std::uint16_t>(mask));
            ok("configured=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "MIDI_MAP_UPSERT" && parts.size() == 15) {
            stageforge::MidiLearnBinding binding{};unsigned int channel=0,number=0,message=0,behavior=0,action=0,steps=0,key_sync=0;
            if(!parse_number(parts[1],binding.mapping_id)||!parse_number(parts[2],binding.device_id)||!parse_number(parts[3],binding.target_id)||
               !parse_number(parts[4],binding.resource_id)||!parse_number(parts[5],binding.parameter_id)||!parse_number(parts[6],channel)||!parse_number(parts[7],number)||
               !parse_number(parts[8],message)||!parse_number(parts[9],behavior)||!parse_number(parts[10],action)||!parse_number(parts[11],steps)||
               !parse_number(parts[12],key_sync)||!parse_number(parts[13],binding.minimum)||!parse_number(parts[14],binding.maximum)||
               channel>15||number>127||message>3||behavior>4||action>6||steps>32||key_sync>1||binding.maximum<binding.minimum||
               (action>=4&&binding.resource_id==0)){error("argument","invalid MIDI mapping");continue;}
            binding.channel=static_cast<std::uint8_t>(channel);binding.number=static_cast<std::uint8_t>(number);binding.steps_per_beat=static_cast<std::uint8_t>(steps);
            binding.message=static_cast<stageforge::MidiLearnMessage>(message);binding.behavior=static_cast<stageforge::MidiMapBehavior>(behavior);
            binding.action=static_cast<stageforge::MidiMappedActionKind>(action);binding.key_sync=key_sync!=0;
            if(!midi_mapping.upsert(binding)){error("capacity","MIDI mapping refused");continue;}ok("mapped=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "MIDI_MAP_REMOVE" && parts.size() == 2) {
            std::uint64_t mapping_id=0;if(!parse_number(parts[1],mapping_id)||!midi_mapping.remove(mapping_id)){error("not_found","MIDI mapping unavailable");continue;}ok("removed=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "MIDI_MAP_CLEAR" && parts.size() == 1) {
            midi_mapping.clear();ok("cleared=1 physicalOutputsArmed=0");
            continue;
        }
        if (command == "MIDI_MAP_STATUS" && parts.size() == 1) {
            const auto mapping=midi_mapping.status();const auto dispatch=midi_action_dispatcher.status();
            std::cout<<"OK bindings="<<mapping.bindings<<" received="<<mapping.received<<" matched="<<mapping.matched<<" dropped="<<mapping.dropped
                     <<" queued="<<mapping.queued<<" submitted="<<dispatch.submitted<<" rejected="<<dispatch.rejected<<" ignored="<<dispatch.ignored
                     <<" lastEventId="<<dispatch.last_event_id<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "MIDI_SCHEDULE" && parts.size() == 6) {
            stageforge::ShowEvent event{};
            unsigned int status = 0, data1 = 0, data2 = 0;
            if (!parse_number(parts[1], event.event_id) || !parse_number(parts[2], event.show_time_ns) ||
                !parse_number(parts[3], status) || !parse_number(parts[4], data1) || !parse_number(parts[5], data2) ||
                status > 255 || data1 > 127 || data2 > 127) {
                error("argument", "invalid midi event"); continue;
            }
            event.type = stageforge::ShowEventType::midi;
            event.priority = SF_PRIORITY_SHOW;
            event.revision = core.metrics().revision;
            event.payload.midi = {static_cast<std::uint8_t>(status), static_cast<std::uint8_t>(data1), static_cast<std::uint8_t>(data2), 0};
            if (!show_loop.submit(event)) { error("busy", "show event ingress full"); continue; }
            const auto metrics = show_loop.dispatch_metrics();
            ok(std::string("queued=") + std::to_string(metrics.pending));
            continue;
        }
        if (command == "MIDI_DRAIN" && parts.size() == 2) {
            std::uint64_t now_ns = 0;
            if (!parse_number(parts[1], now_ns)) { error("argument", "invalid midi drain time"); continue; }
            (void)show_loop.drain_until(now_ns);
            (void)ingest_midi_domain();
            std::size_t count = 0;
            stageforge::MidiEvent event{};
            while (midi.pop_due(now_ns, event)) ++count;
            ok(std::string("drained=") + std::to_string(count) + " queued=" + std::to_string(midi.size()));
            continue;
        }
        if (command == "MIDI_SCAN") {
            const auto count = midi_inputs.scan();
            ok(std::string("count=") + std::to_string(count) + " attached=" + std::to_string(midi_inputs.attached_count()));
            continue;
        }
        if (command == "MIDI_DEVICE" && parts.size() == 2) {
            std::size_t index = 0;
            if (!parse_number(parts[1], index)) { error("argument", "invalid midi device index"); continue; }
            stageforge::MidiDeviceDescriptor device{};
            if (!midi_inputs.device(index, device)) { error("not_found", "unknown midi device index"); continue; }
            std::cout << "OK index=" << index
                      << " id=" << token_safe(device.id.data())
                      << " name=" << token_safe(device.name.data())
                      << " path=" << token_safe(device.path.data())
                      << " input=" << (device.input ? 1 : 0)
                      << " connected=" << (device.connected ? 1 : 0)
                      << " attached=" << (midi_inputs.attached(device.id.data()) ? 1 : 0) << '\n' << std::flush;
            continue;
        }
        if (command == "MIDI_ATTACH" && parts.size() == 3) {
            if (!midi_inputs.attach(parts[1], parts[2])) { error("not_found", "unable to attach midi input"); continue; }
            ok(std::string("device=") + parts[1] + " player=" + parts[2] + " attached=1");
            continue;
        }
        if (command == "MIDI_DETACH" && parts.size() == 2) {
            if (!midi_inputs.detach(parts[1])) { error("not_found", "unknown midi input"); continue; }
            ok(std::string("device=") + parts[1] + " attached=0");
            continue;
        }
        if (command == "MIDI_INPUT_POLL") {
            const auto snapshot = clock.snapshot();
            const auto show_time_ns = static_cast<std::uint64_t>(std::max(0.0, snapshot.show_seconds) * 1000000000.0);
            (void)midi_inputs.poll(show_time_ns);const auto routed=route_captured_midi();
            ok(std::string("captured=") + std::to_string(routed.first) + " mapped="+std::to_string(routed.second)+" queued=" + std::to_string(midi_observer_queue.size_approx()));
            continue;
        }
        if (command == "MIDI_INPUT_NEXT") {
            stageforge::CapturedMidiInput event{};
            if (!midi_observer_queue.try_pop(event)) { ok("available=0"); continue; }
            std::cout << "OK available=1"
                      << " device=" << token_safe(event.device_id.data())
                      << " player=" << token_safe(event.player_id.data())
                      << " showNs=" << event.message.show_time_ns
                      << " status=" << static_cast<unsigned int>(event.message.status)
                      << " data1=" << static_cast<unsigned int>(event.message.data1)
                      << " data2=" << static_cast<unsigned int>(event.message.data2) << '\n' << std::flush;
            continue;
        }
        if (command == "INGRESS_AUDIT_STATUS" && parts.size() == 2 && parts[1] == "MIDI") {
            const auto s=midi_inputs.audit_status();std::cout<<"OK domain=midi polls="<<s.polls<<" bytes="<<s.bytes<<" messages="<<s.messages<<" queueDrops="<<s.queue_drops<<" injectedMessages="<<s.injected_messages<<" topologyDetaches="<<s.topology_detaches<<" maxDurationNs="<<s.max_poll_duration_ns<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "INGRESS_AUDIT_STATUS" && parts.size() == 3 && parts[1] == "CAPTURE") {
            unsigned int slot=0;if(!parse_number(parts[2],slot)||slot>=kAudioInputSlots){error("argument","invalid capture audit slot");continue;}const auto s=audio_inputs[slot].audit.status();std::cout<<"OK domain=capture slot="<<slot<<" callbacks="<<s.callbacks<<" frames="<<s.frames<<" recordBlocks="<<s.record_blocks<<" queueRejections="<<s.queue_rejections<<" nonfiniteSamples="<<s.nonfinite_samples<<" maxDurationNs="<<s.max_duration_ns<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "INGRESS_AUDIT_STATUS" && parts.size() == 2 && parts[1] == "LIGHTING") {
            const auto s=lighting_ingress_audit.status();std::cout<<"OK domain=lighting accepted="<<s.accepted<<" queueRejections="<<s.queue_rejections<<" drained="<<s.drained<<" drainCalls="<<s.drain_calls<<" maxDurationNs="<<s.max_drain_duration_ns<<" physicalOutputsArmed=0\n"<<std::flush;
            continue;
        }
        if (command == "MIDI_INPUT_INJECT" && parts.size() == 7) {
            stageforge::MidiInputMessage message{};
            unsigned int status = 0, data1 = 0, data2 = 0;
            if (!parse_number(parts[3], message.show_time_ns) || !parse_number(parts[4], status) ||
                !parse_number(parts[5], data1) || !parse_number(parts[6], data2) ||
                status > 255 || data1 > 127 || data2 > 127) {
                error("argument", "invalid midi input event"); continue;
            }
            message.status = static_cast<std::uint8_t>(status);
            message.data1 = static_cast<std::uint8_t>(data1);
            message.data2 = static_cast<std::uint8_t>(data2);
            if (!midi_inputs.inject(parts[1], parts[2], message)) { error("busy", "midi input queue full"); continue; }
            const auto routed=route_captured_midi();ok(std::string("queued=") + std::to_string(midi_observer_queue.size_approx())+" mapped="+std::to_string(routed.second));
            continue;
        }
        if (command == "LIGHT_SCHEDULE" && parts.size() == 6) {
            stageforge::ShowEvent event{};
            unsigned int universe = 0, channel = 0, value = 0;
            if (!parse_number(parts[1], event.event_id) || !parse_number(parts[2], event.show_time_ns) ||
                !parse_number(parts[3], universe) || !parse_number(parts[4], channel) || !parse_number(parts[5], value) ||
                universe >= dmx_universes.size() || channel < 1 || channel > 512 || value > 255) {
                error("argument", "invalid lighting event"); continue;
            }
            event.type = stageforge::ShowEventType::lighting;
            event.priority = SF_PRIORITY_SHOW;
            event.revision = core.metrics().revision;
            event.payload.lighting = {static_cast<std::uint16_t>(universe), static_cast<std::uint16_t>(channel), static_cast<std::uint8_t>(value), {0,0,0}};
            if (!show_loop.submit(event)) { error("busy", "show event ingress full"); continue; }
            const auto metrics = show_loop.dispatch_metrics();
            ok(std::string("queued=") + std::to_string(metrics.pending));
            continue;
        }
        if (command == "LIGHT_DRAIN" && parts.size() == 2) {
            std::uint64_t now_ns = 0;
            if (!parse_number(parts[1], now_ns)) { error("argument", "invalid lighting drain time"); continue; }
            (void)show_loop.drain_until(now_ns);
            (void)ingest_lighting_domain();
            std::size_t count = 0;
            std::array<bool, 16> changed{};
            stageforge::LightingEvent event{};
            while (lighting.pop_due(now_ns, event)) {
                if (event.universe < dmx_universes.size()) {
                    dmx_universes[event.universe].set(event.channel, event.value);
                    changed[event.universe] = true;
                    ++count;
                }
            }
            std::size_t sent = 0;
            for (std::size_t universe = 0; universe < changed.size(); ++universe) {
                if (!changed[universe]) continue;
                if (lighting_network_protocol == LightingNetworkProtocol::sacn) {
                    auto& sequence = sacn_sequences[universe];
                    sequence = static_cast<std::uint8_t>(sequence + 1);
                    const auto network_universe = static_cast<std::uint16_t>(sacn_universe_base + universe);
                    const auto packet = stageforge::Sacn::encode_dmx(network_universe, dmx_universes[universe].values(), sequence, sacn_cid);
                    if (sacn_output.send(packet)) ++sent;
                } else {
                    auto& sequence = artnet_sequences[universe];
                    sequence = static_cast<std::uint8_t>(sequence == 255 ? 1 : sequence + 1);
                    const auto packet = stageforge::ArtNet::encode_dmx(static_cast<std::uint16_t>(universe), dmx_universes[universe].values(), sequence);
                    if (artnet_output.send(packet)) ++sent;
                }
            }
            ok(std::string("drained=") + std::to_string(count) + " queued=" + std::to_string(lighting.size()) + " sent=" + std::to_string(sent));
            continue;
        }
        if (command == "LIGHT_NET_CONFIG" && parts.size() >= 3 && parts.size() <= 5) {
            unsigned int port = 0;
            if (!parse_number(parts[2], port) || port == 0 || port > 65535) { error("argument", "invalid lighting network port"); continue; }
            const auto protocol = parts.size() >= 4 ? parts[3] : std::string("ARTNET");
            unsigned int universe_base = 1;
            if (parts.size() == 5 && (!parse_number(parts[4], universe_base) || universe_base < 1 || universe_base > 63984)) {
                error("argument", "invalid sACN universe base"); continue;
            }
            artnet_output.arm(false); sacn_output.arm(false);
            if (protocol == "SACN") {
                artnet_output.close();
                if (!sacn_output.configure(parts[1], static_cast<std::uint16_t>(port))) {
                    const std::string message = sacn_output.last_error().empty() ? "invalid sACN network configuration" : std::string(sacn_output.last_error());
                    error("argument", message); continue;
                }
                lighting_network_protocol = LightingNetworkProtocol::sacn;
                sacn_universe_base = static_cast<std::uint16_t>(universe_base);
            } else if (protocol == "ARTNET") {
                sacn_output.close();
                if (!artnet_output.configure(parts[1], static_cast<std::uint16_t>(port))) {
                    const std::string message = artnet_output.last_error().empty() ? "invalid Art-Net network configuration" : std::string(artnet_output.last_error());
                    error("argument", message); continue;
                }
                lighting_network_protocol = LightingNetworkProtocol::artnet;
            } else {
                error("argument", "lighting protocol must be ARTNET or SACN"); continue;
            }
            ok(std::string("target=") + parts[1] + " port=" + std::to_string(port) + " protocol=" + (lighting_network_protocol == LightingNetworkProtocol::sacn ? "sacn" : "artnet") + " universeBase=" + std::to_string(sacn_universe_base) + " armed=0");
        } else if (command == "LIGHT_NET_ARM" && parts.size() == 2) {
            int enabled = 0;
            if (!parse_number(parts[1], enabled) || (enabled != 0 && enabled != 1)) { error("argument", "invalid lighting arm state"); continue; }
            if (lighting_network_protocol == LightingNetworkProtocol::sacn) {
                if (enabled && !sacn_output.status().configured) { error("conflict", "configure sACN target before arming"); continue; }
                sacn_output.arm(enabled != 0); artnet_output.arm(false);
                ok(std::string("armed=") + (sacn_output.status().armed ? "1" : "0"));
            } else {
                if (enabled && !artnet_output.status().configured) { error("conflict", "configure Art-Net target before arming"); continue; }
                artnet_output.arm(enabled != 0); sacn_output.arm(false);
                ok(std::string("armed=") + (artnet_output.status().armed ? "1" : "0"));
            }
        } else if (command == "LIGHT_NET_STATUS") {
            const auto artnet = artnet_output.status();
            const auto sacn = sacn_output.status();
            const bool use_sacn = lighting_network_protocol == LightingNetworkProtocol::sacn;
            std::cout << "OK configured=" << ((use_sacn ? sacn.configured : artnet.configured) ? 1 : 0)
                      << " armed=" << ((use_sacn ? sacn.armed : artnet.armed) ? 1 : 0)
                      << " target=" << token_safe((use_sacn ? sacn.target : artnet.target).data())
                      << " port=" << (use_sacn ? sacn.port : artnet.port)
                      << " protocol=" << (use_sacn ? "sacn" : "artnet")
                      << " universeBase=" << sacn_universe_base
                      << " packets=" << (use_sacn ? sacn.packets_sent : artnet.packets_sent)
                      << " errors=" << (use_sacn ? sacn.send_errors : artnet.send_errors) << '\n' << std::flush;
        } else if (command == "LIGHT_ARTNET" && parts.size() == 2) {
            unsigned int universe = 0;
            if (!parse_number(parts[1], universe) || universe >= dmx_universes.size()) {
                error("argument", "invalid lighting universe"); continue;
            }
            const auto packet = stageforge::ArtNet::encode_dmx(
                static_cast<std::uint16_t>(universe), dmx_universes[universe].values());
            std::cout << "OK universe=" << universe
                      << " bytes=" << packet.size
                      << " opLow=" << static_cast<unsigned int>(packet.bytes[8])
                      << " opHigh=" << static_cast<unsigned int>(packet.bytes[9])
                      << " channel1=" << static_cast<unsigned int>(packet.bytes[18])
                      << '\n' << std::flush;
        } else if (command == "LIGHT_SACN" && parts.size() == 2) {
            unsigned int universe = 0;
            if (!parse_number(parts[1], universe) || universe >= dmx_universes.size()) {
                error("argument", "invalid lighting universe"); continue;
            }
            const auto network_universe = static_cast<std::uint16_t>(sacn_universe_base + universe);
            const auto packet = stageforge::Sacn::encode_dmx(
                network_universe, dmx_universes[universe].values(), 1, sacn_cid);
            std::cout << "OK universe=" << universe
                      << " networkUniverse=" << network_universe
                      << " bytes=" << packet.size
                      << " priority=" << static_cast<unsigned int>(packet.bytes[108])
                      << " channel1=" << static_cast<unsigned int>(packet.bytes[126])
                      << '\n' << std::flush;
        } else if (command == "NOTATION_QUANTIZE" && parts.size() == 3) {
            double beats = 0.0;
            if (!parse_number(parts[1], beats)) { error("argument", "invalid beat value"); continue; }
            stageforge::NotationGrid grid{};
            if (parts[2] == "1/4") grid = stageforge::NotationGrid::quarter;
            else if (parts[2] == "1/8") grid = stageforge::NotationGrid::eighth;
            else if (parts[2] == "1/16") grid = stageforge::NotationGrid::sixteenth;
            else if (parts[2] == "1/32") grid = stageforge::NotationGrid::thirty_second;
            else { error("argument", "invalid notation grid"); continue; }
            std::cout << "OK beats=" << std::fixed << std::setprecision(6)
                      << stageforge::NotationQuantizer::quantize_beats(beats, grid)
                      << " minimumDuration=" << stageforge::NotationQuantizer::minimum_duration_beats(grid)
                      << '\n' << std::flush;
        } else if (command == "TIMING_PLAN" && parts.size() == 7) {
            std::uint64_t now_ns = 0, target_ns = 0, fixed_ns = 0, jitter_ns = 0, lookahead_ns = 0;
            unsigned int timestamped = 0;
            if (!parse_number(parts[1], now_ns) || !parse_number(parts[2], target_ns) ||
                !parse_number(parts[3], fixed_ns) || !parse_number(parts[4], jitter_ns) ||
                !parse_number(parts[5], lookahead_ns) || !parse_number(parts[6], timestamped)) {
                error("argument", "invalid timing profile"); continue;
            }
            stageforge::EndpointTimingProfile profile{};
            profile.fixed_latency_ns = fixed_ns;
            profile.jitter_ns = jitter_ns;
            profile.minimum_lookahead_ns = lookahead_ns;
            profile.supports_timestamped_execution = timestamped != 0;
            const auto plan = stageforge::LatencyResolver::plan(now_ns, target_ns, profile);
            std::cout << "OK dispatchNs=" << plan.dispatch_time_ns
                      << " targetNs=" << plan.target_time_ns
                      << " reserveNs=" << plan.reserve_ns
                      << " late=" << (plan.late ? 1 : 0)
                      << " timestamped=" << (plan.timestamped ? 1 : 0) << '\n' << std::flush;
        } else if (command == "STATUS") {
            const auto audio_status = audio.status();
            std::uint64_t output_callbacks = 0, output_xruns = 0;
            std::size_t active_outputs = 0;
            for (std::size_t slot = 0; slot < kAudioOutputSlots; ++slot) {
                const auto output_status = alsa_outputs[slot].status();
                output_callbacks += output_status.callback_count; output_xruns += output_status.xruns;
                if (execution_audio_backends[slot] == "alsa" || execution_audio_backends[slot] == "wasapi" ||
                    execution_audio_backends[slot] == "coreaudio" || (slot == 0 && execution_audio_backends[slot] == "null-audio")) ++active_outputs;
            }
            std::uint64_t input_callbacks = 0, input_xruns = 0, input_queued = 0;
            std::size_t active_inputs = 0;
            for (std::size_t slot = 0; slot < kAudioInputSlots; ++slot) {
                const auto input_status = alsa_inputs[slot].status();
                input_callbacks += input_status.callback_count; input_xruns += input_status.xruns;
                for (std::size_t reader = 0; reader < kAudioOutputSlots; ++reader) input_queued += audio_inputs[slot].ring.queued(reader);
                if (execution_audio_input_backends[slot] != "none") ++active_inputs;
            }
            const auto artnet_status = artnet_output.status();
            const auto sacn_status = sacn_output.status();
            const bool use_sacn = lighting_network_protocol == LightingNetworkProtocol::sacn;
            const auto transport_status = clock.snapshot();
            const auto clock_status = clock_discipline.snapshot(transport_status.monotonic_ns);
            const auto core_metrics = core.metrics();
            std::cout << "OK engineVersion=" << kEngineVersion
                      << " coreRevision=" << core_metrics.revision
                      << " coreExternalRevision=" << core_metrics.external_revision
                      << " coreSnapshotCommits=" << core_metrics.snapshot_commits
                      << " showEventPending=" << show_loop.dispatch_metrics().pending
                      << " showEventDispatched=" << show_loop.dispatch_metrics().dispatched
                      << " showLoopRunning=" << (show_loop.loop_metrics().running ? 1 : 0)
                      << " audioState=" << static_cast<int>(active_outputs ? stageforge::AudioDeviceState::running : audio_status.state)
                      << " audioBackend=" << (active_outputs > 1 ? "multi" : execution_audio_backends[0])
                      << " audioOutputActive=" << active_outputs
                      << " audioCallbacks=" << output_callbacks
                      << " audioXruns=" << output_xruns
                      << " audioInputBackend=" << (active_inputs > 1 ? "multi" : execution_audio_input_backends[0])
                      << " audioInputActive=" << active_inputs
                      << " audioInputCallbacks=" << input_callbacks
                      << " audioInputXruns=" << input_xruns
                      << " audioInputQueued=" << input_queued
                      << " clockSource=" << token_safe(clock_source)
                      << " clockState=" << clock_state_name(clock_status.state)
                      << " clockOffsetNs=" << clock_status.offset_ns
                      << " sampleRate=" << audio_status.config.sample_rate
                      << " monitorBuses=" << monitors.size()
                      << " midiQueued=" << (midi.size() + midi_event_ingress.size_approx())
                      << " midiDevices=" << midi_inputs.device_count()
                      << " midiAttached=" << midi_inputs.attached_count()
                      << " midiInputQueued=" << midi_inputs.queued()
                      << " lightingIngress=" << lighting_event_ingress.size_approx()
                      << " currentCueId=" << cue_state.snapshot().current_cue_id
                      << " automationParameters=" << automation_state.metrics().registered
                      << " automationRevision=" << automation_state.metrics().revision
                      << " lightingNetworkArmed=" << ((use_sacn ? sacn_status.armed : artnet_status.armed) ? 1 : 0)
                      << " lightingProtocol=" << (use_sacn ? "sacn" : "artnet")
                      << " lightingPackets=" << (use_sacn ? sacn_status.packets_sent : artnet_status.packets_sent)
                      << " ipcAuthenticated=" << (ipc_authenticated ? 1 : 0)
                      << " notationQuantizer=1" << '\n' << std::flush;
        } else if (command == "QUIT") {
            show_loop.stop();
            ok("bye=1");
            break;
        } else {
            error("unsupported", "unsupported command");
        }
    }

    artnet_output.close();
    sacn_output.close();
#if defined(_WIN32) || defined(__APPLE__)
    for (auto& owner : native_inputs) owner.reset();
    for (auto& owner : native_outputs) owner.reset();
#endif
    for (auto& input : alsa_inputs) input.close();
    for (auto& output : alsa_outputs) output.close();
    audio.stop();
    audio.close();
    return 0;
}
