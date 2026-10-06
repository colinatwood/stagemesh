#pragma once
#include <atomic>
#include <cstdint>
namespace stagemesh {
class CaptureIngressAudit final {
public:
 struct Status{std::uint64_t callbacks{0},frames{0},record_blocks{0},queue_rejections{0},nonfinite_samples{0},max_duration_ns{0};bool physical_outputs_armed{false};};
 void finish(std::uint64_t frames,std::uint64_t blocks,std::uint64_t rejected,std::uint64_t nonfinite,std::uint64_t duration_ns)noexcept{callbacks_.fetch_add(1,std::memory_order_relaxed);frames_.fetch_add(frames,std::memory_order_relaxed);blocks_.fetch_add(blocks,std::memory_order_relaxed);rejected_.fetch_add(rejected,std::memory_order_relaxed);nonfinite_.fetch_add(nonfinite,std::memory_order_relaxed);auto maximum=max_duration_.load(std::memory_order_relaxed);while(duration_ns>maximum&&!max_duration_.compare_exchange_weak(maximum,duration_ns,std::memory_order_relaxed)){} }
 [[nodiscard]] Status status()const noexcept{return{callbacks_.load(std::memory_order_relaxed),frames_.load(std::memory_order_relaxed),blocks_.load(std::memory_order_relaxed),rejected_.load(std::memory_order_relaxed),nonfinite_.load(std::memory_order_relaxed),max_duration_.load(std::memory_order_relaxed),false};}
private:std::atomic<std::uint64_t>callbacks_{0},frames_{0},blocks_{0},rejected_{0},nonfinite_{0},max_duration_{0};
};
}
