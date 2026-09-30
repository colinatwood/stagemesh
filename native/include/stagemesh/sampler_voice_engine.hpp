#pragma once

#include "stagemesh/spsc_queue.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace stagemesh {

struct SamplerSampleDescriptor {
    std::uint64_t sample_id{0};
    const float* left{nullptr};
    const float* right{nullptr};
    std::uint32_t frames{0};
    std::uint32_t loop_begin{0};
    std::uint32_t loop_end{0};
    std::uint16_t loop_crossfade_frames{0};
    std::uint8_t choke_group{0};
    bool looped{false};
};

enum class SamplerCommandKind : std::uint8_t { trigger=0, stop_sample=1, stop_all=2 };

struct SamplerCommand {
    SamplerCommandKind kind{SamplerCommandKind::trigger};
    std::uint64_t event_id{0};
    std::uint64_t sample_id{0};
    float velocity{1.0F};
    std::uint8_t note{60};
};

struct SamplerVoiceStatus {
    std::uint32_t samples{0};
    std::uint32_t active_voices{0};
    std::uint32_t pending_voices{0};
    std::uint32_t queued{0};
    std::uint64_t submitted{0};
    std::uint64_t rendered_frames{0};
    std::uint64_t completed_voices{0};
    std::uint64_t stolen_voices{0};
    std::uint64_t choked_voices{0};
    std::uint64_t rejected_commands{0};
    std::uint64_t queue_overflows{0};
    bool physical_outputs_armed{false};
};

// Fixed-capacity polyphonic sampler. Sample memory is immutable and owned by
// the registering adapter for the engine lifetime. The Show-Time owner is the
// single command producer; the audio callback is the sole voice-state owner.
template<std::size_t VoiceCapacity=64,std::size_t SampleCapacity=32,std::size_t CommandCapacity=257>
class SamplerVoiceEngine final {
    static_assert(VoiceCapacity>=1);
    static_assert(CommandCapacity>=2);
public:
    [[nodiscard]] bool register_sample(const SamplerSampleDescriptor& descriptor) noexcept {
        if(!valid(descriptor))return false;
        for(const auto& slot:samples_)if(slot.ready.load(std::memory_order_acquire)&&slot.descriptor.sample_id==descriptor.sample_id)return false;
        for(auto& slot:samples_)if(!slot.ready.load(std::memory_order_acquire)){
            slot.descriptor=descriptor;slot.ready.store(true,std::memory_order_release);sample_count_.fetch_add(1,std::memory_order_relaxed);return true;
        }
        return false;
    }

    [[nodiscard]] bool submit(const SamplerCommand& command) noexcept {
        submitted_.fetch_add(1,std::memory_order_relaxed);
        if(command.event_id==0||(command.kind!=SamplerCommandKind::stop_all&&command.sample_id==0)||!std::isfinite(command.velocity)){
            rejected_.fetch_add(1,std::memory_order_relaxed);return false;
        }
        if(!commands_.try_push(command)){overflows_.fetch_add(1,std::memory_order_relaxed);return false;}
        return true;
    }

    void render(float* left,float* right,std::uint32_t frames) noexcept {
        if(!left||!right||frames==0)return;
        std::fill_n(left,frames,0.0F);std::fill_n(right,frames,0.0F);drain_commands();
        for(std::uint32_t frame=0;frame<frames;++frame){
            float mixed_left=0.0F,mixed_right=0.0F;
            for(auto& voice:voices_){
                if(!voice.active)continue;
                const auto* sample=find_sample(voice.sample_id);if(!sample){finish(voice);continue;}
                const auto end=sample->looped?sample->loop_end:sample->frames;
                if(voice.position>=end){
                    if(sample->looped)voice.position=sample->loop_begin+(voice.position-end);
                    else{finish(voice);continue;}
                }
                float sl=sample->left[voice.position],sr=sample->right?sample->right[voice.position]:sl;
                const auto crossfade=sample->looped?std::min<std::uint32_t>(sample->loop_crossfade_frames,(sample->loop_end-sample->loop_begin)/2):0;
                if(crossfade&&voice.position>=sample->loop_end-crossfade){
                    const auto offset=voice.position-(sample->loop_end-crossfade);const float mix=static_cast<float>(offset)/static_cast<float>(crossfade);
                    const auto alternate=sample->loop_begin+offset;const float al=sample->left[alternate],ar=sample->right?sample->right[alternate]:al;
                    const float out_gain=std::sqrt(std::max(0.0F,1.0F-mix)),in_gain=std::sqrt(std::max(0.0F,mix));sl=sl*out_gain+al*in_gain;sr=sr*out_gain+ar*in_gain;
                }
                float envelope=voice.age<attack_frames?static_cast<float>(voice.age+1)/static_cast<float>(attack_frames):1.0F;
                if(voice.releasing)envelope*=static_cast<float>(voice.release_remaining)/static_cast<float>(release_frames);
                mixed_left+=sl*voice.gain*envelope;mixed_right+=sr*voice.gain*envelope;++voice.position;++voice.age;
                if(voice.releasing&&voice.release_remaining>0&&--voice.release_remaining==0){
                    if(voice.pending){const auto pending=voice.pending_command;start(voice,pending);}
                    else finish(voice);
                }
            }
            left[frame]=mixed_left;right[frame]=mixed_right;
        }
        rendered_frames_.fetch_add(frames,std::memory_order_relaxed);publish_counts();
    }

    [[nodiscard]] SamplerVoiceStatus status()const noexcept{return{
        sample_count_.load(std::memory_order_relaxed),active_count_.load(std::memory_order_acquire),pending_count_.load(std::memory_order_acquire),static_cast<std::uint32_t>(commands_.size_approx()),
        submitted_.load(std::memory_order_relaxed),rendered_frames_.load(std::memory_order_relaxed),completed_.load(std::memory_order_relaxed),
        stolen_.load(std::memory_order_relaxed),choked_.load(std::memory_order_relaxed),rejected_.load(std::memory_order_relaxed),overflows_.load(std::memory_order_relaxed),false};}

private:
    struct SampleSlot{SamplerSampleDescriptor descriptor{};std::atomic<bool>ready{false};};
    struct Voice{std::uint64_t sample_id{0},sequence{0};std::uint32_t position{0},age{0},release_remaining{0};float gain{0};std::uint8_t choke_group{0},note{60};bool active{false},releasing{false},pending{false};SamplerCommand pending_command{};};
    static constexpr std::uint32_t attack_frames=32,release_frames=64;
    [[nodiscard]] static bool valid(const SamplerSampleDescriptor& d)noexcept{return d.sample_id&&d.left&&d.frames&&d.loop_begin<d.frames&&d.loop_end<=d.frames&&(!d.looped||d.loop_end>d.loop_begin);}
    [[nodiscard]] const SamplerSampleDescriptor* find_sample(std::uint64_t id)const noexcept{for(const auto&slot:samples_)if(slot.ready.load(std::memory_order_acquire)&&slot.descriptor.sample_id==id)return&slot.descriptor;return nullptr;}
    void begin_release(Voice&v)noexcept{if(v.active&&!v.releasing){v.releasing=true;v.release_remaining=release_frames;}}
    void finish(Voice&v)noexcept{v.active=false;v.releasing=false;v.pending=false;v.release_remaining=0;completed_.fetch_add(1,std::memory_order_relaxed);}
    void start(Voice&v,const SamplerCommand&command)noexcept{const auto*sample=find_sample(command.sample_id);if(!sample){v.active=false;rejected_.fetch_add(1,std::memory_order_relaxed);return;}v.sample_id=command.sample_id;v.sequence=next_sequence_++;v.position=0;v.age=0;v.release_remaining=0;v.gain=std::clamp(command.velocity,0.0F,1.0F);v.choke_group=sample->choke_group;v.note=command.note;v.active=true;v.releasing=false;v.pending=false;}
    void trigger(const SamplerCommand&command)noexcept{
        const auto*sample=find_sample(command.sample_id);if(!sample){rejected_.fetch_add(1,std::memory_order_relaxed);return;}
        if(sample->choke_group)for(auto&voice:voices_)if(voice.active&&voice.choke_group==sample->choke_group){begin_release(voice);choked_.fetch_add(1,std::memory_order_relaxed);}
        for(auto&voice:voices_)if(!voice.active){start(voice,command);return;}
        auto*oldest=&voices_[0];for(auto&voice:voices_)if(voice.sequence<oldest->sequence)oldest=&voice;
        oldest->pending=true;oldest->pending_command=command;begin_release(*oldest);stolen_.fetch_add(1,std::memory_order_relaxed);
    }
    void drain_commands()noexcept{SamplerCommand command{};while(commands_.try_pop(command)){if(command.kind==SamplerCommandKind::trigger)trigger(command);else if(command.kind==SamplerCommandKind::stop_all){for(auto&voice:voices_)begin_release(voice);}else for(auto&voice:voices_)if(voice.active&&voice.sample_id==command.sample_id)begin_release(voice);}}
    void publish_counts()noexcept{std::uint32_t active=0,pending=0;for(const auto&voice:voices_){if(voice.active)++active;if(voice.pending)++pending;}active_count_.store(active,std::memory_order_release);pending_count_.store(pending,std::memory_order_release);}
    std::array<SampleSlot,SampleCapacity>samples_{};std::array<Voice,VoiceCapacity>voices_{};SpscQueue<SamplerCommand,CommandCapacity>commands_{};
    std::uint64_t next_sequence_{1};std::atomic<std::uint32_t>sample_count_{0},active_count_{0},pending_count_{0};
    std::atomic<std::uint64_t>submitted_{0},rendered_frames_{0},completed_{0},stolen_{0},choked_{0},rejected_{0},overflows_{0};
};

static_assert(std::is_trivially_copyable_v<SamplerCommand>);

} // namespace stagemesh
