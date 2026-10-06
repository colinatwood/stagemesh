#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>

namespace stagemesh {

enum class MonitorChannel : std::uint8_t {
    self = 0,
    vocals,
    band,
    click,
    talkback,
    ambient,
    count,
};

constexpr std::size_t monitor_channel_count = static_cast<std::size_t>(MonitorChannel::count);

struct MonitorBusSnapshot {
    float master{72.0F};
    std::array<float, monitor_channel_count> levels{76.0F, 58.0F, 62.0F, 38.0F, 45.0F, 28.0F};
    bool muted{false};
};

class MonitorBus {
public:
    MonitorBus() noexcept;

    void set_master(float percent) noexcept;
    void set_level(MonitorChannel channel, float percent) noexcept;
    void set_muted(bool muted) noexcept;

    [[nodiscard]] float master() const noexcept;
    [[nodiscard]] float level(MonitorChannel channel) const noexcept;
    [[nodiscard]] bool muted() const noexcept;
    [[nodiscard]] MonitorBusSnapshot snapshot() const noexcept;

    [[nodiscard]] static bool parse_channel(std::string_view name, MonitorChannel& out) noexcept;
    [[nodiscard]] static std::string_view channel_name(MonitorChannel channel) noexcept;

private:
    [[nodiscard]] static float clamp_percent(float value) noexcept;

    std::atomic<float> master_{72.0F};
    std::array<std::atomic<float>, monitor_channel_count> levels_{};
    std::atomic<bool> muted_{false};
};

struct MonitorBusEntry {
    std::string player_id;
    MonitorBus bus;
};

// Registry operations are control-thread only. MonitorBus values themselves
// expose atomic reads/writes suitable for a future audio callback snapshot.
class MonitorBusRegistry {
public:
    MonitorBus& get_or_create(std::string_view player_id);
    [[nodiscard]] MonitorBus* find(std::string_view player_id) noexcept;
    [[nodiscard]] const MonitorBus* find(std::string_view player_id) const noexcept;
    [[nodiscard]] std::size_t size() const noexcept { return size_; }

private:
    std::array<MonitorBusEntry, 32> entries_{};
    std::size_t size_{0};
};

} // namespace stagemesh
