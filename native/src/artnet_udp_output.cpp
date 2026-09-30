#include "stagemesh/artnet_udp_output.hpp"

#include <algorithm>
#include <cstring>

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace stagemesh {

namespace {

template <std::size_t N>
void copy_text(std::array<char, N>& target, std::string_view source) noexcept {
    const auto size = std::min(source.size(), N - 1);
    std::memcpy(target.data(), source.data(), size);
    target[size] = '\0';
}

bool rejected_target(std::uint32_t address_be) noexcept {
    const std::uint32_t host = ntohl(address_be);
    const auto first = static_cast<std::uint8_t>((host >> 24u) & 0xffu);
    // 0/8, multicast 224/4, and limited broadcast are rejected. Loopback and
    // private unicast are allowed for local testing and venue networks.
    return first == 0 || first >= 224 || host == 0xffffffffu;
}

} // namespace

ArtNetUdpOutput::~ArtNetUdpOutput() {
    close();
}

bool ArtNetUdpOutput::configure(std::string_view ipv4_target, std::uint16_t port) noexcept {
    close();
    if (ipv4_target.empty() || port == 0) {
        last_error_ = "invalid Art-Net target";
        return false;
    }

#if defined(_WIN32)
    WSADATA data{};
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
        last_error_ = "Winsock startup failed";
        return false;
    }
#endif

    in_addr address{};
    std::string target(ipv4_target);
    if (inet_pton(AF_INET, target.c_str(), &address) != 1 || rejected_target(address.s_addr)) {
        last_error_ = "target must be a unicast IPv4 address";
#if defined(_WIN32)
        WSACleanup();
#endif
        return false;
    }

    const int fd = static_cast<int>(::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP));
    if (fd < 0) {
        last_error_ = "unable to create UDP socket";
#if defined(_WIN32)
        WSACleanup();
#endif
        return false;
    }

    socket_ = fd;
    target_addr_be_ = address.s_addr;
    port_ = port;
    copy_text(target_, ipv4_target);
    packets_sent_.store(0, std::memory_order_relaxed);
    send_errors_.store(0, std::memory_order_relaxed);
    armed_.store(false, std::memory_order_release);
    configured_.store(true, std::memory_order_release);
    last_error_.clear();
    return true;
}

void ArtNetUdpOutput::arm(bool enabled) noexcept {
    armed_.store(enabled && configured_.load(std::memory_order_acquire), std::memory_order_release);
}

void ArtNetUdpOutput::close() noexcept {
    armed_.store(false, std::memory_order_release);
    configured_.store(false, std::memory_order_release);
    if (socket_ >= 0) {
#if defined(_WIN32)
        closesocket(static_cast<SOCKET>(socket_));
        WSACleanup();
#else
        ::close(socket_);
#endif
    }
    socket_ = -1;
    target_addr_be_ = 0;
    target_.fill('\0');
}

bool ArtNetUdpOutput::send(const ArtNetDmxPacket& packet) noexcept {
    if (!armed_.load(std::memory_order_acquire) || !configured_.load(std::memory_order_acquire) || socket_ < 0 || packet.size == 0) {
        return false;
    }
    sockaddr_in destination{};
    destination.sin_family = AF_INET;
    destination.sin_port = htons(port_);
    destination.sin_addr.s_addr = target_addr_be_;
#if defined(_WIN32)
    const int sent = ::sendto(static_cast<SOCKET>(socket_), reinterpret_cast<const char*>(packet.bytes.data()), static_cast<int>(packet.size), 0,
                              reinterpret_cast<const sockaddr*>(&destination), sizeof(destination));
    const bool ok = sent == static_cast<int>(packet.size);
#else
    const auto sent = ::sendto(socket_, packet.bytes.data(), packet.size, 0,
                               reinterpret_cast<const sockaddr*>(&destination), sizeof(destination));
    const bool ok = sent >= 0 && static_cast<std::size_t>(sent) == packet.size;
#endif
    if (ok) packets_sent_.fetch_add(1, std::memory_order_relaxed);
    else send_errors_.fetch_add(1, std::memory_order_relaxed);
    return ok;
}

ArtNetUdpStatus ArtNetUdpOutput::status() const noexcept {
    ArtNetUdpStatus value{};
    value.configured = configured_.load(std::memory_order_acquire);
    value.armed = armed_.load(std::memory_order_acquire);
    value.target = target_;
    value.port = port_;
    value.packets_sent = packets_sent_.load(std::memory_order_acquire);
    value.send_errors = send_errors_.load(std::memory_order_acquire);
    return value;
}

} // namespace stagemesh
