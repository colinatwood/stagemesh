#include "stagemesh/alsa_audio_output.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <new>

#if defined(__linux__)
#include <dlfcn.h>
#endif

namespace stagemesh {

namespace {

bool valid_config(const AudioDeviceConfig& config) noexcept {
    return std::isfinite(config.sample_rate) &&
           config.sample_rate >= 8000.0 && config.sample_rate <= 384000.0 &&
           config.output_channels >= 1 && config.output_channels <= 32 &&
           config.frames_per_buffer >= 16 && config.frames_per_buffer <= 8192;
}

} // namespace

struct AlsaAudioOutput::Api {
#if defined(__linux__)
    void* library{nullptr};
    using pcm_open_fn = int (*)(void**, const char*, int, int);
    using pcm_close_fn = int (*)(void*);
    using pcm_set_params_fn = int (*)(void*, int, int, unsigned int, unsigned int, int, unsigned int);
    using hw_params_malloc_fn = int (*)(void**);
    using hw_params_free_fn = void (*)(void*);
    using hw_params_current_fn = int (*)(void*, void*);
    using hw_params_get_rate_fn = int (*)(const void*, unsigned int*, int*);
    using hw_params_get_channels_fn = int (*)(const void*, unsigned int*);
    using hw_params_get_period_size_fn = int (*)(const void*, unsigned long*, int*);
    using hw_params_get_format_fn = int (*)(const void*, int*);
    using format_value_fn = int (*)(const char*);
    using pcm_writei_fn = long (*)(void*, const void*, unsigned long);
    using pcm_recover_fn = int (*)(void*, int, int);
    using pcm_prepare_fn = int (*)(void*);
    using strerror_fn = const char* (*)(int);

    pcm_open_fn pcm_open{nullptr};
    pcm_close_fn pcm_close{nullptr};
    pcm_set_params_fn pcm_set_params{nullptr};
    hw_params_malloc_fn hw_params_malloc{nullptr};
    hw_params_free_fn hw_params_free{nullptr};
    hw_params_current_fn hw_params_current{nullptr};
    hw_params_get_rate_fn hw_params_get_rate{nullptr};
    hw_params_get_channels_fn hw_params_get_channels{nullptr};
    hw_params_get_period_size_fn hw_params_get_period_size{nullptr};
    hw_params_get_format_fn hw_params_get_format{nullptr};
    format_value_fn format_value{nullptr};
    pcm_writei_fn pcm_writei{nullptr};
    pcm_recover_fn pcm_recover{nullptr};
    pcm_prepare_fn pcm_prepare{nullptr};
    strerror_fn strerror_fn_ptr{nullptr};
#endif
};

AlsaAudioOutput::~AlsaAudioOutput() {
    close();
}

void AlsaAudioOutput::set_error(const char* text) noexcept {
    try {
        last_error_ = text ? text : "unknown ALSA error";
    } catch (...) {
        last_error_.clear();
    }
}

bool AlsaAudioOutput::open(
    std::string device_address,
    const AudioDeviceConfig& config,
    AudioRenderCallback callback,
    void* callback_context,
    std::string_view sample_format) noexcept {
    close();
    CanonicalAudioSampleFormat pcm_format{};
    if (!valid_config(config) || device_address.empty() || callback == nullptr ||
        !canonical_audio_sample_format_from_name(sample_format, pcm_format)) {
        set_error("invalid ALSA stream configuration");
        state_.store(AudioDeviceState::faulted, std::memory_order_release);
        return false;
    }
#if !defined(__linux__)
    (void)device_address;
    (void)config;
    (void)callback;
    (void)callback_context;
    (void)sample_format;
    set_error("ALSA backend is only available on Linux");
    state_.store(AudioDeviceState::faulted, std::memory_order_release);
    return false;
#else
    auto* api = new (std::nothrow) Api{};
    if (!api) {
        set_error("unable to allocate ALSA runtime state");
        state_.store(AudioDeviceState::faulted, std::memory_order_release);
        return false;
    }
    api->library = dlopen("libasound.so.2", RTLD_NOW | RTLD_LOCAL);
    if (!api->library) {
        delete api;
        set_error("libasound.so.2 unavailable");
        state_.store(AudioDeviceState::faulted, std::memory_order_release);
        return false;
    }

#define SF_ALSA_LOAD(member, symbol) \
    api->member = reinterpret_cast<Api::member##_fn>(dlsym(api->library, symbol)); \
    if (!api->member) { \
        dlclose(api->library); \
        delete api; \
        set_error("required ALSA symbol unavailable: " symbol); \
        state_.store(AudioDeviceState::faulted, std::memory_order_release); \
        return false; \
    }

    SF_ALSA_LOAD(pcm_open, "snd_pcm_open")
    SF_ALSA_LOAD(pcm_close, "snd_pcm_close")
    SF_ALSA_LOAD(pcm_set_params, "snd_pcm_set_params")
    SF_ALSA_LOAD(hw_params_malloc, "snd_pcm_hw_params_malloc")
    SF_ALSA_LOAD(hw_params_free, "snd_pcm_hw_params_free")
    SF_ALSA_LOAD(hw_params_current, "snd_pcm_hw_params_current")
    SF_ALSA_LOAD(hw_params_get_rate, "snd_pcm_hw_params_get_rate")
    SF_ALSA_LOAD(hw_params_get_channels, "snd_pcm_hw_params_get_channels")
    SF_ALSA_LOAD(hw_params_get_period_size, "snd_pcm_hw_params_get_period_size")
    SF_ALSA_LOAD(hw_params_get_format, "snd_pcm_hw_params_get_format")
    SF_ALSA_LOAD(format_value, "snd_pcm_format_value")
    SF_ALSA_LOAD(pcm_writei, "snd_pcm_writei")
    SF_ALSA_LOAD(pcm_recover, "snd_pcm_recover")
    SF_ALSA_LOAD(pcm_prepare, "snd_pcm_prepare")
#undef SF_ALSA_LOAD
    api->strerror_fn_ptr = reinterpret_cast<Api::strerror_fn>(dlsym(api->library, "snd_strerror"));

    void* pcm = nullptr;
    // snd_pcm_stream_t playback == 0. Blocking mode is deliberate: ALSA paces
    // the dedicated playback thread while the control and show threads remain
    // independent.
    int result = api->pcm_open(&pcm, device_address.c_str(), 0, 0);
    if (result < 0 || !pcm) {
        if (api->strerror_fn_ptr) set_error(api->strerror_fn_ptr(result));
        else set_error("snd_pcm_open failed");
        dlclose(api->library);
        delete api;
        state_.store(AudioDeviceState::faulted, std::memory_order_release);
        return false;
    }

    // Access value 3 is the stable ALSA userspace ABI value for
    // SND_PCM_ACCESS_RW_INTERLEAVED. Sample-format values are resolved by the
    // runtime library rather than duplicated as compile-time ALSA constants.
    const auto channels = static_cast<unsigned int>(config.output_channels);
    const auto rate = static_cast<unsigned int>(std::llround(config.sample_rate));
    const auto buffer_us = static_cast<unsigned int>(std::clamp(
        (static_cast<double>(config.frames_per_buffer) / config.sample_rate) * 2'000'000.0,
        2'000.0,
        500'000.0));
    const auto requested_format_name = canonical_audio_sample_format_name(pcm_format);
    const int requested_format = api->format_value(requested_format_name.data());
    if (requested_format < 0) {
        set_error("requested ALSA playback format is unavailable");
        api->pcm_close(pcm); dlclose(api->library); delete api;
        state_.store(AudioDeviceState::faulted, std::memory_order_release); return false;
    }
    result = api->pcm_set_params(pcm, requested_format, 3, channels, rate, 1, buffer_us);
    if (result < 0) {
        if (api->strerror_fn_ptr) set_error(api->strerror_fn_ptr(result));
        else set_error("snd_pcm_set_params failed");
        api->pcm_close(pcm);
        dlclose(api->library);
        delete api;
        state_.store(AudioDeviceState::faulted, std::memory_order_release);
        return false;
    }

    AudioDeviceConfig actual = config;
    void* current = nullptr;
    unsigned int actual_rate = 0, actual_channels = 0;
    unsigned long actual_period = 0;
    int direction = 0, actual_format = -1;
    result = api->hw_params_malloc(&current);
    if (result >= 0 && current) result = api->hw_params_current(pcm, current);
    if (result >= 0) result = api->hw_params_get_rate(current, &actual_rate, &direction);
    if (result >= 0) result = api->hw_params_get_channels(current, &actual_channels);
    if (result >= 0) result = api->hw_params_get_period_size(current, &actual_period, &direction);
    if (result >= 0) result = api->hw_params_get_format(current, &actual_format);
    if (current) api->hw_params_free(current);
    if (result < 0 || actual_format != requested_format || actual_rate < 8000 || actual_rate > 384000 || actual_channels < 1 || actual_channels > 32 || actual_period < 16 || actual_period > 8192) {
        set_error("unable to query configured ALSA playback parameters");
        api->pcm_close(pcm); dlclose(api->library); delete api;
        state_.store(AudioDeviceState::faulted, std::memory_order_release); return false;
    }
    actual.sample_rate = actual_rate; actual.output_channels = actual_channels;
    actual.frames_per_buffer = static_cast<std::uint32_t>(actual_period);

    const auto sample_bytes = canonical_audio_sample_bytes(pcm_format);
    try {
        const auto samples = static_cast<std::size_t>(actual.frames_per_buffer) * actual.output_channels;
        float_buffer_.assign(samples, 0.0F);
        pcm_buffer_.assign(samples * sample_bytes, 0U);
        address_ = std::move(device_address);
    } catch (...) {
        api->pcm_close(pcm);
        dlclose(api->library);
        delete api;
        set_error("unable to allocate ALSA audio buffer");
        state_.store(AudioDeviceState::faulted, std::memory_order_release);
        return false;
    }

    api_ = api;
    pcm_ = pcm;
    requested_config_ = config;
    config_ = actual;
    sample_format_ = std::string(canonical_audio_sample_format_name(pcm_format));
    pcm_format_ = pcm_format;
    sample_bytes_ = sample_bytes;
    callback_ = callback;
    callback_context_ = callback_context;
    callback_count_.store(0, std::memory_order_relaxed);
    xruns_.store(0, std::memory_order_relaxed);
    first_write_ns_.store(0, std::memory_order_relaxed);
    last_write_ns_.store(0, std::memory_order_relaxed);
    max_excess_gap_ns_.store(0, std::memory_order_relaxed);
    frames_written_.store(0, std::memory_order_relaxed);
    stop_requested_.store(false, std::memory_order_relaxed);
    last_error_.clear();
    state_.store(AudioDeviceState::open, std::memory_order_release);
    return true;
#endif
}

bool AlsaAudioOutput::start() noexcept {
#if !defined(__linux__)
    return false;
#else
    if (state_.load(std::memory_order_acquire) != AudioDeviceState::open || !api_ || !pcm_ || !callback_) {
        return false;
    }
    stop_requested_.store(false, std::memory_order_release);
    try {
        thread_ = std::thread(&AlsaAudioOutput::render_loop, this);
    } catch (...) {
        set_error("unable to start ALSA playback thread");
        state_.store(AudioDeviceState::faulted, std::memory_order_release);
        return false;
    }
    state_.store(AudioDeviceState::running, std::memory_order_release);
    return true;
#endif
}

void AlsaAudioOutput::stop() noexcept {
    stop_requested_.store(true, std::memory_order_release);
    if (thread_.joinable()) {
        thread_.join();
    }
    if (state_.load(std::memory_order_acquire) == AudioDeviceState::running) {
        state_.store(AudioDeviceState::open, std::memory_order_release);
    }
}

void AlsaAudioOutput::close() noexcept {
    stop();
#if defined(__linux__)
    if (api_ && pcm_) {
        api_->pcm_close(pcm_);
    }
    pcm_ = nullptr;
    if (api_) {
        if (api_->library) dlclose(api_->library);
        delete api_;
        api_ = nullptr;
    }
#endif
    float_buffer_.clear();
    pcm_buffer_.clear();
    address_.clear();
    callback_ = nullptr;
    callback_context_ = nullptr;
    sample_format_ = "unknown";
    pcm_format_ = CanonicalAudioSampleFormat::float32;
    sample_bytes_ = sizeof(float);
    state_.store(AudioDeviceState::closed, std::memory_order_release);
}

bool AlsaAudioOutput::available() const noexcept {
    const auto value = state_.load(std::memory_order_acquire);
    return value == AudioDeviceState::open || value == AudioDeviceState::running;
}

AudioDeviceStatus AlsaAudioOutput::status() const noexcept {
    AudioDeviceStatus result{};
    result.state = state_.load(std::memory_order_acquire);
    result.config = config_;
    result.callback_count = callback_count_.load(std::memory_order_acquire);
    result.xruns = xruns_.load(std::memory_order_acquire);
    return result;
}

void AlsaAudioOutput::render_loop() noexcept {
#if defined(__linux__)
    const auto frames = config_.frames_per_buffer;
    const auto channels = config_.output_channels;
    while (!stop_requested_.load(std::memory_order_acquire)) {
        callback_(callback_context_, float_buffer_.data(), frames, channels);
        callback_count_.fetch_add(1, std::memory_order_relaxed);
        if (!encode_interleaved_pcm(float_buffer_.data(), pcm_format_, frames, channels, pcm_buffer_.data())) {
            set_error("ALSA playback PCM conversion failed");
            state_.store(AudioDeviceState::faulted, std::memory_order_release);
            stop_requested_.store(true, std::memory_order_release);
            break;
        }

        std::uint32_t offset = 0;
        while (offset < frames && !stop_requested_.load(std::memory_order_acquire)) {
            const auto* data = pcm_buffer_.data() + static_cast<std::size_t>(offset) * channels * sample_bytes_;
            const auto remaining = static_cast<unsigned long>(frames - offset);
            const long written = api_->pcm_writei(pcm_, data, remaining);
            if (written > 0) {
                const auto now_ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()).count());
                std::uint64_t expected_zero = 0;
                first_write_ns_.compare_exchange_strong(expected_zero, now_ns, std::memory_order_relaxed);
                const auto previous_ns = last_write_ns_.exchange(now_ns, std::memory_order_relaxed);
                if (previous_ns > 0 && now_ns > previous_ns && config_.sample_rate > 0.0) {
                    const auto expected_ns = static_cast<std::uint64_t>((static_cast<double>(written) / config_.sample_rate) * 1'000'000'000.0);
                    const auto delta_ns = now_ns - previous_ns;
                    const auto excess_ns = delta_ns > expected_ns ? delta_ns - expected_ns : 0;
                    auto current_max = max_excess_gap_ns_.load(std::memory_order_relaxed);
                    while (excess_ns > current_max && !max_excess_gap_ns_.compare_exchange_weak(current_max, excess_ns, std::memory_order_relaxed)) {}
                }
                frames_written_.fetch_add(static_cast<std::uint64_t>(written), std::memory_order_relaxed);
                offset += static_cast<std::uint32_t>(written);
                continue;
            }
            if (written < 0) {
                xruns_.fetch_add(1, std::memory_order_relaxed);
                const int recovered = api_->pcm_recover(pcm_, static_cast<int>(written), 1);
                if (recovered < 0) {
                    if (api_->strerror_fn_ptr) set_error(api_->strerror_fn_ptr(recovered));
                    else set_error("ALSA playback recovery failed");
                    state_.store(AudioDeviceState::faulted, std::memory_order_release);
                    stop_requested_.store(true, std::memory_order_release);
                    break;
                }
                api_->pcm_prepare(pcm_);
                continue;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        // ALSA's virtual "null" PCM consumes immediately rather than pacing
        // against hardware. Sleep one block duration so development tests do
        // not turn the render thread into a benchmark by accident.
        if (address_ == "null" && !stop_requested_.load(std::memory_order_acquire)) {
            const auto micros = static_cast<long long>(std::max(1.0, (static_cast<double>(frames) / config_.sample_rate) * 1'000'000.0));
            std::this_thread::sleep_for(std::chrono::microseconds(micros));
        }
    }
#endif
}

} // namespace stagemesh
