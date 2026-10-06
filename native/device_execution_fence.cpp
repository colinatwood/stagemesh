#include "device_execution_fence.h"
#include <stdexcept>

namespace stagemesh {

DeviceExecutionFence::DeviceExecutionFence(DeviceSelection selection)
    : selection_(std::move(selection)) {
    if (selection_.native_hash.empty() || selection_.persistent_hash.empty())
        throw std::invalid_argument("device execution fence requires a pinned identity");
}

FenceObservation DeviceExecutionFence::observation() const noexcept {
    const bool armed = state_ == ExecutionFenceState::Armed;
    return {state_, resolution_, armed, !armed, generation_};
}

void DeviceExecutionFence::transition(ExecutionFenceState next, ResolutionStatus resolution) noexcept {
    if (state_ != next || resolution_ != resolution) ++generation_;
    state_ = next;
    resolution_ = resolution;
}

void DeviceExecutionFence::accept_resolved_native(const DeviceRecord& record) {
    if (record.kind != selection_.kind || record.persistent_hash != selection_.persistent_hash)
        throw std::logic_error("resolved device does not match pinned persistent identity");
    selection_.native_hash = record.native_hash;
}

bool DeviceExecutionFence::arm_initial(const std::vector<DeviceRecord>& devices) {
    if (initial_attempted_ || generation_ != 0) return false;
    initial_attempted_ = true;
    auto resolved = resolve_device(selection_, devices);
    if (resolved.status != ResolutionStatus::Attached) {
        transition(
            resolved.status == ResolutionStatus::Ambiguous ? ExecutionFenceState::FencedAmbiguous : ExecutionFenceState::FencedDetached,
            resolved.status);
        return false;
    }
    accept_resolved_native(devices.at(resolved.index));
    transition(ExecutionFenceState::Armed, ResolutionStatus::Attached);
    return true;
}

FenceObservation DeviceExecutionFence::reconcile(const std::vector<DeviceRecord>& devices) {
    auto resolved = resolve_device(selection_, devices);
    switch (resolved.status) {
        case ResolutionStatus::Attached:
            if (state_ == ExecutionFenceState::Armed) {
                transition(ExecutionFenceState::Armed, ResolutionStatus::Attached);
            } else {
                transition(ExecutionFenceState::RecoveredDisarmed, ResolutionStatus::Attached);
            }
            break;
        case ResolutionStatus::Rebound:
            accept_resolved_native(devices.at(resolved.index));
            transition(ExecutionFenceState::RecoveredDisarmed, ResolutionStatus::Rebound);
            break;
        case ResolutionStatus::Detached:
            transition(ExecutionFenceState::FencedDetached, ResolutionStatus::Detached);
            break;
        case ResolutionStatus::Ambiguous:
            transition(ExecutionFenceState::FencedAmbiguous, ResolutionStatus::Ambiguous);
            break;
    }
    return observation();
}

bool DeviceExecutionFence::explicit_rearm(const std::vector<DeviceRecord>& devices) {
    auto resolved = resolve_device(selection_, devices);
    if (resolved.status != ResolutionStatus::Attached && resolved.status != ResolutionStatus::Rebound) {
        transition(
            resolved.status == ResolutionStatus::Ambiguous ? ExecutionFenceState::FencedAmbiguous : ExecutionFenceState::FencedDetached,
            resolved.status);
        return false;
    }
    accept_resolved_native(devices.at(resolved.index));
    // A native stream may revoke without changing this control-thread fence.
    // Explicit authorization must still advance beyond that revoked generation.
    const auto previous_generation = generation_;
    transition(ExecutionFenceState::Armed, ResolutionStatus::Attached);
    if (generation_ == previous_generation) ++generation_;
    return true;
}

void DeviceExecutionFence::disarm() noexcept {
    transition(ExecutionFenceState::Unarmed, resolution_);
}

const char* execution_fence_state_name(ExecutionFenceState state) {
    switch (state) {
        case ExecutionFenceState::Unarmed: return "unarmed";
        case ExecutionFenceState::Armed: return "armed";
        case ExecutionFenceState::FencedDetached: return "fenced-detached";
        case ExecutionFenceState::FencedAmbiguous: return "fenced-ambiguous";
        case ExecutionFenceState::RecoveredDisarmed: return "recovered-disarmed";
    }
    return "unknown";
}

}
