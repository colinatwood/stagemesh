#include "stagemesh/monitor_bus.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace stagemesh {

MonitorBus::MonitorBus() noexcept {
    constexpr std::array<float, monitor_channel_count> defaults{76.0F, 58.0F, 62.0F, 38.0F, 45.0F, 28.0F};
    for (std::size_t index = 0; index < monitor_channel_count; ++index) {
        levels_[index].store(defaults[index], std::memory_order_relaxed);
    }
}

float MonitorBus::clamp_percent(float value) noexcept {
    if (!std::isfinite(value)) {
        return 0.0F;
    }
    return std::clamp(value, 0.0F, 100.0F);
}

void MonitorBus::set_master(float percent) noexcept {
    master_.store(clamp_percent(percent), std::memory_order_release);
}

void MonitorBus::set_level(MonitorChannel channel, float percent) noexcept {
    const auto index = static_cast<std::size_t>(channel);
    if (index >= monitor_channel_count) {
        return;
    }
    levels_[index].store(clamp_percent(percent), std::memory_order_release);
}

void MonitorBus::set_muted(bool muted) noexcept {
    muted_.store(muted, std::memory_order_release);
}

float MonitorBus::master() const noexcept {
    return master_.load(std::memory_order_acquire);
}

float MonitorBus::level(MonitorChannel channel) const noexcept {
    const auto index = static_cast<std::size_t>(channel);
    if (index >= monitor_channel_count) {
        return 0.0F;
    }
    return levels_[index].load(std::memory_order_acquire);
}

bool MonitorBus::muted() const noexcept {
    return muted_.load(std::memory_order_acquire);
}

MonitorBusSnapshot MonitorBus::snapshot() const noexcept {
    MonitorBusSnapshot value{};
    value.master = master();
    value.muted = muted();
    for (std::size_t index = 0; index < monitor_channel_count; ++index) {
        value.levels[index] = levels_[index].load(std::memory_order_acquire);
    }
    return value;
}

bool MonitorBus::parse_channel(std::string_view name, MonitorChannel& out) noexcept {
    constexpr std::array<std::string_view, monitor_channel_count> names{"self", "vocals", "band", "click", "talkback", "ambient"};
    for (std::size_t index = 0; index < names.size(); ++index) {
        if (name == names[index]) {
            out = static_cast<MonitorChannel>(index);
            return true;
        }
    }
    return false;
}

std::string_view MonitorBus::channel_name(MonitorChannel channel) noexcept {
    constexpr std::array<std::string_view, monitor_channel_count> names{"self", "vocals", "band", "click", "talkback", "ambient"};
    const auto index = static_cast<std::size_t>(channel);
    return index < names.size() ? names[index] : "unknown";
}

MonitorBus& MonitorBusRegistry::get_or_create(std::string_view player_id) {
    if (player_id.empty() || player_id.size() > 64) {
        throw std::invalid_argument("invalid player id");
    }
    if (auto* existing = find(player_id)) {
        return *existing;
    }
    if (size_ >= entries_.size()) {
        throw std::runtime_error("monitor bus registry full");
    }
    const auto index = size_;
    entries_[index].player_id.assign(player_id);
    ++size_;
    return entries_[index].bus;
}

MonitorBus* MonitorBusRegistry::find(std::string_view player_id) noexcept {
    for (std::size_t index = 0; index < size_; ++index) {
        if (entries_[index].player_id == player_id) {
            return &entries_[index].bus;
        }
    }
    return nullptr;
}

const MonitorBus* MonitorBusRegistry::find(std::string_view player_id) const noexcept {
    for (std::size_t index = 0; index < size_; ++index) {
        if (entries_[index].player_id == player_id) {
            return &entries_[index].bus;
        }
    }
    return nullptr;
}

} // namespace stagemesh
