#include "stagemesh/monitor_graph_router.hpp"

#include <algorithm>

namespace stagemesh {

namespace {
float percent_gain(float value) noexcept {
    return std::clamp(value, 0.0F, 100.0F) / 100.0F;
}
}

int MonitorGraphRouter::output_for(std::string_view player_id) const noexcept {
    for (std::size_t index = 0; index < entries_.size(); ++index) {
        if (entries_[index].active && entries_[index].player_id == player_id) {
            return static_cast<int>(first_monitor_output + index);
        }
    }
    return -1;
}

int MonitorGraphRouter::self_source_for(std::string_view player_id) const noexcept {
    for (std::size_t index = 0; index < entries_.size(); ++index) {
        if (entries_[index].active && entries_[index].player_id == player_id) {
            return static_cast<int>(self_source_base + index);
        }
    }
    return -1;
}

int MonitorGraphRouter::ensure_player(std::string_view player_id) noexcept {
    if (player_id.empty()) return -1;
    const int existing = output_for(player_id);
    if (existing >= 0) return existing;
    for (std::size_t index = 0; index < entries_.size(); ++index) {
        if (entries_[index].active) continue;
        try {
            entries_[index].player_id.assign(player_id);
        } catch (...) {
            return -1;
        }
        entries_[index].active = true;
        return static_cast<int>(first_monitor_output + index);
    }
    return -1;
}

bool MonitorGraphRouter::sync(std::string_view player_id, const MonitorBus& bus, AudioGraph& graph) noexcept {
    const int output = ensure_player(player_id);
    const int self_source = self_source_for(player_id);
    if (output < 0 || self_source < 0) return false;
    const auto out = static_cast<std::uint8_t>(output);
    graph.set_route_gain(static_cast<std::uint8_t>(self_source), out, percent_gain(bus.level(MonitorChannel::self)));
    graph.set_route_gain(vocals_source, out, percent_gain(bus.level(MonitorChannel::vocals)));
    graph.set_route_gain(band_source, out, percent_gain(bus.level(MonitorChannel::band)));
    graph.set_route_gain(click_source, out, percent_gain(bus.level(MonitorChannel::click)));
    graph.set_route_gain(talkback_source, out, percent_gain(bus.level(MonitorChannel::talkback)));
    graph.set_route_gain(ambient_source, out, percent_gain(bus.level(MonitorChannel::ambient)));
    graph.set_output_master(out, bus.muted() ? 0.0F : percent_gain(bus.master()));
    return true;
}

} // namespace stagemesh
