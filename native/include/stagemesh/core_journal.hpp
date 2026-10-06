#pragma once
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
namespace stagemesh {
enum class CoreJournalKind:std::uint8_t{transport=0,cue=1,automation=2,routing=3,runtime_swap=4,parameter=5,midi=6,lighting=7,sampler=8};
struct CoreJournalRecord{std::uint64_t sequence{0},show_ns{0},event_id{0},subject_id{0},revision{0},previous_hash{0},hash{0};CoreJournalKind kind{CoreJournalKind::transport};};
inline std::uint64_t journal_mix(std::uint64_t h,std::uint64_t v) noexcept{h^=v+0x9e3779b97f4a7c15ULL+(h<<6U)+(h>>2U);return h;}
template<std::size_t Capacity=4096> class CoreJournal final{
public:
 [[nodiscard]] bool append(CoreJournalKind kind,std::uint64_t show,std::uint64_t event,std::uint64_t subject,std::uint64_t revision) noexcept{
   const auto w=write_.load(std::memory_order_relaxed),r=read_.load(std::memory_order_acquire);if(w-r>=Capacity){dropped_.fetch_add(1);return false;}
   CoreJournalRecord x{};x.sequence=w+1;x.show_ns=show;x.event_id=event;x.subject_id=subject;x.revision=revision;x.kind=kind;x.previous_hash=last_hash_.load(std::memory_order_relaxed);
   auto h=journal_mix(x.previous_hash,x.sequence);h=journal_mix(h,show);h=journal_mix(h,event);h=journal_mix(h,subject);h=journal_mix(h,revision);h=journal_mix(h,static_cast<std::uint64_t>(kind));x.hash=h;
   records_[w%Capacity]=x;last_hash_.store(h,std::memory_order_release);write_.store(w+1,std::memory_order_release);return true;}
 [[nodiscard]] bool try_pop(CoreJournalRecord& out) noexcept{const auto r=read_.load(std::memory_order_relaxed),w=write_.load(std::memory_order_acquire);if(r==w)return false;out=records_[r%Capacity];read_.store(r+1,std::memory_order_release);return true;}
 [[nodiscard]] std::uint64_t pending()const noexcept{return write_.load()-read_.load();} [[nodiscard]]std::uint64_t dropped()const noexcept{return dropped_.load();} [[nodiscard]]std::uint64_t last_hash()const noexcept{return last_hash_.load();}
private:std::array<CoreJournalRecord,Capacity>records_{};std::atomic<std::uint64_t>write_{0},read_{0},dropped_{0},last_hash_{0};};
} // namespace stagemesh
