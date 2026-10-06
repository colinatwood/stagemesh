#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

inline constexpr std::size_t le_iso_timing_frame_size = 56;

struct LeIsoTimingObservation {
    std::uint64_t node_id{0};
    std::uint64_t sequence{0};
    std::uint64_t authority_epoch{0};
    std::uint64_t event_counter{0};
    std::uint64_t node_transmit_ns{0};
    bool authenticated{false};
};

struct LeIsoHardwareStatus {
    bool kernel_iso_supported{false};
    bool open{false};
    bool connecting{false};
    bool connected{false};
    std::uint64_t received_sdus{0};
    std::uint64_t transmitted_sdus{0};
    std::uint64_t received_bytes{0};
    std::uint64_t transmitted_bytes{0};
    std::uint64_t would_block{0};
    std::uint64_t io_errors{0};
    int last_errno{0};
};

[[nodiscard]] bool encode_le_iso_timing_frame(const LeIsoTimingObservation& observation,
                                              std::array<std::uint8_t, le_iso_timing_frame_size>& frame) noexcept;
[[nodiscard]] bool decode_le_iso_timing_frame(const std::uint8_t* frame, std::size_t size,
                                              LeIsoTimingObservation& observation) noexcept;

// Linux Bluetooth ISO socket data-plane adapter. BlueZ/PipeWire or another
// platform BAP layer remains responsible for discovery, pairing, codec/QoS and
// stream authorization. This object owns only an established/nonblocking ISO
// SDU path and never arms an audio output.
class LeIsoHardwareSocket final {
public:
    LeIsoHardwareSocket() noexcept;
    ~LeIsoHardwareSocket();
    LeIsoHardwareSocket(const LeIsoHardwareSocket&) = delete;
    LeIsoHardwareSocket& operator=(const LeIsoHardwareSocket&) = delete;

    [[nodiscard]] static bool probe_kernel_support() noexcept;

    [[nodiscard]] bool open_unicast(const char* local_address, const char* remote_address,
                                    bool random_address) noexcept;
    [[nodiscard]] bool adopt_fd_for_test(int fd) noexcept;
    [[nodiscard]] bool refresh_connection() noexcept;
    [[nodiscard]] bool receive(std::uint8_t* destination, std::size_t capacity,
                               std::size_t& received, std::uint64_t& received_monotonic_ns) noexcept;
    [[nodiscard]] bool send(const std::uint8_t* data, std::size_t size) noexcept;
    void close() noexcept;
    [[nodiscard]] LeIsoHardwareStatus status() const noexcept { return status_; }

private:
    void fail(int error_number) noexcept;
    int fd_{-1};
    LeIsoHardwareStatus status_{};
};

} // namespace stagemesh
