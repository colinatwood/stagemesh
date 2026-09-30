#pragma once
#include <array>
#include <atomic>
#include <cstdint>
#include <thread>
namespace stagemesh {
template<std::size_t Tracks=8,std::size_t BlockFrames=256,std::size_t Capacity=64> class DawRecordingQueue final {
public:
 struct Block{std::uint64_t generation{0},sequence{0},show_frame{0};std::uint32_t frames{0};std::array<float,BlockFrames>left{},right{};};
 struct TrackStatus{std::uint64_t generation{0},submitted{0},written{0},dropped{0},stale{0},sequence_gaps{0},queued{0};bool armed{false};};
 // Arm/disarm/pop belong to one serialized control thread. Submit never waits.
 [[nodiscard]] bool arm(std::size_t track,bool acknowledged)noexcept{if(track>=Tracks||!acknowledged)return false;auto&s=states_[track];disarm(track);s.read.store(s.write.load(std::memory_order_acquire),std::memory_order_release);s.last_sequence.store(0);s.generation.fetch_add(1);s.gate.store(Armed,std::memory_order_release);return true;}
 void disarm(std::size_t track)noexcept{
  if(track>=Tracks)return;
  auto&s=states_[track];s.gate.fetch_and(~Armed,std::memory_order_acq_rel);
  // The admitted writer publishes before releasing Writing. Closing Armed
  // prevents any subsequent submit from acquiring that writer slot.
  while(s.gate.load(std::memory_order_acquire)&Writing)std::this_thread::yield();
 }
 [[nodiscard]] std::uint64_t generation(std::size_t track)const noexcept{return track<Tracks?states_[track].generation.load(std::memory_order_acquire):0;}
 [[nodiscard]] bool submit(std::size_t track,const Block&block)noexcept{
  if(track>=Tracks||block.frames==0||block.frames>BlockFrames)return false;
  auto&s=states_[track];unsigned expected=Armed;
  if(!s.gate.compare_exchange_strong(expected,Armed|Writing,std::memory_order_acq_rel)){s.stale.fetch_add(1);return false;}
  struct Release{std::atomic<unsigned>&gate;~Release(){gate.fetch_and(~Writing,std::memory_order_release);}} release{s.gate};
  if(block.generation!=s.generation.load(std::memory_order_acquire)){s.stale.fetch_add(1);return false;}
  const auto w=s.write.load(std::memory_order_relaxed),r=s.read.load(std::memory_order_acquire);
  if(w-r>=Capacity){s.dropped.fetch_add(1);return false;}
  s.blocks[w%Capacity]=block;s.write.store(w+1,std::memory_order_release);s.submitted.fetch_add(1);return true;
 }
 [[nodiscard]] bool pop(std::size_t track,Block&out)noexcept{if(track>=Tracks)return false;auto&s=states_[track];const auto r=s.read.load(std::memory_order_relaxed),w=s.write.load(std::memory_order_acquire);if(r==w)return false;out=s.blocks[r%Capacity];const auto expected=s.last_sequence.load()+1;if(s.last_sequence.load()!=0&&out.sequence!=expected)s.sequence_gaps.fetch_add(1);s.last_sequence.store(out.sequence);s.read.store(r+1,std::memory_order_release);s.written.fetch_add(1);return true;}
 [[nodiscard]] TrackStatus status(std::size_t track)const noexcept{if(track>=Tracks)return{};const auto&s=states_[track];return{s.generation.load(),s.submitted.load(),s.written.load(),s.dropped.load(),s.stale.load(),s.sequence_gaps.load(),s.write.load()-s.read.load(),bool(s.gate.load()&Armed)};}
private:
 static constexpr unsigned Armed=1,Writing=2;
 static_assert(std::atomic<unsigned>::is_always_lock_free);
 struct State{std::array<Block,Capacity>blocks{};std::atomic<std::uint64_t>write{0},read{0},last_sequence{0},generation{0},submitted{0},written{0},dropped{0},stale{0},sequence_gaps{0};std::atomic<unsigned>gate{0};};std::array<State,Tracks>states_{};
};}
