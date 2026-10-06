#pragma once

#include "stagemesh/audio_graph.hpp"
#include "stagemesh/monitor_bus.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace stagemesh {

// Maps personal MonitorBus controls into the fixed audio graph. Global stems
// occupy sources 0..4; each player receives a dedicated self stem starting at
// source 5. Monitor outputs occupy outputs 1..15, leaving output 0 for FOH.
class MonitorGraphRouter {
public:
    static constexpr std::uint8_t vocals_source = 0;
    static constexpr std::uint8_t band_source = 1;
    static constexpr std::uint8_t click_source = 2;
    static constexpr std::uint8_t talkback_source = 3;
    static constexpr std::uint8_t ambient_source = 4;
    static constexpr std::uint8_t self_source_base = 5;
    static constexpr std::uint8_t first_monitor_output = 1;
    static constexpr std::size_t max_monitor_outputs = audio_graph_max_outputs - first_monitor_output;

    [[nodiscard]] int ensure_player(std::string_view player_id) noexcept;
    [[nodiscard]] int output_for(std::string_view player_id) const noexcept;
    [[nodiscard]] int self_source_for(std::string_view player_id) const noexcept;
    bool sync(std::string_view player_id, const MonitorBus& bus, AudioGraph& graph) noexcept;

private:
    struct Entry {
        std::string player_id{};
        bool active{false};
    };
    std::array<Entry, max_monitor_outputs> entries_{};
};

} // namespace stagemesh
