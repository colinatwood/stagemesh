#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <string_view>

namespace stagemesh {

struct SacnDataPacket {
    std::array<std::uint8_t, 638> bytes{};
    std::size_t size{0};
};

class Sacn {
public:
    // Encodes one full E1.31 data packet with DMX start code 0. StageMesh
    // currently sends the complete 512-slot universe so packet size and callback
    // work remain fixed and bounded. Universe is the E1.31 1..63999 value.
    [[nodiscard]] static SacnDataPacket encode_dmx(
        std::uint16_t universe,
        std::span<const std::uint8_t> levels,
        std::uint8_t sequence,
        const std::array<std::uint8_t, 16>& cid,
        std::string_view source_name = "StageMesh",
        std::uint8_t priority = 100) noexcept {
        SacnDataPacket packet{};
        if (universe == 0 || universe > 63999) return packet;
        auto& out = packet.bytes;
        out[0] = 0x00; out[1] = 0x10; // preamble size
        out[2] = 0x00; out[3] = 0x00; // post-amble
        constexpr std::array<std::uint8_t, 12> identifier{'A','S','C','-','E','1','.','1','7',0,0,0};
        std::copy(identifier.begin(), identifier.end(), out.begin() + 4);
        out[16] = 0x72; out[17] = 0x6e; // root flags/length: 638 - 16
        out[18] = 0x00; out[19] = 0x00; out[20] = 0x00; out[21] = 0x04; // data packet vector
        std::copy(cid.begin(), cid.end(), out.begin() + 22);
        out[38] = 0x72; out[39] = 0x58; // framing flags/length: 638 - 38
        out[40] = 0x00; out[41] = 0x00; out[42] = 0x00; out[43] = 0x02;
        const auto source_size = std::min<std::size_t>(source_name.size(), 63);
        std::copy_n(source_name.begin(), source_size, out.begin() + 44);
        out[108] = priority;
        out[109] = 0; out[110] = 0; // synchronization address
        out[111] = sequence;
        out[112] = 0; // options
        out[113] = static_cast<std::uint8_t>((universe >> 8u) & 0xffu);
        out[114] = static_cast<std::uint8_t>(universe & 0xffu);
        out[115] = 0x72; out[116] = 0x0b; // DMP flags/length: 638 - 115
        out[117] = 0x02; // DMP set property vector
        out[118] = 0xa1; // 16-bit address/data type
        out[119] = 0x00; out[120] = 0x00; // first property address
        out[121] = 0x00; out[122] = 0x01; // address increment
        out[123] = 0x02; out[124] = 0x01; // 513 values: start code + 512 slots
        out[125] = 0x00; // DMX start code
        std::copy_n(levels.begin(), std::min<std::size_t>(levels.size(), 512), out.begin() + 126);
        packet.size = out.size();
        return packet;
    }
};

} // namespace stagemesh
