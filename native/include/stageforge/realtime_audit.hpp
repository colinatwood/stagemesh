#pragma once
#include <atomic>
#include <cstdint>
namespace stageforge {
class RealtimeAudit final{
public:
 struct Status{std::uint64_t callbacks{0},deadline_misses{0},consecutive_misses{0},max_duration_ns{0},nonfinite_samples{0},queue_pressure_events{0},optional_shed_blocks{0},recovery_transitions{0},allocation_attempts{0},allocated_bytes{0},lock_attempts{0};std::uint32_t overload_level{0};bool qualification_enabled{false},physical_outputs_armed{false};};
 void finish(std::uint64_t duration_ns,std::uint64_t deadline_ns)noexcept{callbacks_.fetch_add(1,std::memory_order_relaxed);auto maximum=max_duration_.load();while(duration_ns>maximum&&!max_duration_.compare_exchange_weak(maximum,duration_ns)){}if(duration_ns>deadline_ns){deadline_misses_.fetch_add(1);const auto misses=consecutive_.fetch_add(1)+1;on_time_.store(0);const auto level=misses>=10?2U:misses>=3?1U:0U;if(level>overload_.load())overload_.store(level);}else{consecutive_.store(0);const auto good=on_time_.fetch_add(1)+1;if(good>=128&&overload_.exchange(0)!=0){recovery_.fetch_add(1);on_time_.store(0);}}}
 void note_nonfinite(std::uint64_t count=1)noexcept{nonfinite_.fetch_add(count);}void note_queue_pressure()noexcept{queue_pressure_.fetch_add(1);}void note_optional_shed()noexcept{optional_shed_.fetch_add(1);}bool allow_optional()const noexcept{return overload_.load(std::memory_order_relaxed)==0;}
 void note_allocation(std::uint64_t bytes)noexcept{allocation_attempts_.fetch_add(1,std::memory_order_relaxed);allocated_bytes_.fetch_add(bytes,std::memory_order_relaxed);}void note_lock_attempt()noexcept{lock_attempts_.fetch_add(1,std::memory_order_relaxed);}
 Status status()const noexcept{return{callbacks_.load(),deadline_misses_.load(),consecutive_.load(),max_duration_.load(),nonfinite_.load(),queue_pressure_.load(),optional_shed_.load(),recovery_.load(),allocation_attempts_.load(),allocated_bytes_.load(),lock_attempts_.load(),overload_.load(),qualification_enabled(),false};}
 static constexpr bool qualification_enabled()noexcept{
#ifdef STAGEMESH_RT_QUALIFICATION
 return true;
#else
 return false;
#endif
 }
private:std::atomic<std::uint64_t>callbacks_{0},deadline_misses_{0},consecutive_{0},max_duration_{0},nonfinite_{0},queue_pressure_{0},optional_shed_{0},recovery_{0},on_time_{0},allocation_attempts_{0},allocated_bytes_{0},lock_attempts_{0};std::atomic<std::uint32_t>overload_{0};};
}
