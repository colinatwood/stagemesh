#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
namespace stagemesh {
template<std::size_t Paths=16,std::size_t MaxDelayFrames=65536> class PluginDelayCompensator final {
public:
 struct Status{std::uint32_t paths{0},maximum_latency_frames{0};std::uint64_t processed_frames{0};bool configured{false},physical_outputs_armed{false};};
 [[nodiscard]] bool configure(const std::uint32_t*latencies,std::size_t count)noexcept{if(!latencies||count==0||count>Paths)return false;std::uint32_t maximum=0;for(std::size_t i=0;i<count;++i){if(latencies[i]>MaxDelayFrames)return false;maximum=std::max(maximum,latencies[i]);}for(std::size_t i=0;i<count;++i){delay_[i]=maximum-latencies[i];write_[i]=0;left_[i].fill(0);right_[i].fill(0);}status_={static_cast<std::uint32_t>(count),maximum,0,true,false};return true;}
 [[nodiscard]] bool process(std::size_t path,float*left,float*right,std::uint32_t frames)noexcept{if(!status_.configured||path>=status_.paths||!left||!right)return false;const auto delay=delay_[path];for(std::uint32_t i=0;i<frames;++i){const auto w=write_[path]%(MaxDelayFrames+1),r=(w+MaxDelayFrames+1-delay)%(MaxDelayFrames+1);const float in_l=left[i],in_r=right[i];left_[path][w]=in_l;right_[path][w]=in_r;left[i]=delay?left_[path][r]:in_l;right[i]=delay?right_[path][r]:in_r;++write_[path];}status_.processed_frames+=frames;return true;}
 [[nodiscard]] std::uint32_t delay_for(std::size_t path)const noexcept{return path<status_.paths?delay_[path]:0;}[[nodiscard]] Status status()const noexcept{return status_;}
private:std::array<std::array<float,MaxDelayFrames+1>,Paths>left_{},right_{};std::array<std::uint64_t,Paths>write_{};std::array<std::uint32_t,Paths>delay_{};Status status_{};
};}
