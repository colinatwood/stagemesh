#include "stagemesh/core_state.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace stagemesh {

CoreControlState::CoreControlState(double sample_rate, double bpm)
    : transport_(sample_rate, bpm) {
    counters_.revision = revision_;
    counters_.transport_revision = transport_revision_;
}

std::string_view core_mutation_status_name(CoreMutationStatus status) noexcept {
    switch (status) {
        case CoreMutationStatus::applied: return "applied";
        case CoreMutationStatus::duplicate: return "duplicate";
        case CoreMutationStatus::conflict: return "conflict";
        case CoreMutationStatus::invalid: return "invalid";
        case CoreMutationStatus::stale_snapshot: return "stale_snapshot";
        case CoreMutationStatus::busy: return "busy";
    }
    return "invalid";
}

CoreMutationResult CoreControlState::current_result(CoreMutationStatus status, std::uint64_t resource_revision) const noexcept {
    return CoreMutationResult{status, revision_, resource_revision, external_revision_};
}

bool CoreControlState::find_dedup(CoreCommandDomain domain, std::uint64_t command_id, CoreMutationResult& result) const noexcept {
    if (command_id == 0) return false;
    for (const auto& entry : dedup_) {
        if (entry.active && entry.domain == domain && entry.command_id == command_id) {
            result = entry.result;
            result.status = CoreMutationStatus::duplicate;
            return true;
        }
    }
    return false;
}

void CoreControlState::remember_dedup(CoreCommandDomain domain, std::uint64_t command_id, const CoreMutationResult& result) noexcept {
    if (command_id == 0) return;
    dedup_[dedup_cursor_] = DedupEntry{domain, command_id, result, true};
    dedup_cursor_ = (dedup_cursor_ + 1) % dedup_.size();
}

std::uint64_t CoreControlState::monitor_revision_locked(std::string_view player_id) const noexcept {
    for (const auto& entry : monitor_revisions_) {
        if (entry.active && entry.player_id == player_id) return entry.revision;
    }
    return 1;
}

std::uint64_t CoreControlState::bump_monitor_revision_locked(std::string_view player_id) {
    for (auto& entry : monitor_revisions_) {
        if (entry.active && entry.player_id == player_id) return ++entry.revision;
    }
    for (auto& entry : monitor_revisions_) {
        if (!entry.active) {
            entry.player_id.assign(player_id);
            entry.revision = 2;
            entry.active = true;
            return entry.revision;
        }
    }
    throw std::runtime_error("monitor revision registry full");
}

CoreMutationResult CoreControlState::mutate_transport(
    std::uint64_t command_id,
    std::uint64_t expected_resource_revision,
    CoreTransportAction action,
    double value) {
    return mutate_transport_scoped(CoreCommandDomain::control, command_id, expected_resource_revision, action, value);
}

CoreMutationResult CoreControlState::mutate_transport_scoped(
    CoreCommandDomain domain,
    std::uint64_t command_id,
    std::uint64_t expected_resource_revision,
    CoreTransportAction action,
    double value) {
    std::scoped_lock lock(mutex_);
    CoreMutationResult cached{};
    if (find_dedup(domain, command_id, cached)) {
        ++counters_.duplicate_commands;
        return cached;
    }
    if (draft_.active) {
        const auto result = current_result(CoreMutationStatus::busy, transport_revision_);
        remember_dedup(domain, command_id, result);
        return result;
    }
    if (expected_resource_revision != core_any_revision && expected_resource_revision != transport_revision_) {
        ++counters_.conflicts;
        const auto result = current_result(CoreMutationStatus::conflict, transport_revision_);
        remember_dedup(domain, command_id, result);
        return result;
    }

    switch (action) {
        case CoreTransportAction::play: transport_.play(); break;
        case CoreTransportAction::pause: transport_.pause(); break;
        case CoreTransportAction::stop: transport_.stop(); break;
        case CoreTransportAction::rewind: transport_.rewind(); break;
        case CoreTransportAction::set_bpm:
            if (!std::isfinite(value)) {
                ++counters_.invalid_commands;
                const auto result = current_result(CoreMutationStatus::invalid, transport_revision_);
                remember_dedup(domain, command_id, result);
                return result;
            }
            transport_.set_bpm(value);
            break;
        case CoreTransportAction::seek_seconds:
            if (!std::isfinite(value)) {
                ++counters_.invalid_commands;
                const auto result = current_result(CoreMutationStatus::invalid, transport_revision_);
                remember_dedup(domain, command_id, result);
                return result;
            }
            transport_.seek_seconds(value);
            break;
    }

    ++revision_;
    ++transport_revision_;
    ++counters_.applied_commands;
    counters_.revision = revision_;
    counters_.transport_revision = transport_revision_;
    const auto result = current_result(CoreMutationStatus::applied, transport_revision_);
    remember_dedup(domain, command_id, result);
    return result;
}

CoreMutationResult CoreControlState::mutate_monitor(
    std::uint64_t command_id,
    std::uint64_t expected_resource_revision,
    std::string_view player_id,
    std::string_view field,
    double value) {
    return mutate_monitor_scoped(CoreCommandDomain::control, command_id, expected_resource_revision, player_id, field, value);
}

CoreMutationResult CoreControlState::mutate_monitor_scoped(
    CoreCommandDomain domain,
    std::uint64_t command_id,
    std::uint64_t expected_resource_revision,
    std::string_view player_id,
    std::string_view field,
    double value) {
    std::scoped_lock lock(mutex_);
    CoreMutationResult cached{};
    if (find_dedup(domain, command_id, cached)) {
        ++counters_.duplicate_commands;
        return cached;
    }
    const auto current_monitor_revision = monitor_revision_locked(player_id);
    if (draft_.active) {
        const auto result = current_result(CoreMutationStatus::busy, current_monitor_revision);
        remember_dedup(domain, command_id, result);
        return result;
    }
    if (player_id.empty() || player_id.size() > 64 || (expected_resource_revision != core_any_revision && expected_resource_revision != current_monitor_revision)) {
        if (expected_resource_revision != core_any_revision && expected_resource_revision != current_monitor_revision) {
            ++counters_.conflicts;
            const auto result = current_result(CoreMutationStatus::conflict, current_monitor_revision);
            remember_dedup(domain, command_id, result);
            return result;
        }
        ++counters_.invalid_commands;
        const auto result = current_result(CoreMutationStatus::invalid, current_monitor_revision);
        remember_dedup(domain, command_id, result);
        return result;
    }

    try {
        auto& bus = monitors_.get_or_create(player_id);
        if (field == "muted") {
            bus.set_muted(value != 0.0);
        } else if (field == "master") {
            bus.set_master(static_cast<float>(value));
        } else {
            MonitorChannel channel{};
            if (!MonitorBus::parse_channel(field, channel) || !std::isfinite(value)) {
                ++counters_.invalid_commands;
                const auto result = current_result(CoreMutationStatus::invalid, current_monitor_revision);
                remember_dedup(domain, command_id, result);
                return result;
            }
            bus.set_level(channel, static_cast<float>(value));
        }
        ++revision_;
        const auto resource_revision = bump_monitor_revision_locked(player_id);
        ++counters_.applied_commands;
        counters_.revision = revision_;
        const auto result = current_result(CoreMutationStatus::applied, resource_revision);
        remember_dedup(domain, command_id, result);
        return result;
    } catch (const std::exception&) {
        ++counters_.invalid_commands;
        const auto result = current_result(CoreMutationStatus::invalid, current_monitor_revision);
        remember_dedup(domain, command_id, result);
        return result;
    }
}

std::uint64_t CoreControlState::monitor_revision(std::string_view player_id) const noexcept {
    std::scoped_lock lock(mutex_);
    return monitor_revision_locked(player_id);
}

CoreMetrics CoreControlState::metrics() const noexcept {
    std::scoped_lock lock(mutex_);
    CoreMetrics result = counters_;
    result.revision = revision_;
    result.external_revision = external_revision_;
    result.transport_revision = transport_revision_;
    return result;
}

bool CoreControlState::begin_snapshot(std::uint64_t external_revision) noexcept {
    std::scoped_lock lock(mutex_);
    if (draft_.active || external_revision < external_revision_) return false;
    reset_draft_locked();
    draft_.active = true;
    draft_.external_revision = external_revision;
    return true;
}

bool CoreControlState::stage_transport(double bpm, double seconds, bool running) noexcept {
    std::scoped_lock lock(mutex_);
    if (!draft_.active || !std::isfinite(bpm) || !std::isfinite(seconds)) return false;
    draft_.has_transport = true;
    draft_.bpm = bpm;
    draft_.seconds = seconds;
    draft_.running = running;
    return true;
}

bool CoreControlState::stage_monitor(std::string_view player_id, const MonitorBusSnapshot& snapshot) noexcept {
    std::scoped_lock lock(mutex_);
    if (!draft_.active || player_id.empty() || player_id.size() > 64) return false;
    for (std::size_t i = 0; i < draft_.monitor_count; ++i) {
        if (draft_.monitors[i].active && draft_.monitors[i].player_id == player_id) {
            draft_.monitors[i].snapshot = snapshot;
            return true;
        }
    }
    if (draft_.monitor_count >= draft_.monitors.size()) return false;
    auto& entry = draft_.monitors[draft_.monitor_count++];
    entry.player_id.assign(player_id);
    entry.snapshot = snapshot;
    entry.active = true;
    return true;
}

CoreMutationResult CoreControlState::commit_snapshot() {
    std::scoped_lock lock(mutex_);
    if (!draft_.active) return current_result(CoreMutationStatus::invalid, transport_revision_);
    if (draft_.external_revision < external_revision_) {
        ++counters_.stale_snapshots;
        const auto result = current_result(CoreMutationStatus::stale_snapshot, transport_revision_);
        reset_draft_locked();
        return result;
    }
    if (draft_.external_revision == external_revision_) {
        const auto result = current_result(CoreMutationStatus::duplicate, transport_revision_);
        reset_draft_locked();
        return result;
    }

    try {
        if (draft_.has_transport) {
            transport_.set_bpm(draft_.bpm);
            transport_.seek_seconds(draft_.seconds);
            if (draft_.running) transport_.play(); else transport_.pause();
            ++transport_revision_;
        }
        for (std::size_t index = 0; index < draft_.monitor_count; ++index) {
            const auto& staged = draft_.monitors[index];
            if (!staged.active) continue;
            auto& bus = monitors_.get_or_create(staged.player_id);
            bus.set_master(staged.snapshot.master);
            for (std::size_t channel = 0; channel < monitor_channel_count; ++channel) {
                bus.set_level(static_cast<MonitorChannel>(channel), staged.snapshot.levels[channel]);
            }
            bus.set_muted(staged.snapshot.muted);
            (void)bump_monitor_revision_locked(staged.player_id);
        }
    } catch (const std::exception&) {
        ++counters_.invalid_commands;
        const auto result = current_result(CoreMutationStatus::invalid, transport_revision_);
        reset_draft_locked();
        return result;
    }

    external_revision_ = draft_.external_revision;
    ++revision_;
    ++counters_.snapshot_commits;
    counters_.revision = revision_;
    counters_.external_revision = external_revision_;
    counters_.transport_revision = transport_revision_;
    const auto result = current_result(CoreMutationStatus::applied, transport_revision_);
    reset_draft_locked();
    return result;
}

void CoreControlState::abort_snapshot() noexcept {
    std::scoped_lock lock(mutex_);
    reset_draft_locked();
}

void CoreControlState::reset_draft_locked() noexcept {
    draft_ = SnapshotDraft{};
}

} // namespace stagemesh
