#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace stagemesh {

using MidiClockPulseSink=bool(*)(void*,std::uint64_t,std::uint64_t) noexcept;
struct MidiClockStatus {std::uint64_t authority_epoch{0},emitted{0},received{0},rejected{0},last_sequence{0},last_pulse_show_ns{0},maximum_jitter_ns{0};double bpm{120};bool running{false},configured{false},physical_outputs_armed{false};};

// Deterministic 24-PPQN Show-Time clock. Generation is control-thread owned;
// emitted pulses are passed to a bounded downstream scheduler.
class MidiClock24Ppqn final {
public:
 [[nodiscard]] bool configure(std::uint64_t epoch,double bpm,std::uint64_t boundary_show_ns)noexcept{if(!epoch||!valid_bpm(bpm))return false;epoch_=epoch;bpm_=bpm;next_exact_=static_cast<double>(boundary_show_ns);next_show_ns_=boundary_show_ns;configured_=true;running_=false;return true;}
 [[nodiscard]] bool start(std::uint64_t epoch,std::uint64_t boundary_show_ns)noexcept{if(!configured_||epoch!=epoch_)return reject();next_exact_=static_cast<double>(boundary_show_ns);next_show_ns_=boundary_show_ns;running_=true;return true;}
 [[nodiscard]] bool stop(std::uint64_t epoch)noexcept{if(!configured_||epoch!=epoch_)return reject();running_=false;return true;}
 [[nodiscard]] bool set_tempo(std::uint64_t epoch,double bpm,std::uint64_t boundary_show_ns)noexcept{if(!configured_||epoch!=epoch_||!valid_bpm(bpm)||boundary_show_ns<last_pulse_show_ns_)return reject();bpm_=bpm;next_exact_=static_cast<double>(boundary_show_ns);next_show_ns_=boundary_show_ns;return true;}
 [[nodiscard]] std::uint32_t emit_until(std::uint64_t until_show_ns,MidiClockPulseSink sink,void* context,std::uint32_t maximum=4096)noexcept{
  if(!configured_||!running_||!sink)return 0;
  std::uint32_t count=0;const double interval=60'000'000'000.0/(bpm_*24.0);
  while(next_show_ns_<=until_show_ns&&count<maximum){const auto sequence=emitted_+1;if(!sink(context,sequence,next_show_ns_))break;last_pulse_show_ns_=next_show_ns_;++emitted_;++count;next_exact_+=interval;next_show_ns_=static_cast<std::uint64_t>(std::llround(next_exact_));}return count;}
 [[nodiscard]] bool observe(std::uint64_t epoch,std::uint64_t sequence,std::uint64_t show_ns)noexcept{
  if(!configured_||epoch!=epoch_||sequence<=last_sequence_||(last_received_show_ns_&&show_ns<=last_received_show_ns_))return reject();
  if(last_received_show_ns_){const auto interval=show_ns-last_received_show_ns_;const double measured=60'000'000'000.0/(static_cast<double>(interval)*24.0);if(valid_bpm(measured))bpm_=received_<2?measured:bpm_*.9+measured*.1;const auto expected=60'000'000'000.0/(bpm_*24.0);const auto jitter=static_cast<std::uint64_t>(std::llround(std::abs(static_cast<double>(interval)-expected)));maximum_jitter_ns_=std::max(maximum_jitter_ns_,jitter);}
  last_sequence_=sequence;last_received_show_ns_=show_ns;last_pulse_show_ns_=show_ns;++received_;return true;}
 [[nodiscard]] MidiClockStatus status()const noexcept{return{epoch_,emitted_,received_,rejected_,last_sequence_,last_pulse_show_ns_,maximum_jitter_ns_,bpm_,running_,configured_,false};}
private:
 [[nodiscard]] static bool valid_bpm(double bpm)noexcept{return std::isfinite(bpm)&&bpm>=20&&bpm<=400;}
 [[nodiscard]] bool reject()noexcept{++rejected_;return false;}
 std::uint64_t epoch_{0},emitted_{0},received_{0},rejected_{0},last_sequence_{0},last_pulse_show_ns_{0},last_received_show_ns_{0},maximum_jitter_ns_{0},next_show_ns_{0};
 double bpm_{120},next_exact_{0};bool running_{false},configured_{false};
};

} // namespace stagemesh
