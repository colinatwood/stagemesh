#pragma once

#include "stagemesh/artnet.hpp"

#include <array>
#include <atomic>
#include <cstdint>
#include <string>
#include <string_view>

namespace stagemesh {

struct ArtNetUdpStatus {
    bool configured{false};
    bool armed{false};
    std::array<char, 64> target{};
    std::uint16_t port{6454};
    std::uint64_t packets_sent{0};
    std::uint64_t send_errors{0};
};

// Explicitly armed unicast Art-Net transport. Configuration alone never sends
// packets. Broadcast/multicast targets are intentionally rejected in this
// starter so enabling physical output is a conscious, narrow action.
class ArtNetUdpOutput {
public:
    ArtNetUdpOutput() noexcept = default;
    ~ArtNetUdpOutput();

    ArtNetUdpOutput(const ArtNetUdpOutput&) = delete;
    ArtNetUdpOutput& operator=(const ArtNetUdpOutput&) = delete;

    bool configure(std::string_view ipv4_target, std::uint16_t port = 6454) noexcept;
    void arm(bool enabled) noexcept;
    void close() noexcept;
    [[nodiscard]] bool send(const ArtNetDmxPacket& packet) noexcept;
    [[nodiscard]] ArtNetUdpStatus status() const noexcept;
    [[nodiscard]] std::string_view last_error() const noexcept { return last_error_; }

private:
    int socket_{-1};
    std::uint32_t target_addr_be_{0};
    std::array<char, 64> target_{};
    std::uint16_t port_{6454};
    std::atomic<bool> configured_{false};
    std::atomic<bool> armed_{false};
    std::atomic<std::uint64_t> packets_sent_{0};
    std::atomic<std::uint64_t> send_errors_{0};
    std::string last_error_{};
};

} // namespace stagemesh
