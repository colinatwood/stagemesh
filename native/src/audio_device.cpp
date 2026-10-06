#include "stagemesh/audio_device.hpp"

#include <cmath>

namespace stagemesh {

namespace {

bool valid_config(const AudioDeviceConfig& config) noexcept {
    return std::isfinite(config.sample_rate) &&
           config.sample_rate >= 8000.0 && config.sample_rate <= 768000.0 &&
           config.output_channels >= 1 && config.output_channels <= 128 &&
           config.input_channels <= 128 &&
           config.frames_per_buffer >= 16 && config.frames_per_buffer <= 8192;
}

} // namespace

bool NullAudioDevice::open(const AudioDeviceConfig& config) {
    if (!valid_config(config) || status_.state == AudioDeviceState::running) {
        return false;
    }
    status_.config = config;
    status_.callback_count = 0;
    status_.xruns = 0;
    status_.state = AudioDeviceState::open;
    return true;
}

bool NullAudioDevice::start() {
    if (status_.state != AudioDeviceState::open) {
        return false;
    }
    status_.state = AudioDeviceState::running;
    return true;
}

void NullAudioDevice::stop() noexcept {
    if (status_.state == AudioDeviceState::running) {
        status_.state = AudioDeviceState::open;
    }
}

void NullAudioDevice::close() noexcept {
    status_.state = AudioDeviceState::closed;
    status_.callback_count = 0;
}

AudioDeviceStatus NullAudioDevice::status() const noexcept {
    return status_;
}

} // namespace stagemesh
