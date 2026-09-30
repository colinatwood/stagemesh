#pragma once

#include "stagemesh/sacn.hpp"

#include <array>
#include <atomic>
#include <cstdint>
#include <string>
#include <string_view>

namespace stagemesh {

struct SacnUdpStatus {
    bool configured{false};
    bool armed{false};
    std::array<char, 64> target{};
    std::uint16_t port{5568};
    std::uint64_t packets_sent{0};
    std::uint64_t send_errors{0};
};

// Explicitly armed unicast E1.31 transport. Multicast discovery/routing is not
// implied by this adapter; venue patching provides an exact execution target.
class SacnUdpOutput {
public:
    SacnUdpOutput() noexcept = default;
    ~SacnUdpOutput();
    SacnUdpOutput(const SacnUdpOutput&) = delete;
    SacnUdpOutput& operator=(const SacnUdpOutput&) = delete;

    bool configure(std::string_view ipv4_target, std::uint16_t port = 5568) noexcept;
    void arm(bool enabled) noexcept;
    void close() noexcept;
    [[nodiscard]] bool send(const SacnDataPacket& packet) noexcept;
    [[nodiscard]] SacnUdpStatus status() const noexcept;
    [[nodiscard]] std::string_view last_error() const noexcept { return last_error_; }

private:
    int socket_{-1};
    std::uint32_t target_addr_be_{0};
    std::array<char, 64> target_{};
    std::uint16_t port_{5568};
    std::atomic<bool> configured_{false}, armed_{false};
    std::atomic<std::uint64_t> packets_sent_{0}, send_errors_{0};
    std::string last_error_{};
};

} // namespace stagemesh
