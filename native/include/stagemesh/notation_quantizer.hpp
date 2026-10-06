#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace stagemesh {

enum class NotationGrid : std::uint8_t {
    quarter,
    eighth,
    sixteenth,
    thirty_second,
};

class NotationQuantizer {
public:
    [[nodiscard]] static double step_beats(NotationGrid grid) noexcept {
        switch (grid) {
            case NotationGrid::quarter: return 1.0;
            case NotationGrid::eighth: return 0.5;
            case NotationGrid::sixteenth: return 0.25;
            case NotationGrid::thirty_second: return 0.125;
        }
        return 0.25;
    }

    [[nodiscard]] static double quantize_beats(double beats, NotationGrid grid) noexcept {
        const auto step = step_beats(grid);
        return std::round(std::max(0.0, beats) / step) * step;
    }

    [[nodiscard]] static double minimum_duration_beats(NotationGrid grid) noexcept {
        return step_beats(grid);
    }
};

} // namespace stagemesh
