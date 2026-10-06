#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace stagemesh {

struct ArtNetDmxPacket {
    std::array<std::uint8_t, 530> bytes{};
    std::size_t size{0};
};

class ArtNet {
public:
    // Encodes ArtDMX (OpDmx 0x5000), Art-Net protocol version 14. Universe is
    // the 15-bit Art-Net Port-Address. Payload is padded to an even length and
    // clamped to the protocol's 512-slot maximum.
    [[nodiscard]] static ArtNetDmxPacket encode_dmx(
        std::uint16_t universe,
        std::span<const std::uint8_t> levels,
        std::uint8_t sequence = 0,
        std::uint8_t physical = 0) noexcept {
        ArtNetDmxPacket packet{};
        constexpr std::array<std::uint8_t, 8> id{'A','r','t','-','N','e','t',0};
        std::copy(id.begin(), id.end(), packet.bytes.begin());
        packet.bytes[8] = 0x00; // OpDmx low byte
        packet.bytes[9] = 0x50;
        packet.bytes[10] = 0x00; // protocol version high byte
        packet.bytes[11] = 14;
        packet.bytes[12] = sequence;
        packet.bytes[13] = physical;
        universe &= 0x7FFFu;
        packet.bytes[14] = static_cast<std::uint8_t>(universe & 0xFFu);
        packet.bytes[15] = static_cast<std::uint8_t>((universe >> 8u) & 0x7Fu);
        std::size_t length = std::min<std::size_t>(levels.size(), 512);
        if (length < 2) length = 2;
        if (length % 2 != 0) ++length;
        packet.bytes[16] = static_cast<std::uint8_t>((length >> 8u) & 0xFFu);
        packet.bytes[17] = static_cast<std::uint8_t>(length & 0xFFu);
        const auto copied = std::min<std::size_t>(levels.size(), length);
        std::copy_n(levels.begin(), copied, packet.bytes.begin() + 18);
        packet.size = 18 + length;
        return packet;
    }
};

} // namespace stagemesh
