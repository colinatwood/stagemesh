#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
namespace stagemesh {
using DawReadFn=bool(*)(void*,std::uint64_t,float*,float*,std::uint32_t) noexcept;
using DawWriteFn=bool(*)(void*,const float*,const float*,std::uint32_t) noexcept;
using DawEffectFn=bool(*)(void*,float*,float*,std::uint32_t,std::uint64_t) noexcept;
using DawProgressFn=void(*)(void*,std::uint64_t,std::uint64_t) noexcept;
struct DawRenderRegion {std::uint64_t clip_id{0},start_frame{0},length_frames{0},source_offset_frames{0};float gain{1},pan{0};std::uint64_t fade_in_frames{0},fade_out_frames{0};DawReadFn read{nullptr};void* source_context{nullptr};bool muted{false};};
struct DawStreamRenderStatus {std::uint64_t total_frames{0},rendered_frames{0},rendered_blocks{0},source_reads{0};std::uint32_t regions{0};float peak{0},minimum_limiter_gain{1};bool configured{false},complete{false},cancelled{false},failed{false},physical_outputs_armed{false};};
template<std::size_t RegionCapacity=4096,std::size_t BlockFrames=1024> class DawStreamRenderer final {
public:
 [[nodiscard]] bool configure(std::uint64_t start,std::uint64_t end,float ceiling_db=-1) noexcept {if(end<=start||!std::isfinite(ceiling_db)||ceiling_db>0||ceiling_db<-24)return false;start_=start;end_=end;ceiling_=std::pow(10.0F,ceiling_db/20.0F);count_=0;cancel_.store(false);status_={end-start,0,0,0,0,0,1,true,false,false,false,false};return true;}
 [[nodiscard]] bool add_region(const DawRenderRegion&r) noexcept {if(!status_.configured||count_>=RegionCapacity||r.clip_id==0||r.length_frames==0||!r.read||!std::isfinite(r.gain)||!std::isfinite(r.pan)||r.fade_in_frames+r.fade_out_frames>r.length_frames)return false;regions_[count_++]=r;status_.regions=static_cast<std::uint32_t>(count_);return true;}
 void cancel() noexcept {cancel_.store(true,std::memory_order_release);}
 [[nodiscard]] bool render(DawWriteFn write,void*wctx,DawEffectFn effect=nullptr,void*ectx=nullptr,DawProgressFn progress=nullptr,void*pctx=nullptr) noexcept {
  if(!status_.configured||!write||status_.complete)return false;
  std::array<float,BlockFrames>left{},right{},sl{},sr{};float limiter=1;
  for(std::uint64_t block=start_;block<end_;block+=BlockFrames){if(cancel_.load(std::memory_order_acquire)){status_.cancelled=true;return false;}const auto frames=static_cast<std::uint32_t>(std::min<std::uint64_t>(BlockFrames,end_-block));std::fill_n(left.data(),frames,0);std::fill_n(right.data(),frames,0);
   for(std::size_t n=0;n<count_;++n){const auto&r=regions_[n];if(r.muted)continue;const auto begin=std::max(block,r.start_frame),finish=std::min(block+frames,r.start_frame+r.length_frames);if(finish<=begin)continue;const auto amount=static_cast<std::uint32_t>(finish-begin);const auto relative=begin-r.start_frame;const auto destination=static_cast<std::uint32_t>(begin-block);if(!r.read(r.source_context,r.source_offset_frames+relative,sl.data(),sr.data(),amount)){status_.failed=true;return false;}++status_.source_reads;const float pan=std::clamp(r.pan,-1.0F,1.0F),gl=r.gain*std::sqrt((1-pan)*.5F),gr=r.gain*std::sqrt((1+pan)*.5F);
    for(std::uint32_t i=0;i<amount;++i){const auto position=relative+i,remaining=r.length_frames-position;float envelope=1;if(r.fade_in_frames&&position<r.fade_in_frames)envelope=std::min(envelope,static_cast<float>(position+1)/r.fade_in_frames);if(r.fade_out_frames&&remaining<=r.fade_out_frames)envelope=std::min(envelope,static_cast<float>(remaining)/r.fade_out_frames);left[destination+i]+=(std::isfinite(sl[i])?sl[i]:0)*gl*envelope;right[destination+i]+=(std::isfinite(sr[i])?sr[i]:0)*gr*envelope;}}
   if(effect&&!effect(ectx,left.data(),right.data(),frames,block)){status_.failed=true;return false;}for(std::uint32_t i=0;i<frames;++i){const float peak=std::max(std::abs(left[i]),std::abs(right[i]));status_.peak=std::max(status_.peak,peak);if(peak>ceiling_&&peak>0)limiter=std::min(limiter,ceiling_/peak);else limiter=std::min(1.0F,limiter+.002F*(1-limiter));status_.minimum_limiter_gain=std::min(status_.minimum_limiter_gain,limiter);left[i]*=limiter;right[i]*=limiter;}if(!write(wctx,left.data(),right.data(),frames)){status_.failed=true;return false;}status_.rendered_frames+=frames;++status_.rendered_blocks;if(progress)progress(pctx,status_.rendered_frames,status_.total_frames);}
  status_.complete=true;return true;}
 [[nodiscard]] DawStreamRenderStatus status()const noexcept{return status_;}
private:std::array<DawRenderRegion,RegionCapacity>regions_{};std::size_t count_{0};std::uint64_t start_{0},end_{0};float ceiling_{1};std::atomic<bool>cancel_{false};DawStreamRenderStatus status_{};
};}

