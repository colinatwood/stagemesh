#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
namespace stagemesh {
template<std::size_t BlockFrames=256,std::size_t Capacity=32> class DawPlaybackQueue final {
public:
 struct Block{std::uint64_t generation{0},start_frame{0};std::uint32_t frames{0};std::array<float,BlockFrames>left{},right{};};
 struct Status{std::uint64_t generation{1},playhead_frame{0},queued_blocks{0},rendered_blocks{0},rendered_frames{0},underrun_blocks{0},discontinuities{0},seeks{0},loop_wraps{0};bool running{false},looping{false},physical_outputs_armed{false};};
 [[nodiscard]] bool push(const Block&block)noexcept{if(block.generation!=generation_.load(std::memory_order_acquire)||block.frames==0||block.frames>BlockFrames)return false;const auto w=write_.load(std::memory_order_relaxed),r=read_.load(std::memory_order_acquire);if(w-r>=Capacity)return false;blocks_[w%Capacity]=block;write_.store(w+1,std::memory_order_release);return true;}
 void start()noexcept{running_.store(true,std::memory_order_release);}void stop()noexcept{running_.store(false,std::memory_order_release);}
 void seek(std::uint64_t frame)noexcept{running_.store(false);playhead_.store(frame);read_.store(write_.load());generation_.fetch_add(1);seeks_.fetch_add(1);}
 [[nodiscard]] bool set_loop(std::uint64_t begin,std::uint64_t end)noexcept{if(end<=begin)return false;loop_begin_=begin;loop_end_=end;looping_.store(true);return true;}void clear_loop()noexcept{looping_.store(false);}
 void render(float*left,float*right,std::uint32_t frames)noexcept{if(!left||!right||frames==0)return;std::fill_n(left,frames,0);std::fill_n(right,frames,0);if(!running_.load(std::memory_order_acquire))return;const auto r=read_.load(std::memory_order_relaxed),w=write_.load(std::memory_order_acquire);const auto expected=playhead_.load();if(r==w){underruns_.fetch_add(1);advance(frames);return;}const auto&block=blocks_[r%Capacity];if(block.generation!=generation_.load()||block.start_frame!=expected||block.frames!=frames){discontinuities_.fetch_add(1);read_.store(r+1,std::memory_order_release);advance(frames);return;}std::copy_n(block.left.data(),frames,left);std::copy_n(block.right.data(),frames,right);read_.store(r+1,std::memory_order_release);rendered_blocks_.fetch_add(1);rendered_frames_.fetch_add(frames);advance(frames);}
 [[nodiscard]] Status status()const noexcept{const auto w=write_.load(),r=read_.load();return{generation_.load(),playhead_.load(),w-r,rendered_blocks_.load(),rendered_frames_.load(),underruns_.load(),discontinuities_.load(),seeks_.load(),loop_wraps_.load(),running_.load(),looping_.load(),false};}
private:void advance(std::uint32_t frames)noexcept{const auto current=playhead_.load();if(looping_.load()&&loop_end_>loop_begin_){const auto span=loop_end_-loop_begin_;if(current>=loop_begin_){const auto total=(current-loop_begin_)+frames;const auto wraps=total/span;playhead_.store(loop_begin_+(total%span));if(wraps)loop_wraps_.fetch_add(wraps);return;}const auto next=current+frames;if(next>=loop_end_){const auto over=next-loop_end_;loop_wraps_.fetch_add(1+(over/span));playhead_.store(loop_begin_+(over%span));return;}}playhead_.store(current+frames);}
 std::array<Block,Capacity>blocks_{};std::atomic<std::uint64_t>write_{0},read_{0},generation_{1},playhead_{0},rendered_blocks_{0},rendered_frames_{0},underruns_{0},discontinuities_{0},seeks_{0},loop_wraps_{0};std::atomic<bool>running_{false},looping_{false};std::uint64_t loop_begin_{0},loop_end_{0};
};}
