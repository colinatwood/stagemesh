#pragma once

#include "stagemesh/clock_discipline.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace stagemesh {

enum class LeUwbNodeRole : std::uint8_t {
    performer_input = 0,
    monitor_output = 1,
    stage_output = 2,
    lighting = 3,
    control = 4,
};

enum class LeUwbSyncState : std::uint8_t {
    unconfigured = 0,
    awaiting_uwb = 1,
    awaiting_le = 2,
    locked = 3,
    holdover = 4,
    blocked = 5,
};

struct LeUwbHubPolicy {
    std::uint64_t target_presentation_lead_ns{10'000'000ULL};
    std::uint64_t max_end_to_end_ns{30'000'000ULL};
    std::uint64_t fresh_observation_ns{100'000'000ULL};
    std::uint64_t holdover_ns{500'000'000ULL};
    std::uint64_t max_clock_uncertainty_ns{250'000ULL};
    std::uint64_t max_jitter_ns{500'000ULL};
    double max_range_uncertainty_mm{300.0};
    double max_drift_ppm{250.0};
    bool require_authenticated_observations{true};
};

struct LeUwbNodeDescriptor {
    std::uint64_t node_id{0};
    std::uint32_t le_stream_id{0};
    LeUwbNodeRole role{LeUwbNodeRole::performer_input};
    std::uint64_t presentation_delay_ns{0};
    bool required{true};
};

struct LeUwbNodeStatus {
    LeUwbNodeDescriptor descriptor{};
    LeUwbSyncState state{LeUwbSyncState::unconfigured};
    std::uint64_t authority_epoch{0};
    std::uint64_t uwb_sequence{0};
    std::uint64_t le_sequence{0};
    std::uint64_t le_event_counter{0};
    std::uint64_t last_uwb_hub_ns{0};
    std::uint64_t last_le_hub_ns{0};
    std::uint64_t transport_latency_ns{0};
    std::uint64_t jitter_ns{0};
    std::uint64_t clock_uncertainty_ns{0};
    double distance_mm{0.0};
    double range_uncertainty_mm{0.0};
    double drift_ppm{0.0};
    std::int64_t clock_offset_ns{0};
    std::uint64_t rejected_observations{0};
    bool authenticated{false};
};

struct LeUwbSyncPlan {
    std::uint64_t generation{0};
    std::uint64_t authority_epoch{0};
    std::uint64_t target_hub_ns{0};
    std::uint64_t target_show_ns{0};
    std::uint64_t presentation_lead_ns{0};
    std::uint32_t configured_nodes{0};
    std::uint32_t required_nodes{0};
    std::uint32_t ready_nodes{0};
    std::uint32_t holdover_nodes{0};
    std::uint32_t blocked_nodes{0};
    bool ready{false};
    bool physical_outputs_armed{false};
};

// Provider-neutral coordinator for a live-stage hub. LE adapters report their
// isochronous transport timing; UWB adapters report ranging and paired clock
// observations. Core only produces timestamped presentation targets. Radio
// discovery, pairing, codecs, keys and physical output arming stay in adapters.
template <std::size_t MaxNodes = 64>
class LeUwbHub final {
    static_assert(MaxNodes > 0);
public:
    [[nodiscard]] bool configure(std::uint64_t authority_epoch, const LeUwbHubPolicy& policy) noexcept {
        if (authority_epoch == 0 || policy.target_presentation_lead_ns == 0 ||
            policy.max_end_to_end_ns < policy.target_presentation_lead_ns ||
            policy.fresh_observation_ns == 0 || policy.holdover_ns < policy.fresh_observation_ns ||
            policy.max_clock_uncertainty_ns == 0 || policy.max_jitter_ns == 0 ||
            !std::isfinite(policy.max_range_uncertainty_mm) || policy.max_range_uncertainty_mm < 0.0 ||
            !std::isfinite(policy.max_drift_ppm) || policy.max_drift_ppm < 0.0) return false;
        if (epoch_ != 0 && authority_epoch < epoch_) return false;
        policy_ = policy;
        epoch_ = authority_epoch;
        generation_ = 0;
        last_plan_ = {};
        for (auto& node : nodes_) {
            if (!node.used) continue;
            reset_evidence(node);
            node.status.authority_epoch = epoch_;
        }
        return true;
    }

    [[nodiscard]] bool register_node(const LeUwbNodeDescriptor& descriptor) noexcept {
        if (epoch_ == 0 || descriptor.node_id == 0 || descriptor.le_stream_id == 0 ||
            descriptor.presentation_delay_ns > policy_.max_end_to_end_ns) return false;
        auto* node = find(descriptor.node_id);
        if (!node) {
            node = first_free();
            if (!node) return false;
            node->used = true;
        }
        reset_evidence(*node);
        node->status.descriptor = descriptor;
        node->status.authority_epoch = epoch_;
        node->status.state = LeUwbSyncState::awaiting_uwb;
        node->discipline.set_holdover_timeout(policy_.holdover_ns);
        return true;
    }

    [[nodiscard]] bool observe_uwb(std::uint64_t node_id, std::uint64_t sequence,
                                   std::uint64_t authority_epoch, std::uint64_t hub_time_ns,
                                   std::uint64_t node_time_ns, double distance_mm,
                                   double range_uncertainty_mm, std::uint64_t clock_uncertainty_ns,
                                   bool authenticated) noexcept {
        auto* node = find(node_id);
        if (!node || sequence == 0 || sequence <= node->status.uwb_sequence ||
            authority_epoch != epoch_ || hub_time_ns == 0 || node_time_ns == 0 ||
            !std::isfinite(distance_mm) || distance_mm < 0.0 ||
            !std::isfinite(range_uncertainty_mm) || range_uncertainty_mm < 0.0 ||
            range_uncertainty_mm > policy_.max_range_uncertainty_mm ||
            clock_uncertainty_ns > policy_.max_clock_uncertainty_ns ||
            (policy_.require_authenticated_observations && !authenticated)) {
            if (node) ++node->status.rejected_observations;
            return false;
        }
        // Correct the hub timestamp for one-way propagation inferred from UWB
        // range. At stage distances this is small, but keeping it explicit
        // avoids baking distance-dependent skew into the clock observation.
        constexpr double light_mm_per_ns = 299.792458;
        const auto propagation_ns = static_cast<std::uint64_t>(std::llround(distance_mm / light_mm_per_ns));
        const auto corrected_hub_ns = propagation_ns < hub_time_ns ? hub_time_ns - propagation_ns : hub_time_ns;
        node->discipline.observe(corrected_hub_ns, node_time_ns);
        const auto clock = node->discipline.snapshot(corrected_hub_ns);
        node->status.uwb_sequence = sequence;
        node->status.last_uwb_hub_ns = hub_time_ns;
        node->status.distance_mm = distance_mm;
        node->status.range_uncertainty_mm = range_uncertainty_mm;
        node->status.clock_uncertainty_ns = clock_uncertainty_ns;
        node->status.drift_ppm = clock.drift_ppm;
        node->status.clock_offset_ns = clock.offset_ns;
        node->uwb_authenticated = authenticated;
        node->status.authenticated = node->uwb_authenticated && node->le_authenticated;
        node->status.state = node->status.le_sequence == 0 ? LeUwbSyncState::awaiting_le : LeUwbSyncState::locked;
        return true;
    }

    [[nodiscard]] bool observe_le(std::uint64_t node_id, std::uint64_t sequence,
                                  std::uint64_t authority_epoch, std::uint64_t event_counter,
                                  std::uint64_t hub_time_ns, std::uint64_t transport_latency_ns,
                                  std::uint64_t jitter_ns, bool authenticated) noexcept {
        auto* node = find(node_id);
        if (!node || sequence == 0 || sequence <= node->status.le_sequence ||
            authority_epoch != epoch_ || event_counter <= node->status.le_event_counter ||
            hub_time_ns == 0 || jitter_ns > policy_.max_jitter_ns ||
            transport_latency_ns > policy_.max_end_to_end_ns ||
            (policy_.require_authenticated_observations && !authenticated)) {
            if (node) ++node->status.rejected_observations;
            return false;
        }
        node->status.le_sequence = sequence;
        node->status.le_event_counter = event_counter;
        node->status.last_le_hub_ns = hub_time_ns;
        node->status.transport_latency_ns = transport_latency_ns;
        node->status.jitter_ns = jitter_ns;
        node->le_authenticated = authenticated;
        node->status.authenticated = node->uwb_authenticated && node->le_authenticated;
        node->status.state = node->status.uwb_sequence == 0 ? LeUwbSyncState::awaiting_uwb : LeUwbSyncState::locked;
        return true;
    }

    [[nodiscard]] LeUwbSyncPlan plan(std::uint64_t hub_now_ns, std::uint64_t show_now_ns,
                                     std::uint64_t authority_epoch) noexcept {
        LeUwbSyncPlan result{};
        result.generation = ++generation_;
        result.authority_epoch = epoch_;
        std::uint64_t required_lead = policy_.target_presentation_lead_ns;
        bool all_required_ready = epoch_ != 0 && authority_epoch == epoch_ && hub_now_ns != 0;
        for (auto& node : nodes_) {
            if (!node.used) continue;
            ++result.configured_nodes;
            if (node.status.descriptor.required) ++result.required_nodes;
            const bool node_ready = evaluate(node, hub_now_ns, required_lead);
            if (node_ready) {
                ++result.ready_nodes;
                if (node.status.state == LeUwbSyncState::holdover) ++result.holdover_nodes;
            } else {
                ++result.blocked_nodes;
                if (node.status.descriptor.required) all_required_ready = false;
            }
        }
        if (result.required_nodes == 0 || required_lead > policy_.max_end_to_end_ns) all_required_ready = false;
        result.presentation_lead_ns = required_lead;
        result.target_hub_ns = saturating_add(hub_now_ns, required_lead);
        result.target_show_ns = saturating_add(show_now_ns, required_lead);
        result.ready = all_required_ready;
        result.physical_outputs_armed = false;
        last_plan_ = result;
        return result;
    }

    [[nodiscard]] bool target_for(std::uint64_t node_id, std::uint64_t plan_generation,
                                  std::uint64_t& out_node_time_ns) noexcept {
        auto* node = find(node_id);
        if (!node || !last_plan_.ready || plan_generation != last_plan_.generation ||
            (node->status.state != LeUwbSyncState::locked && node->status.state != LeUwbSyncState::holdover)) return false;
        out_node_time_ns = node->discipline.project(last_plan_.target_hub_ns);
        return true;
    }

    [[nodiscard]] bool status(std::uint64_t node_id, LeUwbNodeStatus& out) const noexcept {
        const auto* node = find_const(node_id);
        if (!node) return false;
        out = node->status;
        return true;
    }

    [[nodiscard]] LeUwbSyncPlan last_plan() const noexcept { return last_plan_; }
    [[nodiscard]] std::uint64_t authority_epoch() const noexcept { return epoch_; }

private:
    struct Node {
        bool used{false};
        LeUwbNodeStatus status{};
        ClockDiscipline discipline{};
        bool uwb_authenticated{false};
        bool le_authenticated{false};
    };

    static void reset_evidence(Node& node) noexcept {
        const auto descriptor = node.status.descriptor;
        const auto rejected = node.status.rejected_observations;
        node.status = {};
        node.status.descriptor = descriptor;
        node.status.rejected_observations = rejected;
        node.discipline.reset();
        node.uwb_authenticated = false;
        node.le_authenticated = false;
    }

    [[nodiscard]] bool evaluate(Node& node, std::uint64_t hub_now_ns, std::uint64_t& required_lead) noexcept {
        auto& status = node.status;
        if (status.uwb_sequence == 0 || status.le_sequence == 0 ||
            status.authority_epoch != epoch_ ||
            (policy_.require_authenticated_observations && !status.authenticated) ||
            hub_now_ns < status.last_uwb_hub_ns || hub_now_ns < status.last_le_hub_ns) {
            status.state = LeUwbSyncState::blocked;
            return false;
        }
        const auto uwb_age = hub_now_ns - status.last_uwb_hub_ns;
        const auto le_age = hub_now_ns - status.last_le_hub_ns;
        const auto clock = node.discipline.snapshot(hub_now_ns);
        status.drift_ppm = clock.drift_ppm;
        status.clock_offset_ns = clock.offset_ns;
        const double drift_uncertainty = static_cast<double>(uwb_age) * std::abs(clock.drift_ppm) / 1'000'000.0;
        const double projected_uncertainty = static_cast<double>(status.clock_uncertainty_ns) + drift_uncertainty;
        if (uwb_age > policy_.holdover_ns || le_age > policy_.fresh_observation_ns ||
            projected_uncertainty > static_cast<double>(policy_.max_clock_uncertainty_ns) ||
            std::abs(clock.drift_ppm) > policy_.max_drift_ppm ||
            status.jitter_ns > policy_.max_jitter_ns ||
            status.range_uncertainty_mm > policy_.max_range_uncertainty_mm) {
            status.state = LeUwbSyncState::blocked;
            return false;
        }
        status.state = uwb_age > policy_.fresh_observation_ns ? LeUwbSyncState::holdover : LeUwbSyncState::locked;
        const auto node_lead = saturating_add(status.descriptor.presentation_delay_ns,
                              saturating_add(status.transport_latency_ns, status.jitter_ns));
        required_lead = std::max(required_lead, node_lead);
        return node_lead <= policy_.max_end_to_end_ns;
    }

    [[nodiscard]] Node* find(std::uint64_t id) noexcept {
        for (auto& node : nodes_) if (node.used && node.status.descriptor.node_id == id) return &node;
        return nullptr;
    }
    [[nodiscard]] const Node* find_const(std::uint64_t id) const noexcept {
        for (const auto& node : nodes_) if (node.used && node.status.descriptor.node_id == id) return &node;
        return nullptr;
    }
    [[nodiscard]] Node* first_free() noexcept {
        for (auto& node : nodes_) if (!node.used) return &node;
        return nullptr;
    }
    [[nodiscard]] static std::uint64_t saturating_add(std::uint64_t a, std::uint64_t b) noexcept {
        return b > std::numeric_limits<std::uint64_t>::max() - a ? std::numeric_limits<std::uint64_t>::max() : a + b;
    }

    std::array<Node, MaxNodes> nodes_{};
    LeUwbHubPolicy policy_{};
    std::uint64_t epoch_{0};
    std::uint64_t generation_{0};
    LeUwbSyncPlan last_plan_{};
};

} // namespace stagemesh
