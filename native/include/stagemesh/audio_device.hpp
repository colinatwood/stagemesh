#pragma once

#include <cstdint>
#include <string_view>

namespace stagemesh {

struct AudioDeviceConfig {
    double sample_rate{48000.0};
    std::uint32_t input_channels{0};
    std::uint32_t output_channels{2};
    std::uint32_t frames_per_buffer{256};
};

enum class AudioDeviceState : std::uint8_t {
    closed,
    open,
    running,
    faulted,
};

struct AudioDeviceStatus {
    AudioDeviceState state{AudioDeviceState::closed};
    AudioDeviceConfig config{};
    std::uint64_t callback_count{0};
    std::uint64_t xruns{0};
};

class AudioDevice {
public:
    virtual ~AudioDevice() = default;

    [[nodiscard]] virtual std::string_view id() const noexcept = 0;
    [[nodiscard]] virtual std::string_view name() const noexcept = 0;
    virtual bool open(const AudioDeviceConfig& config) = 0;
    virtual bool start() = 0;
    virtual void stop() noexcept = 0;
    virtual void close() noexcept = 0;
    [[nodiscard]] virtual AudioDeviceStatus status() const noexcept = 0;
};

// Dependency-free development device. It validates lifecycle/configuration but
// performs no hardware I/O. A miniaudio/CoreAudio/ASIO/JACK adapter can replace
// it without changing MonitorBus or transport APIs.
class NullAudioDevice final : public AudioDevice {
public:
    [[nodiscard]] std::string_view id() const noexcept override { return "null-audio"; }
    [[nodiscard]] std::string_view name() const noexcept override { return "StageMesh Null Audio Device"; }

    bool open(const AudioDeviceConfig& config) override;
    bool start() override;
    void stop() noexcept override;
    void close() noexcept override;
    [[nodiscard]] AudioDeviceStatus status() const noexcept override;

private:
    AudioDeviceStatus status_{};
};

} // namespace stagemesh
