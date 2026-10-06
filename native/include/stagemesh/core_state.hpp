#pragma once

#include "stagemesh/monitor_bus.hpp"
#include "stagemesh/transport_clock.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <mutex>
#include <string>
#include <string_view>

namespace stagemesh {

inline constexpr std::uint64_t core_any_revision = std::numeric_limits<std::uint64_t>::max();

enum class CoreMutationStatus : std::uint8_t {
    applied = 0,
    duplicate,
    conflict,
    invalid,
    stale_snapshot,
    busy,
};

enum class CoreCommandDomain : std::uint16_t {
    control = 0,
    show_event = 1,
    replication = 2,
    adapter = 3,
};

enum class CoreTransportAction : std::uint8_t {
    play = 0,
    pause,
    stop,
    rewind,
    set_bpm,
    seek_seconds,
};

struct CoreMutationResult {
    CoreMutationStatus status{CoreMutationStatus::invalid};
    std::uint64_t revision{0};
    std::uint64_t resource_revision{0};
    std::uint64_t external_revision{0};

    [[nodiscard]] bool applied() const noexcept { return status == CoreMutationStatus::applied; }
};

struct CoreMetrics {
    std::uint64_t revision{1};
    std::uint64_t external_revision{0};
    std::uint64_t transport_revision{1};
    std::uint64_t applied_commands{0};
    std::uint64_t duplicate_commands{0};
    std::uint64_t conflicts{0};
    std::uint64_t snapshot_commits{0};
    std::uint64_t stale_snapshots{0};
    std::uint64_t invalid_commands{0};
};

// Authoritative native control-state primitive for show-critical control data.
//
// This deliberately stays small: transport intent and personal monitor state.
// Hardware adapters, venue catalogs, governance, networking, and file I/O do
// not belong here. All mutations happen on a control thread; audio readers see
// MonitorBus atomics and TransportClock snapshots without touching this mutex.
class CoreControlState final {
public:
    CoreControlState(double sample_rate = 48000.0, double bpm = 120.0);

    [[nodiscard]] TransportClock& transport() noexcept { return transport_; }
    [[nodiscard]] const TransportClock& transport() const noexcept { return transport_; }
    [[nodiscard]] MonitorBusRegistry& monitors() noexcept { return monitors_; }
    [[nodiscard]] const MonitorBusRegistry& monitors() const noexcept { return monitors_; }

    CoreMutationResult mutate_transport(
        std::uint64_t command_id,
        std::uint64_t expected_resource_revision,
        CoreTransportAction action,
        double value = 0.0);

    CoreMutationResult mutate_transport_scoped(
        CoreCommandDomain domain,
        std::uint64_t command_id,
        std::uint64_t expected_resource_revision,
        CoreTransportAction action,
        double value = 0.0);

    CoreMutationResult mutate_monitor(
        std::uint64_t command_id,
        std::uint64_t expected_resource_revision,
        std::string_view player_id,
        std::string_view field,
        double value);

    CoreMutationResult mutate_monitor_scoped(
        CoreCommandDomain domain,
        std::uint64_t command_id,
        std::uint64_t expected_resource_revision,
        std::string_view player_id,
        std::string_view field,
        double value);

    [[nodiscard]] std::uint64_t monitor_revision(std::string_view player_id) const noexcept;
    [[nodiscard]] CoreMetrics metrics() const noexcept;

    // Snapshot application is a control-plane transaction used by the bridge
    // during migration toward native state authority. A newer external
    // snapshot is applied as one native revision; stale snapshots are refused.
    bool begin_snapshot(std::uint64_t external_revision) noexcept;
    bool stage_transport(double bpm, double seconds, bool running) noexcept;
    bool stage_monitor(std::string_view player_id, const MonitorBusSnapshot& snapshot) noexcept;
    CoreMutationResult commit_snapshot();
    void abort_snapshot() noexcept;

private:
    struct MonitorRevisionEntry {
        std::string player_id{};
        std::uint64_t revision{1};
        bool active{false};
    };

    struct DedupEntry {
        CoreCommandDomain domain{CoreCommandDomain::control};
        std::uint64_t command_id{0};
        CoreMutationResult result{};
        bool active{false};
    };

    struct StagedMonitor {
        std::string player_id{};
        MonitorBusSnapshot snapshot{};
        bool active{false};
    };

    struct SnapshotDraft {
        bool active{false};
        std::uint64_t external_revision{0};
        bool has_transport{false};
        double bpm{120.0};
        double seconds{0.0};
        bool running{false};
        std::array<StagedMonitor, 32> monitors{};
        std::size_t monitor_count{0};
    };

    [[nodiscard]] CoreMutationResult current_result(CoreMutationStatus status, std::uint64_t resource_revision) const noexcept;
    [[nodiscard]] bool find_dedup(CoreCommandDomain domain, std::uint64_t command_id, CoreMutationResult& result) const noexcept;
    void remember_dedup(CoreCommandDomain domain, std::uint64_t command_id, const CoreMutationResult& result) noexcept;
    [[nodiscard]] std::uint64_t monitor_revision_locked(std::string_view player_id) const noexcept;
    [[nodiscard]] std::uint64_t bump_monitor_revision_locked(std::string_view player_id);
    void reset_draft_locked() noexcept;

    mutable std::mutex mutex_{};
    TransportClock transport_;
    MonitorBusRegistry monitors_{};
    std::uint64_t revision_{1};
    std::uint64_t external_revision_{0};
    std::uint64_t transport_revision_{1};
    std::array<MonitorRevisionEntry, 32> monitor_revisions_{};
    std::array<DedupEntry, 256> dedup_{};
    std::size_t dedup_cursor_{0};
    SnapshotDraft draft_{};
    CoreMetrics counters_{};
};

[[nodiscard]] std::string_view core_mutation_status_name(CoreMutationStatus status) noexcept;

} // namespace stagemesh
