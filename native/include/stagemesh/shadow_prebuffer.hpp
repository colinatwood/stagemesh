#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

struct CoreShadowPrebufferStatus {
    std::uint64_t source_id{0};
    std::uint64_t generation{0};
    std::uint64_t show_revision{0};
    std::uint64_t content_hash{0};
    std::uint64_t contiguous_from_show_ns{0};
    std::uint64_t buffered_until_show_ns{0};
    std::uint64_t rendered_frames{0};
    std::uint64_t rendered_blocks{0};
    std::uint64_t discontinuities{0};
    bool healthy{false};
};

template<std::size_t Capacity = 64>
class CoreShadowPrebuffer final {
public:
    [[nodiscard]] bool configure(std::uint64_t source_id,
                                 std::uint64_t generation,
                                 std::uint64_t show_revision,
                                 std::uint64_t content_hash) noexcept {
        if (source_id == 0) return false;
        auto* slot = find_or_empty(source_id);
        if (!slot) return false;
        if (slot->source_id != source_id || slot->generation != generation ||
            slot->show_revision != show_revision || slot->content_hash != content_hash) {
            *slot = {};
            slot->source_id = source_id;
            slot->generation = generation;
            slot->show_revision = show_revision;
            slot->content_hash = content_hash;
        }
        return true;
    }

    [[nodiscard]] bool ingest_block(std::uint64_t source_id,
                                    std::uint64_t generation,
                                    std::uint64_t show_revision,
                                    std::uint64_t content_hash,
                                    std::uint64_t start_show_ns,
                                    std::uint64_t end_show_ns,
                                    std::uint32_t frames,
                                    bool healthy) noexcept {
        auto* slot = find(source_id);
        if (!slot || slot->generation != generation || slot->show_revision != show_revision ||
            slot->content_hash != content_hash || end_show_ns <= start_show_ns || frames == 0) {
            return false;
        }
        if (slot->rendered_blocks == 0) {
            slot->contiguous_from_show_ns = start_show_ns;
            slot->buffered_until_show_ns = end_show_ns;
        } else if (start_show_ns == slot->buffered_until_show_ns) {
            slot->buffered_until_show_ns = end_show_ns;
        } else if (start_show_ns >= slot->contiguous_from_show_ns && end_show_ns <= slot->buffered_until_show_ns) {
            // Idempotent/replayed block entirely inside the verified window.
        } else {
            ++slot->discontinuities;
            slot->healthy = false;
            return false;
        }
        slot->rendered_frames += frames;
        ++slot->rendered_blocks;
        slot->healthy = healthy;
        return true;
    }

    void invalidate_revision(std::uint64_t revision) noexcept {
        for (auto& slot : slots_) {
            if (slot.source_id && slot.show_revision != revision) {
                slot.healthy = false;
                slot.contiguous_from_show_ns = 0;
                slot.buffered_until_show_ns = 0;
            }
        }
    }

    [[nodiscard]] bool status(std::uint64_t source_id, CoreShadowPrebufferStatus& out) const noexcept {
        const auto* slot = find_const(source_id);
        if (!slot) return false;
        out = *slot;
        return true;
    }

private:
    [[nodiscard]] CoreShadowPrebufferStatus* find(std::uint64_t id) noexcept {
        for (auto& slot : slots_) if (slot.source_id == id) return &slot;
        return nullptr;
    }
    [[nodiscard]] const CoreShadowPrebufferStatus* find_const(std::uint64_t id) const noexcept {
        for (const auto& slot : slots_) if (slot.source_id == id) return &slot;
        return nullptr;
    }
    [[nodiscard]] CoreShadowPrebufferStatus* find_or_empty(std::uint64_t id) noexcept {
        for (auto& slot : slots_) if (slot.source_id == id) return &slot;
        for (auto& slot : slots_) if (slot.source_id == 0) return &slot;
        return nullptr;
    }

    std::array<CoreShadowPrebufferStatus, Capacity> slots_{};
};

} // namespace stagemesh
