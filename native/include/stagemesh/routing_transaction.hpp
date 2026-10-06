#pragma once
#include "stagemesh/runtime_show.hpp"
#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {
struct CoreRoutingStatus { std::uint64_t revision{0}, commits{0}, conflicts{0}; std::uint16_t route_count{0}; };

template <std::size_t Capacity=128>
class CoreRoutingState final {
public:
    [[nodiscard]] bool begin(std::uint64_t expected_revision) noexcept {
        if (open_ || expected_revision != revision_) { ++conflicts_; return false; }
        staged_ = active_; staged_count_ = active_count_; open_ = true; return true;
    }
    [[nodiscard]] bool set(const CoreRuntimeRoute& route) noexcept {
        if (!open_ || route.from_id == 0 || route.to_id == 0 || route.from_id == route.to_id) return false;
        for (std::size_t i=0; i<staged_count_; ++i) {
            if (staged_[i].from_id == route.from_id && staged_[i].to_id == route.to_id) { staged_[i]=route; return true; }
        }
        if (staged_count_ >= Capacity) return false;
        staged_[staged_count_++] = route; return true;
    }
    [[nodiscard]] bool validate() const noexcept {
        if (!open_) return false;
        std::array<std::uint64_t, Capacity*2> nodes{}; std::size_t n=0;
        auto add=[&](std::uint64_t id) noexcept {
            for (std::size_t i=0;i<n;++i) if (nodes[i]==id) return;
            if (n<nodes.size()) nodes[n++]=id;
        };
        for (std::size_t i=0;i<staged_count_;++i) if (staged_[i].enabled) { add(staged_[i].from_id); add(staged_[i].to_id); }
        std::array<std::uint16_t, Capacity*2> indegree{};
        for (std::size_t i=0;i<staged_count_;++i) if (staged_[i].enabled)
            for (std::size_t j=0;j<n;++j) if (nodes[j]==staged_[i].to_id) ++indegree[j];
        std::array<bool, Capacity*2> removed{}; std::size_t removed_count=0;
        for (std::size_t pass=0; pass<n; ++pass) {
            bool progress=false;
            for (std::size_t i=0;i<n;++i) {
                if (removed[i] || indegree[i]!=0) continue;
                removed[i]=true; ++removed_count; progress=true;
                for (std::size_t r=0;r<staged_count_;++r) if (staged_[r].enabled && staged_[r].from_id==nodes[i])
                    for (std::size_t j=0;j<n;++j) if (!removed[j] && nodes[j]==staged_[r].to_id && indegree[j]>0) --indegree[j];
            }
            if (!progress) break;
        }
        return removed_count==n;
    }
    [[nodiscard]] bool commit() noexcept {
        if (!open_ || !validate()) return false;
        active_=staged_; active_count_=staged_count_; open_=false; ++revision_; ++commits_; return true;
    }
    void rollback() noexcept { open_=false; }
    [[nodiscard]] CoreRoutingStatus status() const noexcept { return {revision_,commits_,conflicts_,static_cast<std::uint16_t>(active_count_)}; }
    [[nodiscard]] const CoreRuntimeRoute* routes() const noexcept { return active_.data(); }
private:
    std::array<CoreRuntimeRoute,Capacity> active_{},staged_{};
    std::size_t active_count_{0},staged_count_{0}; bool open_{false};
    std::uint64_t revision_{0},commits_{0},conflicts_{0};
};
} // namespace stagemesh
