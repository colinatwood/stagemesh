#pragma once

#include <cstdint>

namespace stagemesh {

enum class CorePlannedHandoffState : std::uint8_t { idle=0, prepared, target_ready, committed, aborted };

struct CorePlannedHandoffStatus {
    std::uint64_t transaction_id{0};
    std::uint64_t source_epoch{0};
    std::uint64_t target_epoch{0};
    std::uint64_t target_show_ns{0};
    std::uint64_t prepares{0};
    std::uint64_t commits{0};
    std::uint64_t aborts{0};
    std::uint64_t conflicts{0};
    CorePlannedHandoffState state{CorePlannedHandoffState::idle};
    bool allow_degraded_program{false};
    bool program_ready{false};
    bool authority_committed{false};
    bool physical_outputs_armed{false};
};

// Control-plane transaction for planned authority handoff. This class validates
// the boundary and fencing facts only; the caller performs the actual witness
// lease transfer. Physical output is deliberately outside this state machine.
class CorePlannedHandoff final {
public:
    [[nodiscard]] bool prepare(std::uint64_t transaction_id, std::uint64_t source_epoch,
                               std::uint64_t target_epoch, std::uint64_t target_show_ns,
                               bool allow_degraded_program) noexcept {
        if (transaction_id==0 || source_epoch==0 || target_epoch<=source_epoch || target_show_ns==0 || active()) {
            ++status_.conflicts; return false;
        }
        const auto prepares=status_.prepares+1, commits=status_.commits, aborts=status_.aborts, conflicts=status_.conflicts;
        status_={transaction_id,source_epoch,target_epoch,target_show_ns,prepares,commits,aborts,conflicts,
                 CorePlannedHandoffState::prepared,allow_degraded_program,false,false,false};
        return true;
    }

    [[nodiscard]] bool acknowledge_target(std::uint64_t transaction_id, bool program_ready) noexcept {
        if (status_.state!=CorePlannedHandoffState::prepared || status_.transaction_id!=transaction_id ||
            (!program_ready && !status_.allow_degraded_program)) { ++status_.conflicts; return false; }
        status_.program_ready=program_ready;
        status_.state=CorePlannedHandoffState::target_ready;
        return true;
    }

    [[nodiscard]] bool commit(std::uint64_t transaction_id, std::uint64_t observed_source_epoch,
                              std::uint64_t witness_epoch, std::uint64_t current_show_ns) noexcept {
        if (status_.state!=CorePlannedHandoffState::target_ready || status_.transaction_id!=transaction_id ||
            observed_source_epoch!=status_.source_epoch || witness_epoch!=status_.target_epoch ||
            current_show_ns<status_.target_show_ns) { ++status_.conflicts; return false; }
        status_.state=CorePlannedHandoffState::committed;
        status_.authority_committed=true;
        status_.physical_outputs_armed=false;
        ++status_.commits;
        return true;
    }

    [[nodiscard]] bool abort(std::uint64_t transaction_id) noexcept {
        if (!active() || status_.transaction_id!=transaction_id) { ++status_.conflicts; return false; }
        status_.state=CorePlannedHandoffState::aborted;
        status_.authority_committed=false;
        status_.physical_outputs_armed=false;
        ++status_.aborts;
        return true;
    }

    [[nodiscard]] CorePlannedHandoffStatus status() const noexcept { return status_; }

private:
    [[nodiscard]] bool active() const noexcept {
        return status_.state==CorePlannedHandoffState::prepared || status_.state==CorePlannedHandoffState::target_ready;
    }
    CorePlannedHandoffStatus status_{};
};

} // namespace stagemesh
