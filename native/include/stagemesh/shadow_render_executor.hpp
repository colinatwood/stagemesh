#pragma once

#include "stagemesh/shadow_prebuffer.hpp"
#include "stagemesh/shadow_render_planner.hpp"

#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

using CoreShadowRenderBlockFn = bool (*)(void* context,
                                         std::uint64_t start_show_ns,
                                         std::uint64_t end_show_ns,
                                         std::uint32_t frames) noexcept;

struct CoreShadowRenderExecutorStatus {
    std::uint64_t source_id{0};
    std::uint64_t generation{0};
    std::uint64_t show_revision{0};
    std::uint64_t content_hash{0};
    std::uint64_t next_show_ns{0};
    std::uint64_t requested_until_show_ns{0};
    std::uint64_t rendered_frames{0};
    std::uint64_t rendered_blocks{0};
    std::uint64_t failures{0};
    bool registered{false};
    bool healthy{false};
};

// Bounded control-thread executor for deterministic source adapters. Core owns
// ordering and evidence publication; adapters own actual sample production.
// No method here arms an output or changes authority.
template<std::size_t Capacity = 64>
class CoreShadowRenderExecutor final {
public:
    CoreShadowRenderExecutor(CoreShadowPrebuffer<Capacity>& prebuffer,
                             CoreShadowRenderPlanner<Capacity>& planner) noexcept
        : prebuffer_(prebuffer), planner_(planner) {}

    [[nodiscard]] bool register_source(std::uint64_t source_id,
                                       std::uint64_t generation,
                                       std::uint64_t show_revision,
                                       std::uint64_t content_hash,
                                       std::uint64_t start_show_ns,
                                       CoreShadowRenderBlockFn render,
                                       void* context) noexcept {
        if (source_id == 0 || render == nullptr || !prebuffer_.configure(source_id, generation, show_revision, content_hash)) return false;
        auto* slot = find_or_empty(source_id);
        if (!slot) return false;
        *slot = {source_id, generation, show_revision, content_hash, start_show_ns, start_show_ns,
                 0, 0, 0, true, true, render, context};
        return true;
    }

    [[nodiscard]] bool render_until(std::uint64_t source_id,
                                    std::uint64_t target_show_ns,
                                    std::uint64_t block_duration_ns,
                                    std::uint32_t frames_per_block) noexcept {
        auto* slot = find(source_id);
        if (!slot || !slot->registered || !slot->healthy || block_duration_ns == 0 || frames_per_block == 0 || target_show_ns < slot->next_show_ns) return false;
        slot->requested_until_show_ns = target_show_ns;
        while (slot->next_show_ns < target_show_ns) {
            const auto remaining = target_show_ns - slot->next_show_ns;
            const auto duration = remaining < block_duration_ns ? remaining : block_duration_ns;
            const auto end = slot->next_show_ns + duration;
            const auto frames64 = (static_cast<std::uint64_t>(frames_per_block) * duration + block_duration_ns - 1) / block_duration_ns;
            const auto frames = static_cast<std::uint32_t>(frames64 == 0 ? 1 : frames64);
            if (!slot->render(slot->context, slot->next_show_ns, end, frames) ||
                !prebuffer_.ingest_block(source_id, slot->generation, slot->show_revision, slot->content_hash,
                                         slot->next_show_ns, end, frames, true)) {
                slot->healthy = false;
                ++slot->failures;
                (void)planner_.report(source_id, slot->generation, slot->show_revision, slot->content_hash, slot->next_show_ns, false);
                return false;
            }
            slot->next_show_ns = end;
            slot->rendered_frames += frames;
            ++slot->rendered_blocks;
        }
        if (!planner_.report(source_id, slot->generation, slot->show_revision, slot->content_hash, slot->next_show_ns, true)) {
            slot->healthy = false;
            ++slot->failures;
            return false;
        }
        return true;
    }

    void invalidate_revision(std::uint64_t revision) noexcept {
        prebuffer_.invalidate_revision(revision);
        planner_.invalidate_revision(revision);
        for (auto& slot : slots_) if (slot.registered && slot.show_revision != revision) slot.healthy = false;
    }

    [[nodiscard]] bool status(std::uint64_t source_id, CoreShadowRenderExecutorStatus& out) const noexcept {
        const auto* slot = find_const(source_id);
        if (!slot) return false;
        out = *slot;
        return true;
    }

private:
    struct Slot : CoreShadowRenderExecutorStatus {
        CoreShadowRenderBlockFn render{nullptr};
        void* context{nullptr};
    };
    Slot* find(std::uint64_t id) noexcept { for (auto& x : slots_) if (x.source_id == id) return &x; return nullptr; }
    const Slot* find_const(std::uint64_t id) const noexcept { for (const auto& x : slots_) if (x.source_id == id) return &x; return nullptr; }
    Slot* find_or_empty(std::uint64_t id) noexcept { if (auto* x = find(id)) return x; for (auto& x : slots_) if (!x.registered) return &x; return nullptr; }

    CoreShadowPrebuffer<Capacity>& prebuffer_;
    CoreShadowRenderPlanner<Capacity>& planner_;
    std::array<Slot, Capacity> slots_{};
};

} // namespace stagemesh
