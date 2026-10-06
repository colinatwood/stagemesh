#pragma once
#include <atomic>
#include <cstdint>
namespace stagemesh {
class LightingIngressAudit final{
public:
 struct Status{std::uint64_t accepted{0},queue_rejections{0},drained{0},drain_calls{0},max_drain_duration_ns{0};bool physical_outputs_armed{false};};
 void note_handoff(bool accepted)noexcept{(accepted?accepted_:rejected_).fetch_add(1,std::memory_order_relaxed);}
 void note_drain(std::uint64_t count,std::uint64_t duration_ns)noexcept{drained_.fetch_add(count,std::memory_order_relaxed);drain_calls_.fetch_add(1,std::memory_order_relaxed);auto maximum=max_duration_.load(std::memory_order_relaxed);while(duration_ns>maximum&&!max_duration_.compare_exchange_weak(maximum,duration_ns,std::memory_order_relaxed)){} }
 [[nodiscard]] Status status()const noexcept{return{accepted_.load(std::memory_order_relaxed),rejected_.load(std::memory_order_relaxed),drained_.load(std::memory_order_relaxed),drain_calls_.load(std::memory_order_relaxed),max_duration_.load(std::memory_order_relaxed),false};}
private:std::atomic<std::uint64_t>accepted_{0},rejected_{0},drained_{0},drain_calls_{0},max_duration_{0};
};
}
