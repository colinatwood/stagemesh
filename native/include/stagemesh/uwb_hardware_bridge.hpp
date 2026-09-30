#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace stagemesh {

inline constexpr std::size_t uwb_hardware_frame_size = 80;

struct UwbHardwareObservation {
    std::uint64_t node_id{0};
    std::uint64_t sequence{0};
    std::uint64_t authority_epoch{0};
    std::uint64_t hub_time_ns{0};
    std::uint64_t node_time_ns{0};
    double distance_mm{0.0};
    double range_uncertainty_mm{0.0};
    std::uint64_t clock_uncertainty_ns{0};
    bool authenticated{false};
};

struct UwbHardwareBridgeStatus {
    bool open{false};
    bool faulted{false};
    std::uint64_t bytes_read{0};
    std::uint64_t valid_frames{0};
    std::uint64_t invalid_frames{0};
    std::uint64_t resync_bytes{0};
    std::uint64_t io_errors{0};
    int last_errno{0};
};

[[nodiscard]] std::uint32_t hardware_crc32(const std::uint8_t* data, std::size_t size) noexcept;
[[nodiscard]] bool encode_uwb_hardware_frame(const UwbHardwareObservation& observation,
                                             std::array<std::uint8_t, uwb_hardware_frame_size>& frame) noexcept;
[[nodiscard]] bool decode_uwb_hardware_frame(const std::uint8_t* frame, std::size_t size,
                                             UwbHardwareObservation& observation) noexcept;

// Nonblocking POSIX VCOM/serial bridge. UCI/vendor radio control remains in a
// replaceable device adapter; this boundary carries only normalized ranging
// and paired-clock evidence with version, length and CRC protection.
class UwbHardwareBridge final {
public:
    UwbHardwareBridge() noexcept = default;
    ~UwbHardwareBridge();
    UwbHardwareBridge(const UwbHardwareBridge&) = delete;
    UwbHardwareBridge& operator=(const UwbHardwareBridge&) = delete;

    [[nodiscard]] bool open_device(const char* path, std::uint32_t baud) noexcept;
    [[nodiscard]] bool adopt_fd_for_test(int fd) noexcept;
    void close() noexcept;
    [[nodiscard]] bool try_read(UwbHardwareObservation& observation) noexcept;
    [[nodiscard]] UwbHardwareBridgeStatus status() const noexcept { return status_; }

private:
    [[nodiscard]] bool parse_buffer(UwbHardwareObservation& observation) noexcept;
    void discard_prefix(std::size_t count) noexcept;
    void fault(int error_number) noexcept;

    int fd_{-1};
    std::array<std::uint8_t, uwb_hardware_frame_size * 4> buffer_{};
    std::size_t used_{0};
    UwbHardwareBridgeStatus status_{};
};

} // namespace stagemesh
