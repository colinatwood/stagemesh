#include "device_identity.h"
#include <array>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace stagemesh {
namespace {
constexpr std::array<std::uint32_t, 64> k = {
    0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
    0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
    0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
    0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
    0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
    0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
    0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
    0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
};
constexpr std::uint32_t rotr(std::uint32_t value, unsigned shift) {
    return (value >> shift) | (value << (32u - shift));
}
void transform(const std::uint8_t* block, std::array<std::uint32_t, 8>& state) {
    std::uint32_t w[64]{};
    for (unsigned i = 0; i < 16; ++i) {
        const auto* p = block + i * 4;
        w[i] = (std::uint32_t(p[0]) << 24) | (std::uint32_t(p[1]) << 16) | (std::uint32_t(p[2]) << 8) | std::uint32_t(p[3]);
    }
    for (unsigned i = 16; i < 64; ++i) {
        auto s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15] >> 3);
        auto s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    auto a=state[0],b=state[1],c=state[2],d=state[3],e=state[4],f=state[5],g=state[6],h=state[7];
    for (unsigned i = 0; i < 64; ++i) {
        auto s1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
        auto ch = (e & f) ^ ((~e) & g);
        auto t1 = h + s1 + ch + k[i] + w[i];
        auto s0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
        auto maj = (a & b) ^ (a & c) ^ (b & c);
        auto t2 = s0 + maj;
        h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
    }
    state[0]+=a;state[1]+=b;state[2]+=c;state[3]+=d;state[4]+=e;state[5]+=f;state[6]+=g;state[7]+=h;
}
}

std::string sha256_hex(std::string_view input) {
    std::array<std::uint32_t,8> state = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
    const auto* data = reinterpret_cast<const std::uint8_t*>(input.data());
    std::size_t offset = 0;
    while (input.size() - offset >= 64) { transform(data + offset, state); offset += 64; }
    std::array<std::uint8_t,128> tail{};
    const auto remaining = input.size() - offset;
    for (std::size_t i=0;i<remaining;++i) tail[i]=data[offset+i];
    tail[remaining]=0x80;
    const auto tail_blocks = remaining < 56 ? 1u : 2u;
    const std::uint64_t bits = static_cast<std::uint64_t>(input.size()) * 8u;
    const auto length_offset = tail_blocks * 64u - 8u;
    for (unsigned i=0;i<8;++i) tail[length_offset + i] = static_cast<std::uint8_t>((bits >> (56u - 8u*i)) & 0xffu);
    transform(tail.data(), state);
    if (tail_blocks == 2) transform(tail.data()+64, state);
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (auto word : state) out << std::setw(8) << word;
    return out.str();
}

std::string sha256_token(std::string_view input) { return "sha256:" + sha256_hex(input); }

DeviceSelection pin_device(const DeviceRecord& record, bool require_input, bool require_output) {
    if (record.native_hash.empty() || record.persistent_hash.empty()) throw std::invalid_argument("device identity hashes are required");
    if (record.automatic_reconnect && record.identity_strength != IdentityStrength::OsStableEndpoint)
        throw std::invalid_argument("automatic reconnect requires a stable endpoint identity");
    if (require_input && !record.input) throw std::invalid_argument("device does not provide requested input direction");
    if (require_output && !record.output) throw std::invalid_argument("device does not provide requested output direction");
    return {record.kind, record.native_hash, record.persistent_hash, record.automatic_reconnect, require_input, require_output};
}

DeviceResolution resolve_device(const DeviceSelection& selection, const std::vector<DeviceRecord>& devices) {
    if (selection.native_hash.empty() || selection.persistent_hash.empty())
        return {ResolutionStatus::Detached, static_cast<std::size_t>(-1)};
    std::vector<std::size_t> persistent;
    std::vector<std::size_t> native;
    for (std::size_t i=0;i<devices.size();++i) {
        const auto& d = devices[i];
        if (d.kind != selection.kind) continue;
        if (selection.require_input && !d.input) continue;
        if (selection.require_output && !d.output) continue;
        if (d.native_hash == selection.native_hash && d.persistent_hash == selection.persistent_hash) native.push_back(i);
        if (d.persistent_hash == selection.persistent_hash) persistent.push_back(i);
    }
    if (!selection.automatic_reconnect) {
        if (native.size() == 1) return {ResolutionStatus::Attached, native.front()};
        if (native.size() > 1) return {ResolutionStatus::Ambiguous, static_cast<std::size_t>(-1)};
        return {ResolutionStatus::Detached, static_cast<std::size_t>(-1)};
    }
    if (persistent.size() > 1) return {ResolutionStatus::Ambiguous, static_cast<std::size_t>(-1)};
    if (persistent.empty()) return {ResolutionStatus::Detached, static_cast<std::size_t>(-1)};
    auto index = persistent.front();
    // Hash equality cannot replace current identity assurance. A formerly strong
    // selection must fence even its original native object when assurance is
    // withdrawn. Keep weak duplicate candidates in the ambiguity count above.
    if (!devices[index].automatic_reconnect ||
        devices[index].identity_strength != IdentityStrength::OsStableEndpoint ||
        devices[index].native_hash.empty())
        return {ResolutionStatus::Detached, static_cast<std::size_t>(-1)};
    return {devices[index].native_hash == selection.native_hash ? ResolutionStatus::Attached : ResolutionStatus::Rebound, index};
}

const char* resolution_status_name(ResolutionStatus status) {
    switch (status) {
        case ResolutionStatus::Attached: return "attached";
        case ResolutionStatus::Rebound: return "rebound";
        case ResolutionStatus::Detached: return "detached";
        case ResolutionStatus::Ambiguous: return "ambiguous";
    }
    return "unknown";
}
const char* identity_strength_name(IdentityStrength strength) {
    switch (strength) {
        case IdentityStrength::Volatile: return "volatile";
        case IdentityStrength::InstallationSnapshot: return "installation-snapshot";
        case IdentityStrength::OsStableEndpoint: return "os-stable-endpoint";
    }
    return "unknown";
}
const char* device_kind_name(DeviceKind kind) { return kind == DeviceKind::Audio ? "audio" : "midi"; }

}
