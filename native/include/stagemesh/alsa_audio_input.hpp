#pragma once

#include "stagemesh/audio_device.hpp"
#include "stagemesh/canonical_audio.hpp"

#include <atomic>
#include <cstdint>
#include <string>
#include <thread>
#include <vector>

namespace stagemesh {

using AudioCaptureCallback = void (*)(
    void* context,
    const float* interleaved_input,
    std::uint32_t frames,
    std::uint32_t channels) noexcept;

class AlsaAudioInput final {
public:
    AlsaAudioInput() noexcept = default;
    ~AlsaAudioInput();

    AlsaAudioInput(const AlsaAudioInput&) = delete;
    AlsaAudioInput& operator=(const AlsaAudioInput&) = delete;

    bool open(std::string device_address, const AudioDeviceConfig& config, AudioCaptureCallback callback, void* context,
              std::string_view sample_format = "FLOAT_LE") noexcept;
    bool start() noexcept;
    void stop() noexcept;
    void close() noexcept;

    [[nodiscard]] bool available() const noexcept;
    [[nodiscard]] AudioDeviceStatus status() const noexcept;
    [[nodiscard]] AudioDeviceConfig requested_config() const noexcept { return requested_config_; }
    [[nodiscard]] std::string_view sample_format() const noexcept { return sample_format_; }
    [[nodiscard]] std::string_view address() const noexcept { return address_; }
    [[nodiscard]] std::string_view last_error() const noexcept { return last_error_; }

private:
    void capture_loop() noexcept;
    void set_error(const char* text) noexcept;

    struct Api;
    Api* api_{nullptr};
    void* pcm_{nullptr};
    std::string address_{};
    std::string last_error_{};
    AudioDeviceConfig config_{};
    AudioDeviceConfig requested_config_{};
    std::string sample_format_{"unknown"};
    CanonicalAudioSampleFormat pcm_format_{CanonicalAudioSampleFormat::float32};
    std::size_t sample_bytes_{sizeof(float)};
    AudioCaptureCallback callback_{nullptr};
    void* callback_context_{nullptr};
    std::vector<float> float_buffer_{};
    std::vector<std::uint8_t> pcm_buffer_{};
    std::thread thread_{};
    std::atomic<bool> stop_requested_{false};
    std::atomic<AudioDeviceState> state_{AudioDeviceState::closed};
    std::atomic<std::uint64_t> callback_count_{0};
    std::atomic<std::uint64_t> xruns_{0};
};

} // namespace stagemesh
