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
#include "stageforge/shadow_render_executor.hpp"
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
#include "stageforge/lighting_scheduler.hpp"
#include "stageforge/clock_discipline.hpp"
#include "stageforge/core_state.hpp"
#include "stageforge/latency_resolver.hpp"
#include "stageforge/midi_scheduler.hpp"
#include "stageforge/midi_input.hpp"
#include "stageforge/monitor_mixer.hpp"
#include "stageforge/monitor_bus.hpp"
#include "stageforge/monitor_graph_router.hpp"
#include "stageforge/notation_quantizer.hpp"
#include "stageforge/resource_planner.hpp"
#include "stageforge/spsc_queue.hpp"
#include "stageforge/show_event_dispatcher.hpp"
#include "stageforge/show_execution_loop.hpp"
#include "stageforge/cue_state.hpp"
#include "stageforge/transport_clock.hpp"
#include "stageforge/transport_discipline.hpp"
#include "stageforge/midi_clock.hpp"
#include "stageforge/daw_stream_renderer.hpp"
#include "stageforge/daw_playback_queue.hpp"
#include "stageforge/daw_recording_queue.hpp"
#include "stageforge/plugin_delay_compensation.hpp"
#include "stageforge/plugin_delay_graph.hpp"
#include "stageforge/realtime_audit.hpp"
#include "stageforge/realtime_qualification.hpp"
#include "stageforge/capture_ingress_audit.hpp"
#include "stageforge/capture_ingress.hpp"
#include "stageforge/lighting_ingress_audit.hpp"
#include "stageforge/midi_learn_router.hpp"
#include "stageforge/midi_mapped_action_dispatcher.hpp"
#include "stageforge/sampler_voice_engine.hpp"
#include "stageforge/streaming_voice_engine.hpp"

#include <cstdio>
#include <cstdlib>
#include <atomic>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <thread>
#include <mutex>

#if defined(__unix__) || defined(__APPLE__)
#include <sys/socket.h>
#include <unistd.h>
#endif


#define SF_CHECK(expr) do { \
    if (!(expr)) { \
        std::fprintf(stderr, "CHECK failed: %s (%s:%d)\n", #expr, __FILE__, __LINE__); \
        std::abort(); \
    } \
} while (false)

namespace {

struct DawTestIo {std::uint64_t reads{0},writes{0},frames{0};float maximum{0};};
bool daw_test_read(void* raw,std::uint64_t,float* left,float* right,std::uint32_t frames) noexcept {auto& io=*static_cast<DawTestIo*>(raw);++io.reads;for(std::uint32_t i=0;i<frames;++i)left[i]=right[i]=2.0F;return true;}
bool daw_test_write(void* raw,const float* left,const float* right,std::uint32_t frames) noexcept {auto& io=*static_cast<DawTestIo*>(raw);++io.writes;io.frames+=frames;for(std::uint32_t i=0;i<frames;++i)io.maximum=std::max(io.maximum,std::max(std::abs(left[i]),std::abs(right[i])));return true;}
void test_daw_stream_renderer_bounded_long_render_and_cancel(){DawTestIo io{};stageforge::DawStreamRenderer<8,64> renderer;SF_CHECK(renderer.configure(0,1'000,-1));stageforge::DawRenderRegion region{};region.clip_id=1;region.length_frames=1'000;region.fade_in_frames=10;region.fade_out_frames=10;region.read=&daw_test_read;region.source_context=&io;SF_CHECK(renderer.add_region(region));SF_CHECK(renderer.render(&daw_test_write,&io));const auto status=renderer.status();SF_CHECK(status.complete&&status.rendered_frames==1'000&&status.rendered_blocks==16&&io.frames==1'000);SF_CHECK(io.maximum<=std::pow(10.0F,-1.0F/20.0F)+0.0001F);stageforge::DawStreamRenderer<2,32> cancelled;SF_CHECK(cancelled.configure(0,100));SF_CHECK(cancelled.add_region(region));cancelled.cancel();SF_CHECK(!cancelled.render(&daw_test_write,&io));SF_CHECK(cancelled.status().cancelled&&!cancelled.status().physical_outputs_armed);}
void test_daw_playback_prefetch_seek_loop_and_underrun(){stageforge::DawPlaybackQueue<8,4> queue;stageforge::DawPlaybackQueue<8,4>::Block block{};block.generation=1;block.start_frame=0;block.frames=8;block.left.fill(.25F);block.right.fill(-.25F);SF_CHECK(queue.push(block));SF_CHECK(queue.set_loop(0,8));queue.start();float left[8]{},right[8]{};queue.render(left,right,8);SF_CHECK(left[0]==.25F&&queue.status().loop_wraps==1);queue.render(left,right,8);SF_CHECK(queue.status().underrun_blocks==1);queue.seek(16);SF_CHECK(queue.status().generation==2&&queue.status().seeks==1&&!queue.status().physical_outputs_armed);}
void test_daw_playback_arbitrary_short_loop_wraps_multiple_times_per_block(){stageforge::DawPlaybackQueue<8,4> queue;stageforge::DawPlaybackQueue<8,4>::Block first{};first.generation=1;first.start_frame=0;first.frames=8;first.left.fill(.5F);first.right.fill(-.5F);stageforge::DawPlaybackQueue<8,4>::Block second=first;second.start_frame=2;SF_CHECK(queue.push(first));SF_CHECK(queue.push(second));SF_CHECK(queue.set_loop(0,3));queue.start();float left[8]{},right[8]{};queue.render(left,right,8);auto status=queue.status();SF_CHECK(status.playhead_frame==2&&status.loop_wraps==2&&status.discontinuities==0);queue.render(left,right,8);status=queue.status();SF_CHECK(status.playhead_frame==1&&status.loop_wraps==5&&status.rendered_frames==16&&status.discontinuities==0);}
void test_daw_multitrack_recording_queue_fences_arm_and_tracks_gaps(){stageforge::DawRecordingQueue<2,4,2> queue;stageforge::DawRecordingQueue<2,4,2>::Block block{};block.sequence=1;block.frames=4;SF_CHECK(!queue.submit(0,block));SF_CHECK(!queue.arm(0,false));SF_CHECK(queue.arm(0,true));block.generation=queue.generation(0);SF_CHECK(queue.submit(0,block));block.sequence=3;SF_CHECK(queue.submit(0,block));block.sequence=4;SF_CHECK(!queue.submit(0,block));stageforge::DawRecordingQueue<2,4,2>::Block out{};SF_CHECK(queue.pop(0,out));SF_CHECK(queue.pop(0,out));const auto status=queue.status(0);SF_CHECK(status.written==2&&status.dropped==1&&status.stale==1&&status.sequence_gaps==1&&status.armed);queue.disarm(0);SF_CHECK(!queue.status(0).armed);SF_CHECK(queue.arm(0,true));block.generation-=1;SF_CHECK(!queue.submit(0,block));SF_CHECK(queue.status(0).stale==2);}
void test_plugin_delay_compensation_aligns_parallel_paths(){stageforge::PluginDelayCompensator<2,8> delay;const std::uint32_t latencies[]{0,3};SF_CHECK(delay.configure(latencies,2));SF_CHECK(delay.delay_for(0)==3&&delay.delay_for(1)==0);float left[]{1,0,0,0},right[]{-1,0,0,0};SF_CHECK(delay.process(0,left,right,4));SF_CHECK(left[0]==0&&left[1]==0&&left[2]==0&&left[3]==1);SF_CHECK(right[3]==-1);float wet[]{.5F,0,0,0};SF_CHECK(delay.process(1,wet,wet,4));SF_CHECK(wet[0]==.5F);const auto status=delay.status();SF_CHECK(status.configured&&status.maximum_latency_frames==3&&status.processed_frames==8&&!status.physical_outputs_armed);}
void test_plugin_delay_graph_swaps_complete_generations(){stageforge::PluginDelayGraph<3,16> graph;const std::uint32_t first[]{0,2,5};SF_CHECK(graph.prepare(1,first,3,100));SF_CHECK(!graph.activate(99));SF_CHECK(graph.activate(100));float left[]{1,0},right[]{-1,0};SF_CHECK(graph.process(0,left,right,2));auto status=graph.status();SF_CHECK(status.active_generation==1&&status.paths==3&&status.maximum_latency_frames==5&&status.swaps==1&&status.processed_frames==2);const std::uint32_t second[]{7,1,4};SF_CHECK(graph.prepare(2,second,3,200));SF_CHECK(graph.status().active_generation==1);SF_CHECK(graph.activate(200));SF_CHECK(graph.status().active_generation==2&&!graph.status().physical_outputs_armed);SF_CHECK(!graph.prepare(2,second,3,300));}

void test_realtime_audit_sheds_and_recovers_optional_work(){stageforge::RealtimeAudit audit;for(int i=0;i<3;++i)audit.finish(101,100);SF_CHECK(!audit.allow_optional()&&audit.status().overload_level==1);audit.note_optional_shed();audit.note_nonfinite(2);audit.note_queue_pressure();for(int i=0;i<128;++i)audit.finish(50,100);const auto s=audit.status();SF_CHECK(audit.allow_optional()&&s.deadline_misses==3&&s.optional_shed_blocks==1&&s.nonfinite_samples==2&&s.queue_pressure_events==1&&s.recovery_transitions==1&&!s.physical_outputs_armed);}
void test_realtime_qualification_detects_allocation_and_lock_attempts(){
stageforge::RealtimeAudit audit;
{
stageforge::RealtimeQualificationScope scope(&audit);
auto* values=new int[16];
volatile int* observed_values=values;
observed_values[0]=7;
std::mutex mutex;
mutex.lock();
mutex.unlock();
delete[] values;
}
const auto status=audit.status();
#ifdef STAGEFORGE_RT_QUALIFICATION
SF_CHECK(status.qualification_enabled&&status.allocation_attempts>=1&&status.allocated_bytes>=sizeof(int)*16&&status.lock_attempts>=1);
#else
SF_CHECK(!status.qualification_enabled&&status.allocation_attempts==0&&status.lock_attempts==0);
#endif
SF_CHECK(!status.physical_outputs_armed);
}
void test_midi_learn_router_quantizes_maps_and_key_syncs(){stageforge::MidiLearnRouter<4,4> router;router.configure_master(120,0,0x0AB5);stageforge::MidiLearnBinding binding{};binding.mapping_id=1;binding.device_id=10;binding.target_id=20;binding.parameter_id=3;binding.channel=0;binding.number=61;binding.message=stageforge::MidiLearnMessage::note;binding.behavior=stageforge::MidiMapBehavior::trigger;binding.steps_per_beat=1;binding.key_sync=true;SF_CHECK(router.upsert(binding));router.process(10,0x90,61,100,260'000'000);stageforge::MidiMappedAction action{};SF_CHECK(router.pop(action));SF_CHECK(action.show_time_ns==500'000'000&&action.value==1&&action.input_note==61&&action.output_note==60&&action.key_synced&&!action.physical_outputs_armed);binding.mapping_id=2;binding.message=stageforge::MidiLearnMessage::control_change;binding.number=74;binding.behavior=stageforge::MidiMapBehavior::absolute;binding.minimum=20;binding.maximum=20'000;SF_CHECK(router.upsert(binding));router.process(10,0xB0,74,127,500'000'000);SF_CHECK(router.pop(action)&&action.value==20'000);SF_CHECK(router.status().matched==2&&router.status().bindings==2);}

struct MidiMappedSink {std::array<stageforge::ShowEvent,8>events{};std::size_t count{0};};
bool capture_mapped_event(void* raw,const stageforge::ShowEvent&event)noexcept{auto&sink=*static_cast<MidiMappedSink*>(raw);if(sink.count>=sink.events.size())return false;sink.events[sink.count++]=event;return true;}
void test_midi_mapped_actions_become_authoritative_show_events(){
    MidiMappedSink sink{};stageforge::MidiMappedActionDispatcher dispatcher(&capture_mapped_event,&sink,99);
    stageforge::MidiMappedAction action{};action.mapping_id=7;action.target_id=44;action.parameter_id=3;action.show_time_ns=500;action.value=.75F;
    SF_CHECK(dispatcher.dispatch(action,12));SF_CHECK(sink.count==1);const auto automation=sink.events[0];
    SF_CHECK(automation.type==stageforge::ShowEventType::automation&&automation.owner_id==99&&automation.revision==12&&automation.show_time_ns==500);
    SF_CHECK(automation.payload.automation.target_id==44&&automation.payload.automation.parameter_id==3&&automation.payload.automation.value==.75F);
    SF_CHECK((automation.flags&stageforge::show_event_authoritative)!=0&&!dispatcher.status().physical_outputs_armed);
    action.action=stageforge::MidiMappedActionKind::transport_play;action.value=1;SF_CHECK(dispatcher.dispatch(action,13));
    SF_CHECK(sink.events[1].type==stageforge::ShowEventType::transport&&sink.events[1].priority==SF_PRIORITY_CRITICAL&&sink.events[1].payload.transport.action==SF_CORE_TRANSPORT_PLAY);
    action.action=stageforge::MidiMappedActionKind::transport_tempo;action.value=128;SF_CHECK(dispatcher.dispatch(action,14));
    SF_CHECK(sink.events[2].payload.transport.action==SF_CORE_TRANSPORT_SET_BPM&&sink.events[2].payload.transport.value==128);
    action.action=stageforge::MidiMappedActionKind::sample_trigger;action.resource_id=88;action.value=.8F;action.input_note=63;action.output_note=60;action.key_synced=true;SF_CHECK(dispatcher.dispatch(action,15));
    SF_CHECK(sink.events[3].type==stageforge::ShowEventType::sampler&&sink.events[3].payload.sampler.sample_id==88&&sink.events[3].payload.sampler.note==60&&sink.events[3].payload.sampler.action==stageforge::ShowSamplerAction::trigger);
    action.action=stageforge::MidiMappedActionKind::automation;action.parameter_id=0;SF_CHECK(!dispatcher.dispatch(action,15));
    SF_CHECK(dispatcher.status().submitted==4&&dispatcher.status().ignored==1&&dispatcher.status().rejected==0);
}

void test_sampler_voice_engine_polyphony_steal_choke_and_loop(){
    std::array<float,128> a_left{},a_right{},b_left{},b_right{};a_left.fill(1.0F);a_right.fill(-1.0F);b_left.fill(.5F);b_right.fill(.25F);
    stageforge::SamplerVoiceEngine<2,2,9> sampler;
    SF_CHECK(sampler.register_sample({1,a_left.data(),a_right.data(),128,0,0,0,1,false}));
    SF_CHECK(sampler.register_sample({2,b_left.data(),b_right.data(),128,16,96,16,1,true}));
    SF_CHECK(sampler.submit({stageforge::SamplerCommandKind::trigger,1,1,1.0F,60}));
    SF_CHECK(sampler.submit({stageforge::SamplerCommandKind::trigger,2,1,.5F,61}));
    float left[32]{},right[32]{};sampler.render(left,right,32);SF_CHECK(left[0]>0&&left[0]<.1F);SF_CHECK(sampler.status().active_voices==2);
    SF_CHECK(sampler.submit({stageforge::SamplerCommandKind::trigger,3,2,1.0F,62}));sampler.render(left,right,1);
    const auto saturated=sampler.status();
    SF_CHECK(saturated.stolen_voices==1&&saturated.choked_voices>=2&&saturated.pending_voices==1);
    sampler.render(left,right,31);sampler.render(left,right,32);sampler.render(left,right,32);SF_CHECK(sampler.status().active_voices>=1);
    SF_CHECK(sampler.submit({stageforge::SamplerCommandKind::stop_all,4,0,0,0}));sampler.render(left,right,32);sampler.render(left,right,32);
    SF_CHECK(sampler.status().active_voices==0&&!sampler.status().physical_outputs_armed);
    for(float value:left)SF_CHECK(std::isfinite(value));
}

struct TestEvent {
    std::uint64_t id;
    float value;
};


void test_clock_discipline_holdover() {
    stageforge::ClockDiscipline discipline(1'000);
    auto free = discipline.snapshot(1'000'000);
    SF_CHECK(free.state == stageforge::ClockDisciplineState::free_running);
    SF_CHECK(free.projected_time_ns == 1'000'000);

    discipline.observe(1'000'000, 1'005'000);
    auto locked = discipline.snapshot(1'000'000);
    SF_CHECK(locked.state == stageforge::ClockDisciplineState::locked);
    SF_CHECK(locked.offset_ns == 5'000);
    SF_CHECK(locked.projected_time_ns == 1'005'000);

    discipline.observe(2'000'000, 2'005'100);
    locked = discipline.snapshot(2'000'000);
    SF_CHECK(locked.state == stageforge::ClockDisciplineState::locked);
    SF_CHECK(locked.observations == 2);
    SF_CHECK(locked.drift_ppm > 0.0);

    auto holdover = discipline.snapshot(2'002'000);
    SF_CHECK(holdover.state == stageforge::ClockDisciplineState::holdover);
    SF_CHECK(holdover.projected_time_ns > locked.projected_time_ns);
}
void test_transport() {
    stageforge::TransportClock clock(48000.0, 120.0);
    SF_CHECK(!clock.running());
    clock.play();
    std::this_thread::sleep_for(std::chrono::milliseconds(3));
    auto running = clock.snapshot();
    SF_CHECK(running.show_seconds > 0.0);
    SF_CHECK(running.sample_position > 0);
    clock.pause();
    auto paused = clock.snapshot();
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
    auto paused_later = clock.snapshot();
    SF_CHECK(paused_later.show_seconds == paused.show_seconds);
    clock.seek_seconds(12.5);
    SF_CHECK(clock.snapshot().show_seconds == 12.5);
    clock.stop();
    SF_CHECK(clock.snapshot().show_seconds == 0.0);
}

void test_spsc_queue() {
    stageforge::SpscQueue<TestEvent, 4> queue;
    SF_CHECK(queue.usable_capacity() == 3);
    SF_CHECK(queue.try_push({1, 1.0F}));
    SF_CHECK(queue.try_push({2, 2.0F}));
    SF_CHECK(queue.try_push({3, 3.0F}));
    SF_CHECK(!queue.try_push({4, 4.0F}));
    TestEvent event{};
    SF_CHECK(queue.try_pop(event));
    SF_CHECK(event.id == 1);
    SF_CHECK(queue.try_push({4, 4.0F}));
    SF_CHECK(queue.try_pop(event) && event.id == 2);
    SF_CHECK(queue.try_pop(event) && event.id == 3);
    SF_CHECK(queue.try_pop(event) && event.id == 4);
    SF_CHECK(!queue.try_pop(event));
}

void test_monitor_bus_isolation() {
    stageforge::MonitorBusRegistry registry;
    auto& alex = registry.get_or_create("alex");
    auto& sam = registry.get_or_create("sam");
    alex.set_master(91.0F);
    alex.set_level(stageforge::MonitorChannel::click, 14.0F);
    sam.set_master(63.0F);
    SF_CHECK(alex.master() == 91.0F);
    SF_CHECK(alex.level(stageforge::MonitorChannel::click) == 14.0F);
    SF_CHECK(sam.master() == 63.0F);
    SF_CHECK(sam.level(stageforge::MonitorChannel::click) == 38.0F);
    SF_CHECK(registry.size() == 2);
}


void test_midi_byte_parser() {
    stageforge::MidiByteParser parser;
    stageforge::MidiInputMessage event{};
    SF_CHECK(!parser.feed(0x90, 100, event));
    SF_CHECK(!parser.feed(60, 100, event));
    SF_CHECK(parser.feed(100, 100, event));
    SF_CHECK(event.status == 0x90 && event.data1 == 60 && event.data2 == 100);

    // Running status: second note omits the 0x90 status byte.
    SF_CHECK(!parser.feed(64, 200, event));
    SF_CHECK(parser.feed(90, 200, event));
    SF_CHECK(event.status == 0x90 && event.data1 == 64 && event.data2 == 90);

    // Realtime clock does not disturb an in-progress channel message.
    SF_CHECK(!parser.feed(67, 300, event));
    SF_CHECK(!parser.feed(0xF8, 300, event));
    SF_CHECK(parser.feed(80, 300, event));
    SF_CHECK(event.data1 == 67 && event.data2 == 80);

    // Program change has one data byte and still supports running status.
    SF_CHECK(!parser.feed(0xC1, 400, event));
    SF_CHECK(parser.feed(12, 400, event));
    SF_CHECK(event.status == 0xC1 && event.data1 == 12 && event.data2 == 0);
    SF_CHECK(parser.feed(13, 500, event));
    SF_CHECK(event.status == 0xC1 && event.data1 == 13);

    // SysEx payload is ignored and resets running status.
    SF_CHECK(!parser.feed(0xF0, 600, event));
    SF_CHECK(!parser.feed(0x01, 600, event));
    SF_CHECK(!parser.feed(0xF7, 600, event));
    SF_CHECK(!parser.feed(60, 700, event));
}

void test_midi_input_queue_injection() {
    stageforge::MidiInputManager manager;
    stageforge::MidiInputMessage message{123456, 0x90, 60, 100};
    SF_CHECK(manager.inject("virtual-test", "alex", message));
    SF_CHECK(manager.queued() == 1);
    stageforge::CapturedMidiInput captured{};
    SF_CHECK(manager.pop(captured));
    SF_CHECK(std::string_view(captured.device_id.data()) == "virtual-test");
    SF_CHECK(std::string_view(captured.player_id.data()) == "alex");
    SF_CHECK(captured.message.show_time_ns == 123456);
    SF_CHECK(captured.message.status == 0x90);
    SF_CHECK(manager.queued() == 0);
    const auto audit=manager.audit_status();
    SF_CHECK(audit.messages==1&&audit.injected_messages==1&&audit.queue_drops==0&&!audit.physical_outputs_armed);
    stageforge::MidiInputManager full;
    for(std::size_t i=0;i<2048;++i)SF_CHECK(full.inject("virtual-test","alex",message));
    SF_CHECK(!full.inject("virtual-test","alex",message));
    const auto full_audit=full.audit_status();
    SF_CHECK(full_audit.messages==2048&&full_audit.queue_drops==1);
}
void test_midi_scheduler() {
    stageforge::MidiScheduler<4> scheduler;
    SF_CHECK(scheduler.schedule({3, 300, 0x90, 64, 100}));
    SF_CHECK(scheduler.schedule({1, 100, 0x90, 60, 100}));
    SF_CHECK(scheduler.schedule({2, 100, 0x80, 60, 0}));
    SF_CHECK(scheduler.schedule({4, 400, 0x90, 67, 100}));
    SF_CHECK(!scheduler.schedule({5, 500, 0x90, 70, 100}));
    stageforge::MidiEvent event{};
    SF_CHECK(!scheduler.pop_due(99, event));
    SF_CHECK(scheduler.pop_due(100, event) && event.event_id == 1);
    SF_CHECK(scheduler.pop_due(100, event) && event.event_id == 2);
    SF_CHECK(!scheduler.pop_due(299, event));
    SF_CHECK(scheduler.pop_due(300, event) && event.event_id == 3);
}


void test_monitor_mixer() {
    stageforge::MonitorBus bus;
    bus.set_master(50.0F);
    bus.set_level(stageforge::MonitorChannel::self, 100.0F);
    bus.set_level(stageforge::MonitorChannel::click, 50.0F);
    const float self_samples[3]{1.0F, 0.5F, -1.0F};
    const float click_samples[3]{0.4F, 0.4F, 0.4F};
    const stageforge::MonitorSourceBlock sources[]{
        {stageforge::MonitorChannel::self, self_samples},
        {stageforge::MonitorChannel::click, click_samples},
    };
    float left[3]{};
    float right[3]{};
    stageforge::MonitorMixer::mix(bus, sources, left, right, 3);
    SF_CHECK(left[0] > 0.59F && left[0] < 0.61F);
    SF_CHECK(left[1] > 0.34F && left[1] < 0.36F);
    SF_CHECK(left[2] > -0.41F && left[2] < -0.39F);
    SF_CHECK(left[0] == right[0]);
    bus.set_muted(true);
    stageforge::MonitorMixer::mix(bus, sources, left, right, 3);
    SF_CHECK(left[0] == 0.0F && right[2] == 0.0F);
}

void test_latency_resolver() {
    stageforge::EndpointTimingProfile profile{};
    profile.fixed_latency_ns = 5'000'000;
    profile.jitter_ns = 2'000'000;
    profile.minimum_lookahead_ns = 6'000'000;
    profile.jitter_margin_multiplier = 2;
    const auto plan = stageforge::LatencyResolver::plan(80'000'000, 100'000'000, profile);
    SF_CHECK(plan.reserve_ns == 9'000'000);
    SF_CHECK(plan.dispatch_time_ns == 91'000'000);
    SF_CHECK(!plan.late);
    const auto late = stageforge::LatencyResolver::plan(95'000'000, 100'000'000, profile);
    SF_CHECK(late.late);
}


void test_notation_quantizer() {
    using stageforge::NotationGrid;
    using stageforge::NotationQuantizer;
    SF_CHECK(NotationQuantizer::quantize_beats(1.12, NotationGrid::sixteenth) == 1.0);
    SF_CHECK(NotationQuantizer::quantize_beats(1.14, NotationGrid::eighth) == 1.0);
    SF_CHECK(NotationQuantizer::quantize_beats(1.27, NotationGrid::eighth) == 1.5);
    SF_CHECK(NotationQuantizer::quantize_beats(1.125, NotationGrid::sixteenth) == 1.25);
    SF_CHECK(NotationQuantizer::minimum_duration_beats(NotationGrid::thirty_second) == 0.125);
}



void test_lighting_scheduler_and_artnet() {
    stageforge::LightingScheduler<4> scheduler;
    SF_CHECK(scheduler.schedule({2, 200, 0, 1, 128}));
    SF_CHECK(scheduler.schedule({1, 100, 0, 1, 64}));
    stageforge::LightingEvent event{};
    SF_CHECK(!scheduler.pop_due(99, event));
    SF_CHECK(scheduler.pop_due(100, event));
    SF_CHECK(event.event_id == 1 && event.value == 64);
    stageforge::DmxUniverseState universe;
    universe.set(event.channel, event.value);
    SF_CHECK(universe.get(1) == 64);
    const auto packet = stageforge::ArtNet::encode_dmx(0, universe.values(), 7);
    SF_CHECK(packet.size == 530);
    SF_CHECK(packet.bytes[0] == 'A' && packet.bytes[7] == 0);
    SF_CHECK(packet.bytes[8] == 0x00 && packet.bytes[9] == 0x50);
    SF_CHECK(packet.bytes[12] == 7);
    SF_CHECK(packet.bytes[16] == 0x02 && packet.bytes[17] == 0x00);
    SF_CHECK(packet.bytes[18] == 64);
}

void test_sacn_packet_and_explicit_arm() {
    stageforge::DmxUniverseState universe;
    universe.set(1, 91);
    universe.set(512, 207);
    std::array<std::uint8_t,16> cid{};
    for (std::size_t index=0; index<cid.size(); ++index) cid[index]=static_cast<std::uint8_t>(index+1);
    const auto packet=stageforge::Sacn::encode_dmx(101,universe.values(),9,cid,"StageForge Test",120);
    SF_CHECK(packet.size==638);
    SF_CHECK(packet.bytes[0]==0x00&&packet.bytes[1]==0x10);
    SF_CHECK(packet.bytes[4]=='A'&&packet.bytes[15]==0);
    SF_CHECK(packet.bytes[108]==120&&packet.bytes[111]==9);
    SF_CHECK(packet.bytes[113]==0&&packet.bytes[114]==101);
    SF_CHECK(packet.bytes[123]==0x02&&packet.bytes[124]==0x01);
    SF_CHECK(packet.bytes[125]==0&&packet.bytes[126]==91&&packet.bytes[637]==207);
    stageforge::SacnUdpOutput output;
    SF_CHECK(output.configure("127.0.0.1",5568));
    SF_CHECK(!output.send(packet));
    output.arm(true);
    SF_CHECK(output.send(packet));
    const auto status=output.status();
    SF_CHECK(status.configured&&status.armed&&status.packets_sent==1);
    output.arm(false);
    SF_CHECK(!output.send(packet));
    output.close();
}

void test_audio_device_discovery() {
    stageforge::AudioDeviceManager manager;
    const auto count = manager.scan();
    SF_CHECK(count >= 1);
    const auto* null_device = manager.find("null-audio");
    SF_CHECK(null_device != nullptr);
    SF_CHECK(null_device->output);
    SF_CHECK(null_device->connected);
}

void test_audio_graph_routing_and_limiter() {
    stageforge::AudioGraph graph;
    graph.set_route_gain(0, 0, 1.0F);
    graph.set_route_gain(1, 0, 0.5F);
    graph.set_output_master(0, 1.0F);
    graph.set_limiter_ceiling_db(0, -6.0F);

    const float a_left[4]{0.2F, 0.8F, -0.2F, 0.1F};
    const float a_right[4]{0.2F, 0.8F, -0.2F, 0.1F};
    const float b_mono[4]{0.2F, 0.2F, 0.2F, 0.2F};
    const stageforge::AudioSourceBlock sources[]{
        {0, a_left, a_right},
        {1, b_mono, nullptr},
    };
    float left[4]{};
    float right[4]{};
    stageforge::AudioOutputBlock outputs[]{{0, left, right}};
    graph.process(sources, outputs, 4);

    // First frame is below the -6 dBFS ceiling; second triggers protection.
    SF_CHECK(left[0] > 0.29F && left[0] < 0.31F);
    SF_CHECK(left[1] <= 0.502F && right[1] <= 0.502F);
    SF_CHECK(left[0] == right[0]);
    const auto meter = graph.meter(0);
    SF_CHECK(meter.peak > 0.89F);
    SF_CHECK(meter.gain_reduction_db < -4.0F);
}

void test_transport_clock_rate_discipline() {
    stageforge::TransportClock clock(48000.0, 120.0);
    clock.play();
    clock.set_clock_rate(1.0005);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    const auto fast = clock.snapshot();
    SF_CHECK(fast.show_seconds > 0.009);
    clock.set_clock_rate(1.0);
    const auto before = clock.snapshot().show_seconds;
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
    const auto after = clock.snapshot().show_seconds;
    SF_CHECK(after >= before);
    clock.pause();
}

struct ClockPulseSink {std::uint64_t first{0},last{0};std::uint32_t count{0};};
bool clock_pulse(void*raw,std::uint64_t,std::uint64_t show_ns)noexcept{auto&sink=*static_cast<ClockPulseSink*>(raw);if(!sink.count)sink.first=show_ns;sink.last=show_ns;++sink.count;return true;}
void test_authority_fenced_transport_discipline_and_midi_clock(){
 stageforge::TransportDiscipline discipline;SF_CHECK(discipline.configure(7,3,1'000,500,5'000'000'000ULL));
 SF_CHECK(discipline.observe(1,3,1'000'000,1'000'000,100'000'000,101'000'000));auto status=discipline.status(1'000'000);SF_CHECK(status.state==stageforge::ClockDisciplineState::locked&&status.phase_error_ns==1'000'000&&status.applied_rate>1.0&&status.applied_rate<=1.0005);
 SF_CHECK(!discipline.observe(1,3,2'000'000,2'000'000,101'000'000,102'000'000));status=discipline.status(2'002'000);SF_CHECK(status.state==stageforge::ClockDisciplineState::holdover&&status.holdover_entries==1&&status.applied_rate<=1.0005);
 stageforge::MidiClock24Ppqn midi_clock;SF_CHECK(midi_clock.configure(3,120,0));SF_CHECK(midi_clock.start(3,0));ClockPulseSink sink{};SF_CHECK(midi_clock.emit_until(100'000'000,&clock_pulse,&sink)==5);SF_CHECK(sink.first==0&&sink.last==83'333'333);
 SF_CHECK(midi_clock.set_tempo(3,60,125'000'000));SF_CHECK(midi_clock.emit_until(250'000'000,&clock_pulse,&sink)==4);SF_CHECK(sink.last==250'000'000);SF_CHECK(!midi_clock.observe(2,1,100));SF_CHECK(midi_clock.observe(3,1,1'000'000));SF_CHECK(midi_clock.observe(3,2,21'833'333));SF_CHECK(midi_clock.status().received==2&&!midi_clock.status().physical_outputs_armed);
}

void test_monitor_graph_router() {
    stageforge::AudioGraph graph;
    stageforge::MonitorGraphRouter router;
    stageforge::MonitorBus alex;
    alex.set_master(80.0F);
    alex.set_level(stageforge::MonitorChannel::self, 90.0F);
    alex.set_level(stageforge::MonitorChannel::click, 25.0F);
    SF_CHECK(router.sync("alex", alex, graph));
    const int output = router.output_for("alex");
    const int self_source = router.self_source_for("alex");
    SF_CHECK(output == 1);
    SF_CHECK(self_source == stageforge::MonitorGraphRouter::self_source_base);
    SF_CHECK(graph.route_gain(static_cast<std::uint8_t>(self_source), static_cast<std::uint8_t>(output)) > 0.89F);
    SF_CHECK(graph.route_gain(stageforge::MonitorGraphRouter::click_source, static_cast<std::uint8_t>(output)) > 0.24F);
    SF_CHECK(graph.output_master(static_cast<std::uint8_t>(output)) > 0.79F);
    alex.set_muted(true);
    SF_CHECK(router.sync("alex", alex, graph));
    SF_CHECK(graph.output_master(static_cast<std::uint8_t>(output)) == 0.0F);
}

void test_artnet_udp_explicit_arm() {
    stageforge::ArtNetUdpOutput output;
    SF_CHECK(output.configure("127.0.0.1", 6454));
    stageforge::DmxUniverseState universe;
    universe.set(1, 123);
    const auto packet = stageforge::ArtNet::encode_dmx(0, universe.values(), 1);
    SF_CHECK(!output.send(packet)); // configuration alone never transmits
    output.arm(true);
    SF_CHECK(output.send(packet));
    const auto status = output.status();
    SF_CHECK(status.configured);
    SF_CHECK(status.armed);
    SF_CHECK(status.packets_sent == 1);
    output.arm(false);
    SF_CHECK(!output.send(packet));
    output.close();
}

void silence_render(void* raw, float* interleaved, std::uint32_t frames, std::uint32_t channels) noexcept {
    auto* calls = static_cast<std::atomic<std::uint64_t>*>(raw);
    calls->fetch_add(1, std::memory_order_relaxed);
    std::fill_n(interleaved, static_cast<std::size_t>(frames) * channels, 0.0F);
}

void test_alsa_runtime_stream_when_available() {
#if defined(__linux__)
    stageforge::AlsaAudioOutput output;
    std::atomic<std::uint64_t> calls{0};
    if (!output.open("null", {48000.0, 0, 2, 64}, silence_render, &calls)) {
        // libasound is an optional runtime dependency; absence is a supported
        // configuration rather than a native-core failure.
        return;
    }
    SF_CHECK(output.start());
    std::this_thread::sleep_for(std::chrono::milliseconds(15));
    output.stop();
    const auto status = output.status();
    SF_CHECK(status.callback_count > 0);
    SF_CHECK(calls.load(std::memory_order_relaxed) > 0);
    output.close();
#endif
}

void test_audio_input_ring() {
    stageforge::AudioInputRing<8> ring;
    const float interleaved[]{1.0F, -1.0F, 0.5F, -0.5F, 0.25F, -0.25F};
    SF_CHECK(ring.push_interleaved(interleaved, 3, 2) == 3);
    SF_CHECK(ring.queued() == 3);
    float left[4]{};
    float right[4]{};
    SF_CHECK(ring.pop_planar(left, right, 4) == 3);
    SF_CHECK(left[0] == 1.0F && right[0] == -1.0F);
    SF_CHECK(left[2] == 0.25F && right[2] == -0.25F);
    SF_CHECK(left[3] == 0.0F && right[3] == 0.0F);
    SF_CHECK(ring.underruns() == 1);
}

void capture_to_counter(void* raw, const float*, std::uint32_t frames, std::uint32_t) noexcept {
    auto* captured = static_cast<std::atomic<std::uint64_t>*>(raw);
    captured->fetch_add(frames, std::memory_order_relaxed);
}

void test_captured_input_routes_to_player_monitor_source() {
    stageforge::AudioGraph graph;
    stageforge::MonitorGraphRouter router;
    stageforge::MonitorBus bus;
    bus.set_master(100.0F);
    bus.set_level(stageforge::MonitorChannel::self, 50.0F);
    SF_CHECK(router.sync("jordan", bus, graph));
    const auto source_id = static_cast<std::uint8_t>(router.self_source_for("jordan"));
    const auto output_id = static_cast<std::uint8_t>(router.output_for("jordan"));

    stageforge::AudioInputRing<16> ring;
    const float captured[]{0.8F, -0.8F, 0.4F, -0.4F};
    SF_CHECK(ring.push_interleaved(captured, 2, 2) == 2);
    float source_left[2]{}, source_right[2]{};
    SF_CHECK(ring.pop_planar(source_left, source_right, 2) == 2);
    const stageforge::AudioSourceBlock source{source_id, source_left, source_right};
    float out_left[2]{}, out_right[2]{};
    stageforge::AudioOutputBlock output{output_id, out_left, out_right};
    graph.process(std::span<const stageforge::AudioSourceBlock>(&source, 1), std::span<stageforge::AudioOutputBlock>(&output, 1), 2);
    SF_CHECK(out_left[0] > 0.39F && out_left[0] < 0.41F);
    SF_CHECK(out_right[0] < -0.39F && out_right[0] > -0.41F);
}

void test_alsa_runtime_capture_when_available() {
#if defined(__linux__)
    stageforge::AlsaAudioInput input;
    std::atomic<std::uint64_t> frames{0};
    if (!input.open("null", {48000.0, 2, 0, 64}, capture_to_counter, &frames)) return;
    SF_CHECK(input.start());
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    input.stop();
    const auto stopped = input.status();
    // The ALSA null capture PCM is useful when present, but some CI/container
    // builds expose it without supporting a stable capture loop. Opening and
    // starting proves the dynamic backend contract; a later recover failure is
    // an environmental device condition, not a lifecycle-contract failure.
    SF_CHECK(stopped.state == stageforge::AudioDeviceState::open ||
             stopped.state == stageforge::AudioDeviceState::faulted);
    if (stopped.state == stageforge::AudioDeviceState::faulted) SF_CHECK(stopped.xruns > 0);
    input.close();
    SF_CHECK(input.status().state == stageforge::AudioDeviceState::closed);
#endif
}


void test_audio_fanout_ring() {
    stageforge::AudioFanoutRing<16, 2> ring;
    ring.set_reader_active(0, true);
    ring.set_reader_active(1, true);
    const float interleaved[] = {0.1F, -0.1F, 0.2F, -0.2F, 0.3F, -0.3F};
    SF_CHECK(ring.push_interleaved(interleaved, 3, 2) == 3);
    float l0[3]{}, r0[3]{}, l1[3]{}, r1[3]{};
    SF_CHECK(ring.pop_planar(0, l0, r0, 3) == 3);
    SF_CHECK(ring.pop_planar(1, l1, r1, 3) == 3);
    SF_CHECK(std::abs(l0[2] - 0.3F) < 0.0001F);
    SF_CHECK(std::abs(r1[1] + 0.2F) < 0.0001F);
    SF_CHECK(ring.queued(0) == 0);
    SF_CHECK(ring.queued(1) == 0);

    ring.set_reader_active(1, false);
    std::array<float, 40> mono{};
    for (std::size_t i = 0; i < mono.size(); ++i) mono[i] = static_cast<float>(i) / 40.0F;
    SF_CHECK(ring.push_interleaved(mono.data(), mono.size(), 1) == mono.size());
    SF_CHECK(ring.dropped(0) > 0);
    SF_CHECK(ring.dropped(1) == 0);

    ring.set_reader_active(0,true);
    const float invalid[]{NAN,INFINITY};float sanitized_left[1]{1},sanitized_right[1]{1};
    SF_CHECK(ring.push_interleaved(invalid,1,2)==1);SF_CHECK(ring.pop_planar(0,sanitized_left,sanitized_right,1)==1);SF_CHECK(sanitized_left[0]==0.0F&&sanitized_right[0]==0.0F);
}

void test_capture_ingress_audit_is_bounded_and_unarmed(){stageforge::CaptureIngressAudit audit;audit.finish(256,1,0,2,100);audit.finish(128,1,1,0,80);const auto s=audit.status();SF_CHECK(s.callbacks==2&&s.frames==384&&s.record_blocks==2&&s.queue_rejections==1&&s.nonfinite_samples==2&&s.max_duration_ns==100&&!s.physical_outputs_armed);}
void test_shared_capture_ingress_preserves_samples_generation_and_discontinuities(){
    using Queue=stageforge::DawRecordingQueue<2,4,4>;
    stageforge::AudioFanoutRing<32,1> ring;
    ring.set_reader_active(0,true);
    Queue queue;
    SF_CHECK(queue.arm(0,true));
    std::atomic<std::uint64_t> sequence{0},frame{0},generation{queue.generation(0)};
    const float first[]{.1F,-.1F,.2F,-.2F,.3F,-.3F,.4F,-.4F};
    auto result=stageforge::submit_capture_packet(ring,&queue,0,sequence,frame,generation,first,4,2);
    SF_CHECK(result.blocks==1&&result.rejected==0&&result.nonfinite_samples==0);
    Queue::Block block{};
    SF_CHECK(queue.pop(0,block));
    SF_CHECK(block.sequence==1&&block.generation==generation.load()&&block.show_frame==0&&block.frames==4);
    SF_CHECK(std::abs(block.left[2]-.3F)<.0001F&&std::abs(block.right[2]+.3F)<.0001F);

    const float second[]{.5F,-.5F,.6F,-.6F};
    const stageforge::CapturePacketInfo discontinuity{true,false,0.0};
    result=stageforge::submit_capture_packet(ring,&queue,0,sequence,frame,generation,second,2,2,discontinuity);
    SF_CHECK(result.blocks==1&&result.rejected==0);
    SF_CHECK(queue.pop(0,block)&&block.sequence==3&&block.show_frame==4&&block.frames==2);
    SF_CHECK(queue.status(0).sequence_gaps==1);

    const float damaged[]{NAN,.25F,INFINITY,-.25F};
    result=stageforge::submit_capture_packet(ring,&queue,0,sequence,frame,generation,damaged,2,2);
    SF_CHECK(result.nonfinite_samples==2&&queue.pop(0,block));
    SF_CHECK(block.left[0]==0.0F&&block.right[0]==.25F&&block.left[1]==0.0F&&block.right[1]==-.25F);
    float ring_left[8]{},ring_right[8]{};
    SF_CHECK(ring.pop_planar(0,ring_left,ring_right,8)==8);
    SF_CHECK(std::abs(ring_left[0]-.1F)<.0001F&&std::abs(ring_right[0]+.1F)<.0001F);
    SF_CHECK(ring_left[6]==0.0F&&ring_right[6]==.25F&&ring_left[7]==0.0F&&ring_right[7]==-.25F);
    queue.disarm(0);
    result=stageforge::submit_capture_packet(ring,&queue,0,sequence,frame,generation,first,4,2);
    SF_CHECK(result.rejected==1&&queue.status(0).stale==1);
}
void test_lighting_ingress_audit_is_bounded_and_unarmed(){stageforge::LightingIngressAudit audit;audit.note_handoff(true);audit.note_handoff(false);audit.note_drain(3,90);audit.note_drain(2,50);const auto s=audit.status();SF_CHECK(s.accepted==1&&s.queue_rejections==1&&s.drained==5&&s.drain_calls==2&&s.max_drain_duration_ns==90&&!s.physical_outputs_armed);}

void test_adaptive_drift_controller_and_resampler() {
    stageforge::AdaptiveDriftController controller({2000.0, 1000.0, 1.0});
    const double fast = controller.update(500.0, true, 256, 256);
    SF_CHECK(fast < 0.0);
    std::uint64_t total_source = 0;
    for (int i = 0; i < 2000; ++i) total_source += controller.source_frames_for(256);
    SF_CHECK(total_source < static_cast<std::uint64_t>(2000 * 256));

    controller.reset();
    const double filling = controller.update(0.0, false, 512, 256);
    SF_CHECK(filling > 0.0);

    const float in_l[] = {0.0F, 1.0F, 2.0F, 3.0F};
    const float in_r[] = {3.0F, 2.0F, 1.0F, 0.0F};
    float out_l[8]{}, out_r[8]{};
    stageforge::resample_planar_linear(in_l, in_r, 4, out_l, out_r, 8);
    SF_CHECK(std::abs(out_l[0] - 0.0F) < 0.0001F);
    SF_CHECK(std::abs(out_l[7] - 3.0F) < 0.0001F);
    SF_CHECK(std::abs(out_r[7] - 0.0F) < 0.0001F);
}






struct LoopTestContext {
    stageforge::CoreCueState cues{};
    stageforge::CoreAutomationState<16> automation{};
    std::atomic<std::uint64_t> dispatched{0};
};

bool loop_test_sink(void* raw, const stageforge::ShowEvent& event, bool) noexcept {
    auto* context = static_cast<LoopTestContext*>(raw);
    if (!context) return false;
    if (event.type == stageforge::ShowEventType::cue) context->cues.apply(event);
    if (event.type == stageforge::ShowEventType::automation && !context->automation.apply(event).applied()) return false;
    context->dispatched.fetch_add(1, std::memory_order_release);
    return true;
}

bool wait_for_count(const std::atomic<std::uint64_t>& value, std::uint64_t expected, std::chrono::milliseconds timeout) {
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    while (std::chrono::steady_clock::now() < deadline) {
        if (value.load(std::memory_order_acquire) >= expected) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    return value.load(std::memory_order_acquire) >= expected;
}

void test_show_execution_loop_automatic_owner_and_cue_state() {
    stageforge::TransportClock clock(48000.0, 120.0);
    LoopTestContext context{};
    stageforge::ShowExecutionLoop<16, 32, 16> loop(clock, &loop_test_sink, &context);
    SF_CHECK(loop.start());

    stageforge::ShowEvent immediate{};
    immediate.event_id = 100;
    immediate.show_time_ns = 0;
    immediate.type = stageforge::ShowEventType::cue;
    immediate.priority = SF_PRIORITY_SHOW;
    immediate.payload.cue = {11};
    SF_CHECK(loop.submit(immediate));
    SF_CHECK(wait_for_count(context.dispatched, 1, std::chrono::milliseconds(100)));
    auto cue = context.cues.snapshot();
    SF_CHECK(cue.current_cue_id == 11);
    SF_CHECK(cue.previous_cue_id == 0);
    SF_CHECK(cue.transitions == 1);

    // A paused show clock does not advance future events, but the compatibility
    // drain request is executed by the same owner thread.
    stageforge::ShowEvent paused_future{};
    paused_future.event_id = 101;
    paused_future.show_time_ns = 50'000'000;
    paused_future.type = stageforge::ShowEventType::cue;
    paused_future.priority = SF_PRIORITY_SHOW;
    paused_future.payload.cue = {12};
    SF_CHECK(loop.submit(paused_future));
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    SF_CHECK(context.dispatched.load(std::memory_order_acquire) == 1);
    SF_CHECK(loop.drain_until(50'000'000) == 1);
    SF_CHECK(context.dispatched.load(std::memory_order_acquire) == 2);
    cue = context.cues.snapshot();
    SF_CHECK(cue.current_cue_id == 12);
    SF_CHECK(cue.previous_cue_id == 11);

    stageforge::ShowEvent cancelled{};
    cancelled.event_id = 102;
    cancelled.show_time_ns = 100'000'000;
    cancelled.type = stageforge::ShowEventType::cue;
    cancelled.priority = SF_PRIORITY_SHOW;
    cancelled.payload.cue = {13};
    SF_CHECK(loop.submit(cancelled));
    SF_CHECK(loop.cancel(stageforge::ShowEventType::cue, 102));
    SF_CHECK(loop.drain_until(100'000'000) == 0);

    // With transport running, a near-future event dispatches without a manual
    // drain command.
    clock.seek_seconds(0.0);
    clock.play();
    stageforge::ShowEvent automatic{};
    automatic.event_id = 103;
    automatic.show_time_ns = 20'000'000;
    automatic.type = stageforge::ShowEventType::cue;
    automatic.priority = SF_PRIORITY_SHOW;
    automatic.payload.cue = {14};
    SF_CHECK(loop.submit(automatic));
    SF_CHECK(wait_for_count(context.dispatched, 3, std::chrono::milliseconds(250)));
    clock.pause();
    cue = context.cues.snapshot();
    SF_CHECK(cue.current_cue_id == 14);
    SF_CHECK(cue.transitions == 3);
    const auto loop_metrics = loop.loop_metrics();
    SF_CHECK(loop_metrics.running);
    SF_CHECK(loop_metrics.cycles > 0);
    SF_CHECK(loop_metrics.dispatched >= 3);
    SF_CHECK(loop_metrics.manual_drains >= 2);
    SF_CHECK(loop_metrics.cancel_requests >= 1);
    loop.stop();
    SF_CHECK(!loop.loop_metrics().running);
}

void test_show_event_timeline_order_replay_and_late_policy() {
    stageforge::ShowEventDispatcher<16, 16, 8> dispatcher;

    stageforge::ShowEvent midi{};
    midi.event_id = 1;
    midi.show_time_ns = 1000;
    midi.type = stageforge::ShowEventType::midi;
    midi.priority = SF_PRIORITY_SHOW;
    midi.payload.midi = {0x90, 60, 100, 0};
    SF_CHECK(dispatcher.submit(midi));

    stageforge::ShowEvent lighting{};
    lighting.event_id = 1; // Domain-scoped replay identity preserves legacy IDs.
    lighting.show_time_ns = 1000;
    lighting.type = stageforge::ShowEventType::lighting;
    lighting.priority = SF_PRIORITY_PRODUCTION;
    lighting.payload.lighting = {0, 1, 77, {0,0,0}};
    SF_CHECK(dispatcher.submit(lighting));

    stageforge::ShowEvent transport{};
    transport.event_id = 2;
    transport.show_time_ns = 1000;
    transport.type = stageforge::ShowEventType::transport;
    transport.priority = SF_PRIORITY_CRITICAL;
    transport.payload.transport = {SF_CORE_TRANSPORT_PLAY, 0.0};
    SF_CHECK(dispatcher.submit(transport));

    // Duplicate in the same domain is accepted into ingress, then rejected by
    // dispatcher replay protection when the owner ingests it.
    SF_CHECK(dispatcher.submit(midi));

    std::array<stageforge::ShowEventType, 4> order{};
    std::size_t index = 0;
    const auto dispatched = dispatcher.dispatch_due(1000, [&](const stageforge::ShowEvent& event, bool late) noexcept {
        SF_CHECK(!late);
        order[index++] = event.type;
        return true;
    });
    SF_CHECK(dispatched == 3);
    SF_CHECK(index == 3);
    SF_CHECK(order[0] == stageforge::ShowEventType::transport);
    SF_CHECK(order[1] == stageforge::ShowEventType::midi);
    SF_CHECK(order[2] == stageforge::ShowEventType::lighting);
    auto metrics = dispatcher.metrics();
    SF_CHECK(metrics.duplicates == 1);
    SF_CHECK(metrics.pending == 0);

    stageforge::ShowEvent late{};
    late.event_id = 9;
    late.show_time_ns = 2000;
    late.type = stageforge::ShowEventType::cue;
    late.priority = SF_PRIORITY_PRODUCTION;
    late.flags = stageforge::show_event_drop_if_late;
    late.payload.cue = {42};
    SF_CHECK(dispatcher.submit(late));
    SF_CHECK(dispatcher.dispatch_due(2001, [](const stageforge::ShowEvent&, bool) noexcept { return true; }) == 0);
    metrics = dispatcher.metrics();
    SF_CHECK(metrics.late == 1);
    SF_CHECK(metrics.dropped_late == 1);
}

void test_show_event_cancel_and_timeline_capacity() {
    stageforge::ShowEventDispatcher<8, 2, 8> dispatcher;
    for (std::uint64_t id = 1; id <= 3; ++id) {
        stageforge::ShowEvent event{};
        event.event_id = id;
        event.show_time_ns = 1000 + id;
        event.type = stageforge::ShowEventType::cue;
        event.priority = SF_PRIORITY_PRODUCTION;
        event.payload.cue = {100 + id};
        SF_CHECK(dispatcher.submit(event));
    }
    dispatcher.ingest_pending();
    auto metrics = dispatcher.metrics();
    SF_CHECK(metrics.accepted == 2);
    SF_CHECK(metrics.timeline_overflow == 1);
    SF_CHECK(dispatcher.cancel(stageforge::ShowEventType::cue, 1));
    SF_CHECK(!dispatcher.cancel(stageforge::ShowEventType::cue, 999));
    metrics = dispatcher.metrics();
    SF_CHECK(metrics.cancelled == 1);
    SF_CHECK(metrics.pending == 1);
}

void test_core_automation_points_ramps_and_ownership() {
    stageforge::CoreAutomationState<4> automation;

    stageforge::ShowEvent point{};
    point.event_id = 7001;
    point.show_time_ns = 1'000'000'000ULL;
    point.owner_id = 77;
    point.type = stageforge::ShowEventType::automation;
    point.priority = SF_PRIORITY_SHOW;
    point.payload.automation = {100, 200, 0.25F, 0};
    SF_CHECK(automation.apply(point).applied());

    stageforge::AutomationParameterSnapshot state{};
    SF_CHECK(automation.snapshot(100, 200, 1'000'000'000ULL, state));
    SF_CHECK(state.owner_id == 77);
    SF_CHECK(std::abs(state.current_value - 0.25F) < 0.0001F);
    SF_CHECK(!state.ramping);

    stageforge::ShowEvent ramp{};
    ramp.event_id = 7002;
    ramp.show_time_ns = 2'000'000'000ULL;
    ramp.owner_id = 77;
    ramp.type = stageforge::ShowEventType::automation;
    ramp.priority = SF_PRIORITY_SHOW;
    ramp.payload.automation = {100, 200, 1.0F, 1000};
    SF_CHECK(automation.apply(ramp).applied());
    SF_CHECK(automation.snapshot(100, 200, 2'500'000'000ULL, state));
    SF_CHECK(state.ramping);
    SF_CHECK(std::abs(state.current_value - 0.625F) < 0.001F);
    SF_CHECK(automation.snapshot(100, 200, 3'500'000'000ULL, state));
    SF_CHECK(!state.ramping);
    SF_CHECK(std::abs(state.current_value - 1.0F) < 0.0001F);

    float block[5]{};
    SF_CHECK(automation.render_block(100, 200, 2'000'000'000ULL, 250'000'000ULL, block, 5));
    SF_CHECK(std::abs(block[0] - 0.25F) < 0.001F);
    SF_CHECK(std::abs(block[2] - 0.625F) < 0.001F);
    SF_CHECK(std::abs(block[4] - 1.0F) < 0.001F);

    stageforge::ShowEvent conflict = ramp;
    conflict.event_id = 7003;
    conflict.owner_id = 88;
    conflict.payload.automation.value = 0.0F;
    const auto rejected = automation.apply(conflict);
    SF_CHECK(rejected.status == stageforge::AutomationApplyStatus::owner_conflict);

    stageforge::ShowEvent release{};
    release.event_id = 7004;
    release.show_time_ns = 3'500'000'000ULL;
    release.owner_id = 77;
    release.type = stageforge::ShowEventType::automation;
    release.priority = SF_PRIORITY_SHOW;
    release.flags = stageforge::show_event_automation_release_owner;
    release.payload.automation = {100, 200, 0.0F, 0};
    SF_CHECK(automation.apply(release).applied());
    SF_CHECK(automation.snapshot(100, 200, 3'500'000'000ULL, state));
    SF_CHECK(state.owner_id == 0);

    conflict.event_id = 7005;
    conflict.show_time_ns = 4'000'000'000ULL;
    conflict.owner_id = 88;
    conflict.payload.automation = {100, 200, 0.5F, 0};
    SF_CHECK(automation.apply(conflict).applied());
    SF_CHECK(automation.snapshot(100, 200, 4'000'000'000ULL, state));
    SF_CHECK(state.owner_id == 88);
    SF_CHECK(std::abs(state.current_value - 0.5F) < 0.0001F);

    const auto metrics = automation.metrics();
    SF_CHECK(metrics.registered == 1);
    SF_CHECK(metrics.owner_conflicts == 1);
    SF_CHECK(metrics.owner_releases == 1);
    SF_CHECK(metrics.applied == 4);
}

void test_show_execution_loop_owns_automation_state() {
    stageforge::TransportClock clock(48000.0, 120.0);
    LoopTestContext context{};
    stageforge::ShowExecutionLoop<16, 32, 16> loop(clock, &loop_test_sink, &context);
    SF_CHECK(loop.start());

    stageforge::ShowEvent automation{};
    automation.event_id = 7100;
    automation.show_time_ns = 0;
    automation.owner_id = 55;
    automation.type = stageforge::ShowEventType::automation;
    automation.priority = SF_PRIORITY_SHOW;
    automation.payload.automation = {9, 10, 0.8F, 0};
    SF_CHECK(loop.submit(automation));
    SF_CHECK(wait_for_count(context.dispatched, 1, std::chrono::milliseconds(100)));
    stageforge::AutomationParameterSnapshot state{};
    SF_CHECK(context.automation.snapshot(9, 10, 0, state));
    SF_CHECK(state.last_event_id == 7100);
    SF_CHECK(state.owner_id == 55);
    SF_CHECK(std::abs(state.current_value - 0.8F) < 0.0001F);
    loop.stop();
}



struct TestParameterSink { float value{0.0F}; std::uint64_t writes{0}; };
void apply_test_parameter(void* raw, float value) noexcept {
    auto* sink = static_cast<TestParameterSink*>(raw);
    if (sink) { sink->value = value; ++sink->writes; }
}
struct TestPlugin { std::uint32_t parameter{0}; float value{0.0F}; std::uint64_t writes{0}; };
void set_test_plugin(void* raw, std::uint32_t parameter, float value) noexcept {
    auto* plugin = static_cast<TestPlugin*>(raw);
    if (plugin) { plugin->parameter = parameter; plugin->value = value; ++plugin->writes; }
}


void test_audio_graph_atomic_route_transaction() {
    stageforge::AudioGraph graph;
    graph.set_route_gain(0,0,1.0F);
    graph.set_route_gain(1,0,0.5F);
    const std::array<stageforge::AudioRouteChange,3> changes{{
        {0,0,0.25F}, {1,0,0.75F}, {2,1,1.0F}
    }};
    SF_CHECK(graph.apply_route_transaction(changes));
    SF_CHECK(std::abs(graph.route_gain(0,0)-0.25F)<0.0001F);
    SF_CHECK(std::abs(graph.route_gain(1,0)-0.75F)<0.0001F);
    SF_CHECK(std::abs(graph.route_gain(2,1)-1.0F)<0.0001F);
}

void test_core_parameter_registry_and_plugin_bridge() {
    stageforge::CoreAutomationState<16> automation;
    stageforge::CoreParameterRegistry<8> registry;
    TestParameterSink sink{};
    stageforge::CoreParameterDescriptor descriptor{};
    descriptor.target_id = 11; descriptor.parameter_id = 22;
    descriptor.minimum = 0.0F; descriptor.maximum = 1.0F; descriptor.default_value = 0.25F;
    descriptor.timing = stageforge::CoreParameterTiming::show;
    descriptor.endpoint_kind = stageforge::CoreParameterEndpointKind::mixer_gain;
    SF_CHECK(registry.register_endpoint(descriptor, &apply_test_parameter, &sink));
    SF_CHECK(automation.seed(11,22,descriptor.default_value));
    SF_CHECK(std::abs(sink.value - 0.25F) < 0.0001F);

    stageforge::ShowEvent ramp{}; ramp.event_id=8100; ramp.show_time_ns=1'000'000'000ULL; ramp.owner_id=7;
    ramp.type=stageforge::ShowEventType::automation; ramp.priority=SF_PRIORITY_SHOW;
    ramp.payload.automation={11,22,1.0F,1000};
    SF_CHECK(automation.apply(ramp).applied());
    registry.apply_control(automation, 1'500'000'000ULL);
    SF_CHECK(std::abs(sink.value - 0.625F) < 0.001F);
    stageforge::CoreParameterStatus status{};
    SF_CHECK(registry.status(11,22,status));
    SF_CHECK(status.applications >= 2);

    TestPlugin plugin{};
    stageforge::CorePluginParameterBinding binding{&plugin, 123, &set_test_plugin};
    stageforge::apply_plugin_parameter(&binding, 0.75F);
    SF_CHECK(plugin.parameter == 123);
    SF_CHECK(std::abs(plugin.value - 0.75F) < 0.0001F);
    SF_CHECK(plugin.writes == 1);
}

struct TestEffect { float gain{1.0F}; bool fail{false}; std::uint64_t activations{0},processed{0}; };
bool activate_test_effect(void* raw,double rate,std::uint32_t frames,std::uint32_t channels) noexcept {auto* e=static_cast<TestEffect*>(raw);if(!e||rate<=0||!frames||!channels)return false;++e->activations;return true;}
bool process_test_effect(void* raw,float* const* channels,std::uint32_t count,std::uint32_t frames,std::uint64_t) noexcept {auto* e=static_cast<TestEffect*>(raw);if(!e||e->fail)return false;++e->processed;for(std::uint32_t c=0;c<count;++c)for(std::uint32_t f=0;f<frames;++f)channels[c][f]*=e->gain;return true;}
void deactivate_test_effect(void*) noexcept {}

void test_effect_delay_transaction_commits_and_rolls_back_one_generation(){
    std::array<stageforge::CoreEffectChain<2>,2> chains{};TestEffect effect{};
    SF_CHECK(chains[0].register_effect({41,stageforge::CoreEffectFormat::builtin,2,3,true},{&effect,&activate_test_effect,&process_test_effect,&deactivate_test_effect}));
    SF_CHECK(chains[0].activate_all(192000.0,8,2));
    stageforge::EffectDelayTransaction<2,2,16> transaction(chains);const std::uint32_t delays[]{3,0};
    const stageforge::EffectDelayTransaction<2,2,16>::Change change{0,41,true};
    SF_CHECK(transaction.prepare(1,100,delays,2,&change,1));
    float left[]{1,0,0,0},right[]{-1,0,0,0};float*channels[]{left,right};
    SF_CHECK(transaction.process(0,channels,2,4,99));SF_CHECK(effect.processed==1);
    SF_CHECK(transaction.process(0,channels,2,4,100));SF_CHECK(effect.processed==1);
    auto status=transaction.status();SF_CHECK(status.active_generation==1&&status.commits==1&&status.changes==1&&status.maximum_latency_frames==3);
    SF_CHECK(transaction.prepare_rollback(2,200));SF_CHECK(transaction.process(0,channels,2,4,200));SF_CHECK(effect.processed==2);
    status=transaction.status();SF_CHECK(status.active_generation==2&&status.rollbacks==1&&!status.physical_outputs_armed);
}

void test_independent_polyphonic_streaming_voices_are_generation_fenced(){
    stageforge::StreamingVoiceEngine<2,4,4> engine;using Block=stageforge::StreamingVoiceBlock<4>;
    SF_CHECK(engine.start(0,10,1.0F,false));SF_CHECK(engine.start(1,20,0.5F,true));
    Block a{};a.generation=10;a.sequence=1;a.frames=4;a.terminal=true;a.left={1,1,1,1};a.right={1,1,1,1};
    Block stale=a;stale.generation=19;Block b{};b.generation=20;b.sequence=2;b.frames=4;b.left={2,2,2,2};b.right={-2,-2,-2,-2};
    SF_CHECK(engine.push(0,a));SF_CHECK(engine.push(1,stale));SF_CHECK(engine.push(1,b));
    float left[4]{},right[4]{};engine.render(left,right,4);
    SF_CHECK(left[0]==2.0F&&right[0]==0.0F);auto status=engine.status();
    SF_CHECK(status.active_voices==1&&status.starts==2&&status.completed_voices==1&&status.stale_blocks==1&&status.discontinuities==1&&!status.disk_io_in_audio_callback&&!status.physical_outputs_armed);
    engine.render(left,right,4);status=engine.status();SF_CHECK(status.starved_blocks==1&&status.active_voices==1);
    SF_CHECK(engine.stop(1,20));engine.render(left,right,1);SF_CHECK(engine.status().active_voices==0&&engine.status().stops==1);
}

void test_format_neutral_effect_chain_processing_and_failure_bypass() {
    stageforge::CoreEffectChain<4> chain;
    TestEffect vst{2.0F,false,0}, clap{0.5F,false,0};
    SF_CHECK(chain.register_effect({1,stageforge::CoreEffectFormat::vst3,2,16,true},{&vst,&activate_test_effect,&process_test_effect,&deactivate_test_effect}));
    SF_CHECK(chain.register_effect({2,stageforge::CoreEffectFormat::clap,2,8,true},{&clap,&activate_test_effect,&process_test_effect,&deactivate_test_effect}));
    SF_CHECK(chain.activate_all(48000.0,256,2));
    float left[4]{1,2,3,4},right[4]{2,4,6,8};float* channels[2]{left,right};
    SF_CHECK(chain.process(channels,2,4,1'000));
    SF_CHECK(std::abs(left[2]-3.0F)<0.0001F && std::abs(right[3]-8.0F)<0.0001F);
    clap.fail=true;
    SF_CHECK(!chain.process(channels,2,4,2'000));
    stageforge::CoreEffectSlotStatus failed{};SF_CHECK(chain.slot_status(2,failed));SF_CHECK(failed.bypassed&&failed.failures==1);
    const auto status=chain.status();SF_CHECK(status.registered==2&&status.active==2&&status.bypassed==1&&status.total_latency_frames==24);
}

void graph_gain_effect(void*,std::uint8_t,float* left,float* right,std::size_t frames) noexcept {for(std::size_t i=0;i<frames;++i){left[i]*=4.0F;right[i]*=4.0F;}}
void test_effect_chain_runs_before_output_limiter() {
    stageforge::AudioGraph graph;graph.set_route_gain(0,0,1.0F);graph.set_limiter_ceiling_db(0,-6.0F);
    float input[2]{0.5F,0.5F},left[2]{},right[2]{};
    stageforge::AudioSourceBlock source{0,input,input};stageforge::AudioOutputBlock output{0,left,right};
    graph.process(std::span<const stageforge::AudioSourceBlock>(&source,1),std::span<stageforge::AudioOutputBlock>(&output,1),2,&graph_gain_effect,nullptr);
    SF_CHECK(std::abs(left[0])<=0.502F&&std::abs(right[1])<=0.502F);
}

void test_pcm_integer_and_multichannel_conversion() {
    const float samples[8]{1.0F,-1.0F,0.5F,-0.5F,0.25F,-0.25F,0.0F,0.75F};
    for (const auto format : {stageforge::CanonicalAudioSampleFormat::signed16,
                              stageforge::CanonicalAudioSampleFormat::signed24,
                              stageforge::CanonicalAudioSampleFormat::signed32}) {
        std::array<std::uint8_t, 32> pcm{};
        float decoded[8]{};
        SF_CHECK(stageforge::encode_interleaved_pcm(samples,format,2,4,pcm.data()));
        SF_CHECK(stageforge::decode_interleaved_pcm(pcm.data(),format,2,4,decoded));
        const float tolerance=format==stageforge::CanonicalAudioSampleFormat::signed16?0.00005F:0.000001F;
        for(std::size_t i=0;i<8;++i)SF_CHECK(std::abs(decoded[i]-samples[i])<tolerance);
    }
    stageforge::CanonicalAudioSampleFormat parsed{};
    SF_CHECK(stageforge::canonical_audio_sample_format_from_name("S24_3LE",parsed));
    SF_CHECK(parsed==stageforge::CanonicalAudioSampleFormat::signed24);
    SF_CHECK(stageforge::canonical_audio_sample_bytes(parsed)==3);
    SF_CHECK(!stageforge::canonical_audio_sample_format_from_name("invented",parsed));
}

void test_alsa_integer_multichannel_stream_when_available() {
#if defined(__linux__)
    stageforge::AlsaAudioOutput output;
    std::atomic<std::uint64_t> calls{0};
    if (output.open("null", {48000.0, 0, 4, 64}, silence_render, &calls, "S16_LE")) {
        SF_CHECK(output.sample_format()=="S16_LE");
        SF_CHECK(output.status().config.output_channels==4);
        SF_CHECK(output.start());
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        output.stop();
        SF_CHECK(output.status().callback_count>0);
        output.close();
    }
    stageforge::AlsaAudioInput input;
    std::atomic<std::uint64_t> frames{0};
    if (input.open("null", {48000.0, 4, 0, 64}, capture_to_counter, &frames, "S16_LE")) {
        SF_CHECK(input.sample_format()=="S16_LE");
        SF_CHECK(input.status().config.input_channels==4);
        input.close();
    }
#endif
}

void test_canonical_192khz_rate_conversion() {
    stageforge::CanonicalAudioRateConverter converter;SF_CHECK(converter.configure(48'000.0));
    SF_CHECK(converter.output_frames_for(48)==192);float in_l[48],in_r[48],out_l[192]{},out_r[192]{};
    std::fill_n(in_l,48,0.25F);std::fill_n(in_r,48,-0.5F);SF_CHECK(converter.process(in_l,in_r,48,out_l,out_r,192));
    for(std::size_t i=0;i<192;++i){SF_CHECK(std::abs(out_l[i]-0.25F)<0.001F);SF_CHECK(std::abs(out_r[i]+0.5F)<0.001F);}
    const auto status=converter.status();SF_CHECK(status.source_rate==48'000.0&&status.destination_rate==192'000.0&&status.converted_blocks==1&&status.output_frames==192);
    stageforge::CanonicalAudioRateConverter cd;SF_CHECK(cd.configure(44'100.0));std::uint64_t total=0;for(int i=0;i<100;++i)total+=cd.output_frames_for(441);SF_CHECK(total==192000);

    const std::int16_t pcm16[4]{-32768,32767,16384,-16384};float norm_l[2]{},norm_r[2]{};
    SF_CHECK(stageforge::normalize_interleaved_pcm(pcm16,stageforge::CanonicalAudioSampleFormat::signed16,2,2,norm_l,norm_r));
    SF_CHECK(std::abs(norm_l[0]+1.0F)<0.0001F&&norm_r[0]>0.999F&&std::abs(norm_l[1]-0.5F)<0.0001F&&std::abs(norm_r[1]+0.5F)<0.0001F);
    const std::uint8_t pcm24[6]{0x00,0x00,0x80,0xff,0xff,0x7f};
    SF_CHECK(stageforge::normalize_interleaved_pcm(pcm24,stageforge::CanonicalAudioSampleFormat::signed24,2,1,norm_l,norm_r));
    SF_CHECK(std::abs(norm_l[0]+1.0F)<0.0001F&&norm_l[1]>0.999F&&norm_l[0]==norm_r[0]&&norm_l[1]==norm_r[1]);
    const std::int32_t pcm32[2]{-2147483647-1,1073741824};
    SF_CHECK(stageforge::normalize_interleaved_pcm(pcm32,stageforge::CanonicalAudioSampleFormat::signed32,1,2,norm_l,norm_r));
    SF_CHECK(std::abs(norm_l[0]+1.0F)<0.0001F&&std::abs(norm_r[0]-0.5F)<0.0001F);
}

void test_le_uwb_hub_fenced_group_sync() {
    stageforge::LeUwbHub<4> hub;
    stageforge::LeUwbHubPolicy policy{};
    policy.target_presentation_lead_ns=10'000'000;
    policy.max_end_to_end_ns=25'000'000;
    policy.fresh_observation_ns=100'000'000;
    policy.holdover_ns=500'000'000;
    SF_CHECK(hub.configure(7,policy));
    SF_CHECK(hub.register_node({11,101,stageforge::LeUwbNodeRole::performer_input,2'000'000,true}));
    SF_CHECK(hub.register_node({12,102,stageforge::LeUwbNodeRole::monitor_output,3'000'000,true}));
    SF_CHECK(hub.register_node({13,103,stageforge::LeUwbNodeRole::lighting,1'000'000,false}));

    constexpr std::uint64_t hub_time=1'000'000'000ULL;
    SF_CHECK(hub.observe_uwb(11,1,7,hub_time,hub_time+100'000,8'000.0,50.0,40'000,true));
    SF_CHECK(hub.observe_le(11,1,7,1,hub_time,3'000'000,100'000,true));
    SF_CHECK(hub.observe_uwb(12,1,7,hub_time,hub_time-50'000,12'000.0,60.0,50'000,true));
    SF_CHECK(hub.observe_le(12,1,7,1,hub_time,4'000'000,150'000,true));
    const auto ready=hub.plan(hub_time+1'000'000,5'000'000'000ULL,7);
    SF_CHECK(ready.ready&&ready.required_nodes==2&&ready.ready_nodes==2&&ready.blocked_nodes==1);
    SF_CHECK(!ready.physical_outputs_armed&&ready.presentation_lead_ns==10'000'000);
    std::uint64_t node_target=0;
    SF_CHECK(hub.target_for(11,ready.generation,node_target));
    SF_CHECK(node_target>ready.target_hub_ns);

    // Replays, stale authority, unauthenticated evidence and excessive range
    // uncertainty all fail closed without replacing the last accepted sample.
    SF_CHECK(!hub.observe_uwb(11,1,7,hub_time+2,hub_time+2,1'000.0,10.0,10'000,true));
    SF_CHECK(!hub.observe_le(11,2,6,2,hub_time+2,1'000'000,10'000,true));
    SF_CHECK(!hub.observe_le(11,2,7,2,hub_time+2,1'000'000,10'000,false));
    SF_CHECK(!hub.observe_uwb(11,2,7,hub_time+2,hub_time+2,1'000.0,500.0,10'000,true));

    SF_CHECK(hub.observe_le(11,2,7,2,hub_time+150'000'000,3'000'000,100'000,true));
    SF_CHECK(hub.observe_le(12,2,7,2,hub_time+150'000'000,4'000'000,150'000,true));
    const auto holdover=hub.plan(hub_time+150'000'000,5'150'000'000ULL,7);
    SF_CHECK(holdover.ready&&holdover.holdover_nodes==2);
    SF_CHECK(!hub.plan(hub_time+300'000'000,5'300'000'000ULL,7).ready); // LE evidence has no long holdover.
    SF_CHECK(!hub.plan(hub_time+600'000'000,5'600'000'000ULL,7).ready);
    SF_CHECK(!hub.plan(hub_time+1'000'000,5'000'000'000ULL,8).ready);
    SF_CHECK(!hub.configure(6,policy));
}

void test_le_uwb_hardware_frames_and_nonblocking_loopback() {
    stageforge::UwbHardwareObservation uwb{};uwb.node_id=41;uwb.sequence=1;uwb.authority_epoch=9;
    uwb.hub_time_ns=1'000'000;uwb.node_time_ns=1'100'000;uwb.distance_mm=8'000.0;
    uwb.range_uncertainty_mm=25.0;uwb.clock_uncertainty_ns=20'000;uwb.authenticated=true;
    std::array<std::uint8_t,stageforge::uwb_hardware_frame_size> uwb_frame{};
    SF_CHECK(stageforge::encode_uwb_hardware_frame(uwb,uwb_frame));
    stageforge::UwbHardwareObservation decoded_uwb{};
    SF_CHECK(stageforge::decode_uwb_hardware_frame(uwb_frame.data(),uwb_frame.size(),decoded_uwb));
    SF_CHECK(decoded_uwb.node_id==41&&decoded_uwb.sequence==1&&decoded_uwb.authenticated);
    auto bad_uwb=uwb_frame;bad_uwb[40]^=0x80;
    SF_CHECK(!stageforge::decode_uwb_hardware_frame(bad_uwb.data(),bad_uwb.size(),decoded_uwb));

    stageforge::LeIsoTimingObservation le{41,1,9,1,1'100'000,true};
    std::array<std::uint8_t,stageforge::le_iso_timing_frame_size> le_frame{};
    SF_CHECK(stageforge::encode_le_iso_timing_frame(le,le_frame));
    stageforge::LeIsoTimingObservation decoded_le{};
    SF_CHECK(stageforge::decode_le_iso_timing_frame(le_frame.data(),le_frame.size(),decoded_le));
    SF_CHECK(decoded_le.node_id==41&&decoded_le.event_counter==1&&decoded_le.authenticated);
    auto bad_le=le_frame;bad_le[32]^=1;
    SF_CHECK(!stageforge::decode_le_iso_timing_frame(bad_le.data(),bad_le.size(),decoded_le));

#if defined(__linux__)
    int uwb_pair[2]{-1,-1};int le_pair[2]{-1,-1};
    SF_CHECK(::socketpair(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK,0,uwb_pair)==0);
    SF_CHECK(::socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_NONBLOCK,0,le_pair)==0);
    stageforge::LeUwbHub<4> hub;stageforge::LeUwbHubPolicy policy{};policy.max_end_to_end_ns=30'000'000;
    SF_CHECK(hub.configure(9,policy));
    SF_CHECK(hub.register_node({41,1,stageforge::LeUwbNodeRole::monitor_output,1'000'000,true}));
    stageforge::LeUwbHardwareManager<4> hardware(hub);
    SF_CHECK(hardware.adopt_uwb_fd_for_test(uwb_pair[0]));
    SF_CHECK(hardware.adopt_le_fd_for_test(41,le_pair[0]));

    const auto now=[](){return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count());};
    const auto uwb_now=now();uwb.hub_time_ns=uwb_now;uwb.node_time_ns=uwb_now+100'000;
    SF_CHECK(stageforge::encode_uwb_hardware_frame(uwb,uwb_frame));
    const std::uint8_t garbage[3]{1,2,3};SF_CHECK(::write(uwb_pair[1],garbage,sizeof(garbage))==3);
    SF_CHECK(::write(uwb_pair[1],uwb_frame.data(),17)==17);SF_CHECK(hardware.poll()==0);
    SF_CHECK(::write(uwb_pair[1],uwb_frame.data()+17,uwb_frame.size()-17)==static_cast<ssize_t>(uwb_frame.size()-17));
    SF_CHECK(hardware.poll()==1);
    stageforge::LeUwbNodeStatus node{};SF_CHECK(hub.status(41,node));
    SF_CHECK(node.uwb_sequence==1&&node.clock_offset_ns>90'000);

    const auto le_send_hub=now()-2'000'000;
    le.node_transmit_ns=static_cast<std::uint64_t>(static_cast<std::int64_t>(le_send_hub)+node.clock_offset_ns);
    SF_CHECK(stageforge::encode_le_iso_timing_frame(le,le_frame));
    SF_CHECK(::send(le_pair[1],le_frame.data(),le_frame.size(),0)==static_cast<ssize_t>(le_frame.size()));
    SF_CHECK(hardware.poll()==1);
    const auto hw_status=hardware.status();
    SF_CHECK(hw_status.accepted_uwb_frames==1&&hw_status.accepted_le_frames==1);
    SF_CHECK(hw_status.connected_le_slots==1&&!hw_status.physical_outputs_armed);
    const auto plan=hub.plan(now(),5'000'000'000ULL,9);
    SF_CHECK(plan.ready&&!plan.physical_outputs_armed);
    ::close(uwb_pair[1]);::close(le_pair[1]);
#endif
}

void test_cue_action_graph_expansion() {
    stageforge::CoreCueActionGraph<8> graph;
    std::array<stageforge::CueAction,2> actions{};
    actions[0].type=stageforge::CueActionType::automation;
    actions[0].payload.automation={100,200,0.5F,250};
    actions[0].owner_id=42;
    actions[1].type=stageforge::CueActionType::midi;
    actions[1].offset_ns=10'000'000ULL;
    actions[1].payload.midi={0x90,60,100,1};
    SF_CHECK(graph.define(9,actions.data(),actions.size()));
    std::array<stageforge::ShowEvent,2> expanded{}; std::size_t cursor=0;
    const auto count=graph.expand(9,500,2'000'000'000ULL,[&](const stageforge::ShowEvent& e) noexcept { expanded[cursor++]=e; return true; });
    SF_CHECK(count==2);
    SF_CHECK(expanded[0].type==stageforge::ShowEventType::automation);
    SF_CHECK(expanded[0].owner_id==42);
    SF_CHECK(expanded[0].show_time_ns==2'000'000'000ULL);
    SF_CHECK(expanded[1].type==stageforge::ShowEventType::midi);
    SF_CHECK(expanded[1].show_time_ns==2'010'000'000ULL);
}

void test_runtime_show_generation_hot_swap() {
    stageforge::CoreRuntimeShow show;
    show.begin(10, 0xabc);
    SF_CHECK(show.add_role({1,3}));
    SF_CHECK(show.add_cue({7,0x1234}));
    SF_CHECK(show.add_route({1,2,2,1,true}));
    stageforge::CoreParameterDescriptor d{}; d.target_id=1; d.parameter_id=2; d.minimum=0; d.maximum=1; d.default_value=0.5F;
    SF_CHECK(show.add_parameter(d));
    SF_CHECK(show.queue_publish(1'000));
    SF_CHECK(!show.activate_if_due(999));
    SF_CHECK(show.snapshot().generation==0);
    SF_CHECK(show.activate_if_due(1'000));
    const auto first=show.snapshot();
    SF_CHECK(first.generation==1); SF_CHECK(first.source_revision==10); SF_CHECK(first.role_count==1); SF_CHECK(first.parameter_count==1);
    show.begin(11,0xdef); SF_CHECK(show.add_cue({8,0x5555})); SF_CHECK(show.queue_publish(2'000));
    SF_CHECK(!show.activate_if_due(1'999));
    SF_CHECK(show.snapshot().generation==1);
    SF_CHECK(show.activate_if_due(2'000));
    SF_CHECK(show.snapshot().generation==2);
    SF_CHECK(show.snapshot().source_revision==11);
}

void test_routing_transaction_cycle_detection() {
    stageforge::CoreRoutingState<8> routes;
    SF_CHECK(routes.begin(0));
    SF_CHECK(routes.set({1,2,2,0,true}));
    SF_CHECK(routes.set({2,3,2,0,true}));
    SF_CHECK(routes.validate());
    SF_CHECK(routes.commit());
    SF_CHECK(routes.status().revision==1);
    SF_CHECK(routes.begin(1));
    SF_CHECK(routes.set({3,1,2,0,true}));
    SF_CHECK(!routes.validate());
    SF_CHECK(!routes.commit());
    routes.rollback();
    SF_CHECK(routes.status().revision==1);
}

void test_core_journal_hash_chain() {
    stageforge::CoreJournal<8> journal;
    SF_CHECK(journal.append(stageforge::CoreJournalKind::cue,100,1,7,1));
    SF_CHECK(journal.append(stageforge::CoreJournalKind::automation,110,2,8,2));
    stageforge::CoreJournalRecord a{},b{};
    SF_CHECK(journal.try_pop(a)); SF_CHECK(journal.try_pop(b));
    SF_CHECK(a.sequence==1 && b.sequence==2);
    SF_CHECK(b.previous_hash==a.hash);
    SF_CHECK(b.hash!=0 && b.hash!=a.hash);
}

void test_shadow_prebuffer_contiguous_block_evidence() {
    stageforge::CoreShadowPrebuffer<2> prebuffer;
    SF_CHECK(prebuffer.configure(1, 3, 5, 77));
    SF_CHECK(prebuffer.ingest_block(1,3,5,77,1'000,2'000,48,true));
    SF_CHECK(prebuffer.ingest_block(1,3,5,77,2'000,3'000,48,true));
    stageforge::CoreShadowPrebufferStatus status{};
    SF_CHECK(prebuffer.status(1,status));
    SF_CHECK(status.contiguous_from_show_ns==1'000);
    SF_CHECK(status.buffered_until_show_ns==3'000);
    SF_CHECK(status.rendered_frames==96);
    SF_CHECK(status.rendered_blocks==2);
    SF_CHECK(status.healthy);
    SF_CHECK(!prebuffer.ingest_block(1,3,5,77,4'000,5'000,48,true));
    SF_CHECK(prebuffer.status(1,status));
    SF_CHECK(status.discontinuities==1);
    SF_CHECK(!status.healthy);
    prebuffer.invalidate_revision(6);
    SF_CHECK(prebuffer.status(1,status));
    SF_CHECK(status.buffered_until_show_ns==0);
}

void test_shadow_render_planner_generation_revision_hash() {
    stageforge::CoreShadowRenderPlanner<4> planner;
    stageforge::CoreShadowSource src{}; src.id=1; src.show_revision=5; src.content_hash=77; src.generation=3; src.required=true; src.capable=true; src.asset_ready=true;
    SF_CHECK(planner.declare_source(src));
    SF_CHECK(!planner.report(1,2,5,77,5'000,false));
    SF_CHECK(!planner.report(1,3,4,77,5'000,false));
    SF_CHECK(!planner.report(1,3,5,78,5'000,false));
    SF_CHECK(planner.report(1,3,5,77,5'000,true));
    auto ready=planner.plan(3'000,1'000); SF_CHECK(ready.ready); SF_CHECK(ready.ready_sources==1);
    planner.invalidate_revision(6);
    auto blocked=planner.plan(3'000,1'000); SF_CHECK(!blocked.ready); SF_CHECK(blocked.blocked_sources==1);
}

struct TestShadowRenderer { std::uint64_t calls{0}; bool fail{false}; };
bool render_test_shadow(void* context, std::uint64_t start, std::uint64_t end, std::uint32_t frames) noexcept {
    auto& renderer = *static_cast<TestShadowRenderer*>(context);
    ++renderer.calls;
    return !renderer.fail && end > start && frames > 0;
}

void test_shadow_render_executor_drives_verified_evidence() {
    stageforge::CoreShadowRenderPlanner<2> planner;
    stageforge::CoreShadowPrebuffer<2> prebuffer;
    stageforge::CoreShadowRenderExecutor<2> executor(prebuffer, planner);
    stageforge::CoreShadowSource source{};
    source.id=9; source.generation=4; source.show_revision=7; source.content_hash=88;
    source.required=true; source.capable=true; source.asset_ready=true;
    SF_CHECK(planner.declare_source(source));
    TestShadowRenderer renderer{};
    SF_CHECK(executor.register_source(9,4,7,88,1'000,&render_test_shadow,&renderer));
    SF_CHECK(executor.render_until(9,4'500,1'000,48));
    SF_CHECK(renderer.calls==4);
    const auto plan=planner.plan(3'000,1'500);
    SF_CHECK(plan.ready);
    stageforge::CoreShadowRenderExecutorStatus status{};
    SF_CHECK(executor.status(9,status));
    SF_CHECK(status.next_show_ns==4'500 && status.rendered_blocks==4 && status.rendered_frames==168);
    renderer.fail=true;
    SF_CHECK(!executor.render_until(9,5'500,1'000,48));
    SF_CHECK(executor.status(9,status));
    SF_CHECK(!status.healthy && status.failures==1);
    SF_CHECK(!planner.plan(3'000,1'500).ready);
}

void test_planned_handoff_boundary_and_epoch_fencing() {
    stageforge::CorePlannedHandoff handoff;
    SF_CHECK(handoff.prepare(42,7,8,10'000,false));
    SF_CHECK(!handoff.prepare(43,7,8,10'000,false));
    SF_CHECK(!handoff.acknowledge_target(42,false));
    SF_CHECK(handoff.acknowledge_target(42,true));
    SF_CHECK(!handoff.commit(42,7,8,9'999));
    SF_CHECK(!handoff.commit(42,6,8,10'000));
    SF_CHECK(!handoff.commit(42,7,9,10'000));
    SF_CHECK(handoff.commit(42,7,8,10'000));
    const auto committed=handoff.status();
    SF_CHECK(committed.authority_committed);
    SF_CHECK(!committed.physical_outputs_armed);
    SF_CHECK(committed.commits==1);

    stageforge::CorePlannedHandoff degraded;
    SF_CHECK(degraded.prepare(50,8,9,20'000,true));
    SF_CHECK(degraded.acknowledge_target(50,false));
    SF_CHECK(degraded.abort(50));
    SF_CHECK(degraded.status().state==stageforge::CorePlannedHandoffState::aborted);
}

void test_core_resource_planner_priority_and_degradation() {
    const stageforge::CoreResourceRequest requests[]{
        {SF_PRIORITY_CRITICAL, 24.0F, true, true, false, 0.35F},
        {SF_PRIORITY_SHOW, 12.0F, true, true, true, 0.35F},
        {SF_PRIORITY_PRODUCTION, 8.0F, true, true, true, 0.35F},
        {SF_PRIORITY_VISUAL, 30.0F, true, true, true, 0.25F},
        {SF_PRIORITY_BACKGROUND, 20.0F, true, false, true, 0.35F},
    };
    stageforge::CoreResourceDecision decisions[5]{};
    const auto full = stageforge::CoreResourcePlanner::plan(50.0F, stageforge::CoreOperatingMode::full, requests, decisions);
    SF_CHECK(decisions[0].action == stageforge::CoreResourceAction::full);
    SF_CHECK(decisions[1].action == stageforge::CoreResourceAction::full);
    SF_CHECK(decisions[2].action == stageforge::CoreResourceAction::full);
    SF_CHECK(decisions[3].action == stageforge::CoreResourceAction::suspended);
    SF_CHECK(decisions[4].action == stageforge::CoreResourceAction::suspended);
    SF_CHECK(full.used_percent <= 50.0F);

    stageforge::CoreResourceDecision safe_decisions[5]{};
    const auto safe = stageforge::CoreResourcePlanner::plan(30.0F, stageforge::CoreOperatingMode::safe_show, requests, safe_decisions);
    SF_CHECK(safe_decisions[0].action == stageforge::CoreResourceAction::full);
    SF_CHECK(safe_decisions[1].action == stageforge::CoreResourceAction::degraded);
    SF_CHECK(safe_decisions[3].action == stageforge::CoreResourceAction::suspended);
    SF_CHECK(safe_decisions[4].action == stageforge::CoreResourceAction::suspended);
    SF_CHECK(safe.used_percent <= 30.0F);

    stageforge::CoreResourceDecision audio_decisions[5]{};
    const auto audio_plan = stageforge::CoreResourcePlanner::plan(100.0F, stageforge::CoreOperatingMode::audio_only, requests, audio_decisions);
    SF_CHECK(audio_plan.used_percent <= 100.0F);
    SF_CHECK(audio_decisions[0].action == stageforge::CoreResourceAction::full);
    SF_CHECK(audio_decisions[1].action == stageforge::CoreResourceAction::suspended);
    SF_CHECK(audio_decisions[2].action == stageforge::CoreResourceAction::suspended);
}

void test_transport_lock_free_snapshot_publication() {
    stageforge::TransportClock clock(48000.0, 120.0);
    clock.play();
    std::atomic<bool> done{false};
    std::thread writer([&] {
        for (int i = 0; i < 2000; ++i) {
            clock.set_bpm(90.0 + static_cast<double>(i % 100));
            if ((i % 17) == 0) clock.set_clock_rate(1.0001);
            if ((i % 19) == 0) clock.set_clock_rate(1.0);
        }
        done.store(true, std::memory_order_release);
    });
    std::uint64_t last_monotonic = 0;
    std::size_t reads = 0;
    while (!done.load(std::memory_order_acquire) || reads < 4000) {
        const auto value = clock.snapshot();
        SF_CHECK(value.monotonic_ns >= last_monotonic);
        SF_CHECK(value.bpm >= 30.0 && value.bpm <= 300.0);
        SF_CHECK(value.show_seconds >= 0.0);
        last_monotonic = value.monotonic_ns;
        ++reads;
    }
    writer.join();
    clock.pause();
}

void test_core_command_dedup_is_namespaced_by_source_domain() {
    stageforge::CoreControlState core(48000.0, 120.0);
    const auto direct = core.mutate_transport(5001, stageforge::core_any_revision, stageforge::CoreTransportAction::set_bpm, 121.0);
    SF_CHECK(direct.status == stageforge::CoreMutationStatus::applied);
    const auto show_event = core.mutate_transport_scoped(
        stageforge::CoreCommandDomain::show_event, 5001, stageforge::core_any_revision,
        stageforge::CoreTransportAction::set_bpm, 135.0);
    SF_CHECK(show_event.status == stageforge::CoreMutationStatus::applied);
    SF_CHECK(std::abs(core.transport().snapshot().bpm - 135.0) < 0.001);
    const auto duplicate = core.mutate_transport_scoped(
        stageforge::CoreCommandDomain::show_event, 5001, stageforge::core_any_revision,
        stageforge::CoreTransportAction::set_bpm, 90.0);
    SF_CHECK(duplicate.status == stageforge::CoreMutationStatus::duplicate);
    SF_CHECK(std::abs(core.transport().snapshot().bpm - 135.0) < 0.001);
}

void test_core_control_command_dedup_and_conflicts() {
    stageforge::CoreControlState core(48000.0, 120.0);
    auto first = core.mutate_transport(1001, 1, stageforge::CoreTransportAction::set_bpm, 132.0);
    SF_CHECK(first.status == stageforge::CoreMutationStatus::applied);
    SF_CHECK(first.resource_revision == 2);
    SF_CHECK(std::abs(core.transport().snapshot().bpm - 132.0) < 0.001);

    auto duplicate = core.mutate_transport(1001, 1, stageforge::CoreTransportAction::set_bpm, 90.0);
    SF_CHECK(duplicate.status == stageforge::CoreMutationStatus::duplicate);
    SF_CHECK(std::abs(core.transport().snapshot().bpm - 132.0) < 0.001);

    auto conflict = core.mutate_transport(1002, 1, stageforge::CoreTransportAction::seek_seconds, 10.0);
    SF_CHECK(conflict.status == stageforge::CoreMutationStatus::conflict);
    SF_CHECK(core.transport().snapshot().show_seconds < 1.0);

    auto monitor = core.mutate_monitor(2001, 1, "alex", "click", 17.0);
    SF_CHECK(monitor.status == stageforge::CoreMutationStatus::applied);
    SF_CHECK(monitor.resource_revision == 2);
    const auto* bus = core.monitors().find("alex");
    SF_CHECK(bus != nullptr);
    SF_CHECK(std::abs(bus->level(stageforge::MonitorChannel::click) - 17.0F) < 0.001F);

    auto monitor_conflict = core.mutate_monitor(2002, 1, "alex", "click", 55.0);
    SF_CHECK(monitor_conflict.status == stageforge::CoreMutationStatus::conflict);
    SF_CHECK(std::abs(bus->level(stageforge::MonitorChannel::click) - 17.0F) < 0.001F);

    const auto metrics = core.metrics();
    SF_CHECK(metrics.applied_commands == 2);
    SF_CHECK(metrics.duplicate_commands == 1);
    SF_CHECK(metrics.conflicts == 2);
}

void test_core_snapshot_atomic_apply_and_stale_rejection() {
    stageforge::CoreControlState core(48000.0, 120.0);
    SF_CHECK(core.begin_snapshot(42));
    SF_CHECK(core.stage_transport(128.0, 12.5, false));
    stageforge::MonitorBusSnapshot monitor{};
    monitor.master = 81.0F;
    monitor.levels[static_cast<std::size_t>(stageforge::MonitorChannel::self)] = 91.0F;
    monitor.levels[static_cast<std::size_t>(stageforge::MonitorChannel::click)] = 22.0F;
    monitor.muted = true;
    SF_CHECK(core.stage_monitor("jordan", monitor));

    // Staged state is invisible before commit.
    SF_CHECK(std::abs(core.transport().snapshot().bpm - 120.0) < 0.001);
    SF_CHECK(core.monitors().find("jordan") == nullptr);

    const auto committed = core.commit_snapshot();
    SF_CHECK(committed.status == stageforge::CoreMutationStatus::applied);
    SF_CHECK(committed.external_revision == 42);
    SF_CHECK(std::abs(core.transport().snapshot().bpm - 128.0) < 0.001);
    SF_CHECK(std::abs(core.transport().snapshot().show_seconds - 12.5) < 0.05);
    const auto* bus = core.monitors().find("jordan");
    SF_CHECK(bus != nullptr);
    SF_CHECK(bus->muted());
    SF_CHECK(std::abs(bus->master() - 81.0F) < 0.001F);
    SF_CHECK(std::abs(bus->level(stageforge::MonitorChannel::click) - 22.0F) < 0.001F);

    SF_CHECK(!core.begin_snapshot(41));
    SF_CHECK(core.begin_snapshot(42));
    const auto repeated = core.commit_snapshot();
    SF_CHECK(repeated.status == stageforge::CoreMutationStatus::duplicate);

    SF_CHECK(core.begin_snapshot(43));
    SF_CHECK(core.stage_transport(140.0, 20.0, true));
    core.abort_snapshot();
    SF_CHECK(std::abs(core.transport().snapshot().bpm - 128.0) < 0.001);
    SF_CHECK(!core.transport().running());

    const auto metrics = core.metrics();
    SF_CHECK(metrics.snapshot_commits == 1);
    SF_CHECK(metrics.external_revision == 42);
}

void test_audio_device_lifecycle() {
    stageforge::NullAudioDevice device;
    SF_CHECK(device.status().state == stageforge::AudioDeviceState::closed);
    SF_CHECK(device.open({48000.0, 2, 2, 128}));
    SF_CHECK(device.start());
    SF_CHECK(device.status().state == stageforge::AudioDeviceState::running);
    device.stop();
    SF_CHECK(device.status().state == stageforge::AudioDeviceState::open);
    device.close();
    SF_CHECK(device.status().state == stageforge::AudioDeviceState::closed);
    SF_CHECK(!device.open({0.0, 2, 2, 128}));
}

void test_user_profile_layers_and_interoperability_handshake() {
    stageforge::UserProfileCustomization<8> profile;
    SF_CHECK(profile.configure(77, 12));
    SF_CHECK(profile.set({1, 10, stageforge::ProfileLayer::base, stageforge::ProfileValueType::scalar, 1, 0, 0.25, 0}));
    SF_CHECK(profile.set({1, 10, stageforge::ProfileLayer::user, stageforge::ProfileValueType::scalar, 2, 0, 0.75, 0}));
    stageforge::ProfilePreference resolved{};
    SF_CHECK(profile.resolve(1, 10, resolved));
    SF_CHECK(resolved.layer == stageforge::ProfileLayer::user);
    SF_CHECK(std::abs(resolved.scalar_value - 0.75) < 0.0001);
    SF_CHECK(!profile.set({1, 10, stageforge::ProfileLayer::user, stageforge::ProfileValueType::scalar, 2, 0, 0.5, 0}));
    SF_CHECK(profile.set({1, 10, stageforge::ProfileLayer::session, stageforge::ProfileValueType::scalar, 3, 0, 0.9, 0}));
    SF_CHECK(profile.resolve(1, 10, resolved) && resolved.layer == stageforge::ProfileLayer::session);
    SF_CHECK(profile.clear_layer(stageforge::ProfileLayer::session) == 1);
    SF_CHECK(profile.resolve(1, 10, resolved) && resolved.layer == stageforge::ProfileLayer::user);
    SF_CHECK(!profile.configure(77, 11));
    SF_CHECK(!profile.status().physical_outputs_armed);

    using Offer = stageforge::HandshakeOffer<8>;
    stageforge::InteroperabilityHandshake<8, 4> handshake;
    Offer local{};local.participant_id=1;local.protocol_min=1;local.protocol_max=3;local.profile_schema_min=1;local.profile_schema_max=2;
    local.capabilities[0]={100,true};local.capabilities[1]={200,false};local.capability_count=2;
    SF_CHECK(handshake.configure_local(local));
    SF_CHECK(handshake.add_adapter({300,200,95}));
    Offer remote{};remote.participant_id=2;remote.protocol_min=2;remote.protocol_max=4;remote.profile_schema_min=1;remote.profile_schema_max=1;
    remote.capabilities[0]={100,true};remote.capabilities[1]={300,true};remote.capabilities[2]={999,false};remote.capability_count=3;
    auto plan=handshake.negotiate(remote);
    SF_CHECK(plan.compatible);SF_CHECK(plan.protocol_version==3);SF_CHECK(plan.profile_schema_version==1);
    SF_CHECK(plan.direct_capabilities==1);SF_CHECK(plan.translated_capabilities==1);SF_CHECK(plan.preserved_unknown_capabilities==1);
    SF_CHECK(plan.minimum_adapter_quality==95);SF_CHECK(plan.unknown_preservation);SF_CHECK(!plan.physical_outputs_armed);
    remote.preserves_unknown=false;plan=handshake.negotiate(remote);SF_CHECK(!plan.compatible);
    remote.preserves_unknown=true;remote.capabilities[1].id=301;plan=handshake.negotiate(remote);SF_CHECK(!plan.compatible);SF_CHECK(plan.missing_required==1);
}

void test_authenticated_session_and_profile_projection() {
    stageforge::ProfileProjectionCandidate candidates[4]{};
    candidates[0]={{10,20,stageforge::ProfileLayer::user,stageforge::ProfileValueType::scalar,1,0,0.8,0},true};
    candidates[1]={{10,20,stageforge::ProfileLayer::venue,stageforge::ProfileValueType::scalar,2,0,0.3,0},true};
    candidates[2]={{11,21,stageforge::ProfileLayer::user,stageforge::ProfileValueType::token,1,0,0.0,100},false};
    candidates[3]={{11,21,stageforge::ProfileLayer::venue,stageforge::ProfileValueType::token,2,0,0.0,200},false};
    stageforge::ProfileProjector<8> projector;const auto projection=projector.project(candidates,4);
    SF_CHECK(projection.count==2);SF_CHECK(projection.entries[0].preference.scalar_value==0.8);
    SF_CHECK(projection.entries[1].preference.token_value==200);SF_CHECK(projection.entries[1].consent_required);
    SF_CHECK(projection.consent_required==1);SF_CHECK(projection.digest!=0);SF_CHECK(!projection.physical_outputs_armed);

    stageforge::AuthenticatedInteropSession session;
    SF_CHECK(session.offer(1,2,3,9,4,2000));
    SF_CHECK(session.authenticate(true,1000,9,3));
    SF_CHECK(session.negotiate(true,2,1,7,8));
    SF_CHECK(session.consent(true,projection.digest));
    SF_CHECK(session.activate(1500,9,7,8));
    SF_CHECK(session.status().state==stageforge::InteropSessionState::active);
    SF_CHECK(!session.status().physical_outputs_armed);
    session.invalidate_if_changed(10,7,8);SF_CHECK(session.status().state==stageforge::InteropSessionState::expired);

    stageforge::AuthenticatedInteropSession replay;
    SF_CHECK(replay.offer(2,3,4,9,4,2000));
    SF_CHECK(!replay.authenticate(true,1000,9,4));
    SF_CHECK(replay.status().state==stageforge::InteropSessionState::expired);
}

void test_session_channel_scope_replay_rotation_and_restore() {
    stageforge::SessionChannelGuard<4> channel;const std::uint64_t capabilities[]{100,200};
    SF_CHECK(channel.configure(1,2,1,capabilities,2));stageforge::SessionFrameHeader outbound{};
    SF_CHECK(channel.next_outbound(100,64,outbound));SF_CHECK(outbound.sequence==1&&outbound.key_epoch==1);
    SF_CHECK(!channel.next_outbound(999,1,outbound));
    stageforge::SessionFrameHeader inbound{1,2,1,1,100,32};SF_CHECK(channel.authorize_inbound(inbound,true));
    SF_CHECK(!channel.authorize_inbound(inbound,true));
    SF_CHECK(channel.rotate(2,2));
    inbound.key_epoch=1;inbound.sequence=2;SF_CHECK(channel.authorize_inbound(inbound,true));
    inbound.key_epoch=1;inbound.sequence=4;SF_CHECK(!channel.authorize_inbound(inbound,true));
    inbound.key_epoch=2;inbound.sequence=4;SF_CHECK(channel.authorize_inbound(inbound,true));
    SF_CHECK(!channel.restore_sequences(2,0,0,true));SF_CHECK(channel.restore_sequences(3,10,10,true));
    SF_CHECK(channel.status().key_epoch==3);SF_CHECK(!channel.status().confidential);SF_CHECK(!channel.status().physical_outputs_armed);
}

} // namespace

void test_recording_disarm_stabilizes_tail_and_rearm_fences_old_generation() {
    using Queue = stageforge::DawRecordingQueue<1, 256, 64>;
    Queue queue;
    for (int round = 0; round < 100; ++round) {
        SF_CHECK(queue.arm(0, true));
        const auto generation = queue.generation(0);
        std::atomic<bool> done{false};
        std::atomic<unsigned> attempts{0};
        std::thread writer([&] {
            Queue::Block block{};
            block.generation = generation; block.frames = 256;
            while (!done.load()) {
                ++block.sequence;
                (void)queue.submit(0, block);
                attempts.fetch_add(1);
            }
        });
        while (attempts.load() < 1) std::this_thread::yield();
        queue.disarm(0);
        const auto submitted = queue.status(0).submitted;
        const auto before = attempts.load();
        while (attempts.load() < before + 100) std::this_thread::yield();
        SF_CHECK(queue.status(0).submitted == submitted);
        Queue::Block out{};
        while (queue.pop(0, out)) SF_CHECK(out.generation == generation);
        SF_CHECK(queue.status(0).queued == 0);
        done.store(true); writer.join();
        SF_CHECK(queue.arm(0, true));
        Queue::Block stale{}; stale.frames = 256; stale.generation = generation;
        SF_CHECK(!queue.submit(0, stale));
        stale.generation = queue.generation(0);
        SF_CHECK(queue.submit(0, stale));
        queue.disarm(0);
        SF_CHECK(queue.pop(0, out));
        SF_CHECK(out.generation == stale.generation);
    }
}

int main() {
    {
        stageforge::RealtimeAudit outer, inner;
        {
            stageforge::RealtimeQualificationScope first(&outer);
            stageforge::note_realtime_allocation(8);
            {
                stageforge::RealtimeQualificationScope second(&inner);
                stageforge::note_realtime_allocation(16);
            }
            stageforge::note_realtime_allocation(32);
        }
        stageforge::note_realtime_allocation(64);
        std::atomic<bool> ready{false}, done{false};
        std::thread worker([&]{
            while(!ready.load())std::this_thread::yield();
            stageforge::note_realtime_allocation(128);
            stageforge::RealtimeQualificationScope scope(&inner);
            stageforge::note_realtime_lock_attempt();
            done.store(true);
        });
        {
            stageforge::RealtimeQualificationScope scope(&outer);
            ready.store(true);
            while(!done.load())std::this_thread::yield();
        }
        worker.join();
#ifdef STAGEFORGE_RT_QUALIFICATION
        SF_CHECK(outer.status().allocation_attempts==2&&outer.status().allocated_bytes==40);
        SF_CHECK(inner.status().allocation_attempts==1&&inner.status().allocated_bytes==16);
        SF_CHECK(inner.status().lock_attempts==1&&outer.status().lock_attempts==0);
#else
        SF_CHECK(outer.status().allocation_attempts==0&&inner.status().allocation_attempts==0);
        SF_CHECK(inner.status().lock_attempts==0);
#endif
    }
    test_lighting_ingress_audit_is_bounded_and_unarmed();
    test_capture_ingress_audit_is_bounded_and_unarmed();
    test_shared_capture_ingress_preserves_samples_generation_and_discontinuities();
    test_recording_disarm_stabilizes_tail_and_rearm_fences_old_generation();
    test_sampler_voice_engine_polyphony_steal_choke_and_loop();
    test_midi_mapped_actions_become_authoritative_show_events();
    test_midi_learn_router_quantizes_maps_and_key_syncs();
    test_plugin_delay_compensation_aligns_parallel_paths();
    test_plugin_delay_graph_swaps_complete_generations();
    test_effect_delay_transaction_commits_and_rolls_back_one_generation();
    test_independent_polyphonic_streaming_voices_are_generation_fenced();
    test_realtime_audit_sheds_and_recovers_optional_work();
    test_realtime_qualification_detects_allocation_and_lock_attempts();
    test_daw_playback_prefetch_seek_loop_and_underrun();
    test_daw_playback_arbitrary_short_loop_wraps_multiple_times_per_block();
    test_daw_multitrack_recording_queue_fences_arm_and_tracks_gaps();
    test_daw_stream_renderer_bounded_long_render_and_cancel();
    test_session_channel_scope_replay_rotation_and_restore();
    test_authenticated_session_and_profile_projection();
    test_user_profile_layers_and_interoperability_handshake();
    test_audio_graph_atomic_route_transaction();
    test_core_parameter_registry_and_plugin_bridge();
    test_format_neutral_effect_chain_processing_and_failure_bypass();
    test_effect_chain_runs_before_output_limiter();
    test_pcm_integer_and_multichannel_conversion();
    test_alsa_integer_multichannel_stream_when_available();
    test_canonical_192khz_rate_conversion();
    test_le_uwb_hub_fenced_group_sync();
    test_le_uwb_hardware_frames_and_nonblocking_loopback();
    test_cue_action_graph_expansion();
    test_runtime_show_generation_hot_swap();
    test_routing_transaction_cycle_detection();
    test_core_journal_hash_chain();
    test_shadow_prebuffer_contiguous_block_evidence();
    test_shadow_render_planner_generation_revision_hash();
    test_shadow_render_executor_drives_verified_evidence();
    test_planned_handoff_boundary_and_epoch_fencing();
    test_show_execution_loop_automatic_owner_and_cue_state();
    test_show_event_timeline_order_replay_and_late_policy();
    test_show_event_cancel_and_timeline_capacity();
    test_core_automation_points_ramps_and_ownership();
    test_show_execution_loop_owns_automation_state();
    test_core_resource_planner_priority_and_degradation();
    test_transport_lock_free_snapshot_publication();
    test_core_command_dedup_is_namespaced_by_source_domain();
    test_core_control_command_dedup_and_conflicts();
    test_core_snapshot_atomic_apply_and_stale_rejection();
    test_transport();
    test_clock_discipline_holdover();
    test_spsc_queue();
    test_monitor_bus_isolation();
    test_midi_scheduler();
    test_midi_byte_parser();
    test_midi_input_queue_injection();
    test_monitor_mixer();
    test_latency_resolver();
    test_lighting_scheduler_and_artnet();
    test_sacn_packet_and_explicit_arm();
    test_audio_device_discovery();
    test_audio_graph_routing_and_limiter();
    test_monitor_graph_router();
    test_artnet_udp_explicit_arm();
    test_alsa_runtime_stream_when_available();
    test_audio_input_ring();
    test_audio_fanout_ring();
    test_adaptive_drift_controller_and_resampler();
    test_captured_input_routes_to_player_monitor_source();
    test_alsa_runtime_capture_when_available();
    test_transport_clock_rate_discipline();
    test_authority_fenced_transport_discipline_and_midi_clock();
    test_audio_device_lifecycle();
    test_notation_quantizer();
    return 0;
}
