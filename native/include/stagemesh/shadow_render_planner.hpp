#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
namespace stagemesh {
struct CoreShadowSource{std::uint64_t id{0},show_revision{0},content_hash{0},generation{0},buffered_until_show_ns{0};bool required{true},capable{false},asset_ready{false},healthy{false};};
struct CoreShadowPlanStatus{std::uint64_t target_show_ns{0},required_until_show_ns{0};std::uint16_t sources{0},ready_sources{0},blocked_sources{0};bool ready{false};};
template<std::size_t Capacity=64>class CoreShadowRenderPlanner final{
public:
 [[nodiscard]]bool declare_source(CoreShadowSource s)noexcept{if(s.id==0)return false;for(auto&x:sources_){if(x.id==s.id||x.id==0){x=s;return true;}}return false;}
 [[nodiscard]]bool report(std::uint64_t id,std::uint64_t generation,std::uint64_t show_revision,std::uint64_t hash,std::uint64_t until,bool healthy)noexcept{auto*x=find(id);if(!x||x->generation!=generation||x->show_revision!=show_revision||x->content_hash!=hash)return false;x->buffered_until_show_ns=until;x->healthy=healthy;return true;}
 void invalidate_revision(std::uint64_t revision)noexcept{for(auto&x:sources_)if(x.id&&x.show_revision!=revision){x.healthy=false;x.buffered_until_show_ns=0;}}
 [[nodiscard]]CoreShadowPlanStatus plan(std::uint64_t target,std::uint64_t prebuffer_ns)const noexcept{CoreShadowPlanStatus s{};s.target_show_ns=target;s.required_until_show_ns=target+prebuffer_ns;for(const auto&x:sources_)if(x.id&&x.required){++s.sources;if(x.capable&&x.asset_ready&&x.healthy&&x.buffered_until_show_ns>=s.required_until_show_ns)++s.ready_sources;else ++s.blocked_sources;}s.ready=s.sources>0&&s.blocked_sources==0;return s;}
private:CoreShadowSource*find(std::uint64_t id)noexcept{for(auto&x:sources_)if(x.id==id)return &x;return nullptr;}std::array<CoreShadowSource,Capacity>sources_{};};
} // namespace stagemesh
