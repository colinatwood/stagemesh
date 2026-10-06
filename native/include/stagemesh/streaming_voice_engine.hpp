#pragma once
#include "stagemesh/spsc_queue.hpp"
#include <array>
#include <atomic>
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace stagemesh {

template<std::size_t BlockFrames=256>
struct StreamingVoiceBlock {
    std::uint64_t generation{0},sequence{0};
    std::uint32_t frames{0};
    bool terminal{false};
    std::array<float,BlockFrames>left{},right{};
};

enum class StreamingVoiceCommandKind:std::uint8_t{start=0,stop=1,stop_all=2};
struct StreamingVoiceCommand{StreamingVoiceCommandKind kind{StreamingVoiceCommandKind::start};std::uint16_t slot{0};std::uint64_t generation{0};float gain{1.0F};bool loop{false};};
struct StreamingVoiceEngineStatus{
    std::uint32_t active_voices{0},queued_blocks{0};
    std::uint64_t active_mask{0},starts{0},stops{0},rendered_frames{0},starved_blocks{0},stale_blocks{0},discontinuities{0},completed_voices{0},queue_overflows{0};
    bool disk_io_in_audio_callback{false},physical_outputs_armed{false};
};

// Each voice has an independent SPSC feed. Service threads decode media into
// fixed blocks; the audio callback only drains commands/blocks and mixes.
template<std::size_t Voices=16,std::size_t BlockFrames=256,std::size_t BlocksPerVoice=9,std::size_t CommandCapacity=65>
class StreamingVoiceEngine final{
    static_assert(Voices>0&&BlockFrames>0&&BlocksPerVoice>1&&CommandCapacity>1);
public:
    using Block=StreamingVoiceBlock<BlockFrames>;
    [[nodiscard]]bool start(std::size_t slot,std::uint64_t generation,float gain,bool loop)noexcept{
        if(slot>=Voices||generation==0||!std::isfinite(gain)||gain<0.0F||gain>1.0F)return false;
        if(!commands_.try_push({StreamingVoiceCommandKind::start,static_cast<std::uint16_t>(slot),generation,gain,loop})){overflows_.fetch_add(1);return false;}return true;
    }
    [[nodiscard]]bool stop(std::size_t slot,std::uint64_t generation)noexcept{
        if(slot>=Voices||generation==0)return false;
        if(!commands_.try_push({StreamingVoiceCommandKind::stop,static_cast<std::uint16_t>(slot),generation,0,false})){overflows_.fetch_add(1);return false;}return true;
    }
    [[nodiscard]]bool stop_all()noexcept{return commands_.try_push({StreamingVoiceCommandKind::stop_all,0,0,0,false});}
    [[nodiscard]]bool push(std::size_t slot,const Block&block)noexcept{
        if(slot>=Voices||block.generation==0||block.sequence==0||block.frames==0||block.frames>BlockFrames)return false;
        if(!feeds_[slot].try_push(block)){overflows_.fetch_add(1);return false;}return true;
    }
    void render(float*left,float*right,std::uint32_t frames)noexcept{
        if(!left||!right||frames==0)return;
        std::fill_n(left,frames,0.0F);std::fill_n(right,frames,0.0F);drain_commands();
        for(auto&voice:voices_)voice.starved_this_block=false;
        for(std::uint32_t frame=0;frame<frames;++frame)for(std::size_t slot=0;slot<Voices;++slot){auto&voice=voices_[slot];if(!voice.active)continue;
            if(!voice.has_block&&!load(slot,voice)){if(!voice.starved_this_block){voice.starved_this_block=true;starved_.fetch_add(1);}continue;}
            left[frame]+=voice.block.left[voice.offset]*voice.gain;right[frame]+=voice.block.right[voice.offset]*voice.gain;++voice.offset;
            if(voice.offset==voice.block.frames){const bool terminal=voice.block.terminal;voice.has_block=false;voice.offset=0;if(terminal&&!voice.loop){voice.active=false;completed_.fetch_add(1);}}
        }
        rendered_.fetch_add(frames);publish();
    }
    [[nodiscard]]StreamingVoiceEngineStatus status()const noexcept{
        std::uint32_t queued=0;for(const auto&feed:feeds_)queued+=static_cast<std::uint32_t>(feed.size_approx());
        return{active_.load(),queued,active_mask_.load(),starts_.load(),stops_.load(),rendered_.load(),starved_.load(),stale_.load(),discontinuities_.load(),completed_.load(),overflows_.load(),false,false};
    }
    [[nodiscard]]bool slot_status(std::size_t slot,std::uint64_t&generation,bool&active)const noexcept{if(slot>=Voices)return false;generation=published_generation_[slot].load(std::memory_order_acquire);active=(active_mask_.load(std::memory_order_acquire)&(std::uint64_t{1}<<slot))!=0;return true;}
private:
    struct Voice{std::uint64_t generation{0},expected_sequence{1};float gain{1};std::uint32_t offset{0};bool active{false},loop{false},has_block{false},starved_this_block{false};Block block{};};
    void drain_commands()noexcept{StreamingVoiceCommand command{};while(commands_.try_pop(command)){
        if(command.kind==StreamingVoiceCommandKind::stop_all){for(auto&voice:voices_)if(voice.active){voice.active=false;voice.has_block=false;stops_.fetch_add(1);}continue;}
        auto&voice=voices_[command.slot];if(command.kind==StreamingVoiceCommandKind::start){voice={};voice.generation=command.generation;voice.gain=command.gain;voice.loop=command.loop;voice.active=true;starts_.fetch_add(1);}
        else if(voice.active&&voice.generation==command.generation){voice.active=false;voice.has_block=false;stops_.fetch_add(1);}
    }}
    bool load(std::size_t slot,Voice&voice)noexcept{Block candidate{};while(feeds_[slot].try_pop(candidate)){
        if(candidate.generation!=voice.generation){stale_.fetch_add(1);continue;}
        if(candidate.sequence!=voice.expected_sequence){discontinuities_.fetch_add(1);voice.expected_sequence=candidate.sequence;}
        voice.expected_sequence=candidate.sequence+1;voice.block=candidate;voice.offset=0;voice.has_block=true;return true;
    }return false;}
    void publish()noexcept{std::uint32_t count=0;std::uint64_t mask=0;for(std::size_t i=0;i<Voices;++i){published_generation_[i].store(voices_[i].generation,std::memory_order_release);if(voices_[i].active){++count;if(i<64)mask|=std::uint64_t{1}<<i;}}active_mask_.store(mask,std::memory_order_release);active_.store(count,std::memory_order_release);}
    std::array<Voice,Voices>voices_{};std::array<SpscQueue<Block,BlocksPerVoice>,Voices>feeds_{};SpscQueue<StreamingVoiceCommand,CommandCapacity>commands_{};
    std::array<std::atomic<std::uint64_t>,Voices>published_generation_{};std::atomic<std::uint32_t>active_{0};std::atomic<std::uint64_t>active_mask_{0},starts_{0},stops_{0},rendered_{0},starved_{0},stale_{0},discontinuities_{0},completed_{0},overflows_{0};
};

static_assert(std::is_trivially_copyable_v<StreamingVoiceBlock<256>>);
static_assert(std::is_trivially_copyable_v<StreamingVoiceCommand>);
}
