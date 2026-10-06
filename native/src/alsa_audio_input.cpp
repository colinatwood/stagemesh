#include "stagemesh/alsa_audio_input.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <new>

#if defined(__linux__)
#include <dlfcn.h>
#endif

namespace stagemesh {

namespace {
bool valid_config(const AudioDeviceConfig& config) noexcept {
    return std::isfinite(config.sample_rate) && config.sample_rate >= 8000.0 && config.sample_rate <= 384000.0 &&
           config.input_channels >= 1 && config.input_channels <= 32 &&
           config.frames_per_buffer >= 16 && config.frames_per_buffer <= 8192;
}
}

struct AlsaAudioInput::Api {
#if defined(__linux__)
    void* library{nullptr};
    using pcm_open_fn = int (*)(void**, const char*, int, int);
    using pcm_close_fn = int (*)(void*);
    using pcm_set_params_fn = int (*)(void*, int, int, unsigned int, unsigned int, int, unsigned int);
    using hw_params_malloc_fn = int (*)(void**); using hw_params_free_fn = void (*)(void*);
    using hw_params_current_fn = int (*)(void*, void*); using hw_params_get_rate_fn = int (*)(const void*, unsigned int*, int*);
    using hw_params_get_channels_fn = int (*)(const void*, unsigned int*); using hw_params_get_period_size_fn = int (*)(const void*, unsigned long*, int*);
    using hw_params_get_format_fn = int (*)(const void*, int*);
    using format_value_fn = int (*)(const char*);
    using pcm_readi_fn = long (*)(void*, void*, unsigned long);
    using pcm_recover_fn = int (*)(void*, int, int);
    using pcm_prepare_fn = int (*)(void*);
    using pcm_drop_fn = int (*)(void*);
    using strerror_fn = const char* (*)(int);
    pcm_open_fn pcm_open{nullptr};
    pcm_close_fn pcm_close{nullptr};
    pcm_set_params_fn pcm_set_params{nullptr};
    hw_params_malloc_fn hw_params_malloc{nullptr}; hw_params_free_fn hw_params_free{nullptr}; hw_params_current_fn hw_params_current{nullptr};
    hw_params_get_rate_fn hw_params_get_rate{nullptr}; hw_params_get_channels_fn hw_params_get_channels{nullptr}; hw_params_get_period_size_fn hw_params_get_period_size{nullptr}; hw_params_get_format_fn hw_params_get_format{nullptr};
    format_value_fn format_value{nullptr};
    pcm_readi_fn pcm_readi{nullptr};
    pcm_recover_fn pcm_recover{nullptr};
    pcm_prepare_fn pcm_prepare{nullptr};
    pcm_drop_fn pcm_drop{nullptr};
    strerror_fn strerror_fn_ptr{nullptr};
#endif
};

AlsaAudioInput::~AlsaAudioInput() { close(); }

void AlsaAudioInput::set_error(const char* text) noexcept {
    try { last_error_ = text ? text : "unknown ALSA error"; } catch (...) { last_error_.clear(); }
}

bool AlsaAudioInput::open(std::string device_address, const AudioDeviceConfig& config, AudioCaptureCallback callback, void* context,
                          std::string_view sample_format) noexcept {
    close();
    CanonicalAudioSampleFormat pcm_format{};
    if (!valid_config(config) || device_address.empty() || !callback ||
        !canonical_audio_sample_format_from_name(sample_format, pcm_format)) {
        set_error("invalid ALSA capture configuration");
        state_.store(AudioDeviceState::faulted, std::memory_order_release);
        return false;
    }
#if !defined(__linux__)
    (void)device_address; (void)config; (void)callback; (void)context; (void)sample_format;
    set_error("ALSA backend is only available on Linux");
    state_.store(AudioDeviceState::faulted, std::memory_order_release);
    return false;
#else
    auto* api = new (std::nothrow) Api{};
    if (!api) { set_error("unable to allocate ALSA capture state"); return false; }
    api->library = dlopen("libasound.so.2", RTLD_NOW | RTLD_LOCAL);
    if (!api->library) { delete api; set_error("libasound.so.2 unavailable"); return false; }
#define SF_ALSA_LOAD(member, symbol) \
    api->member = reinterpret_cast<Api::member##_fn>(dlsym(api->library, symbol)); \
    if (!api->member) { dlclose(api->library); delete api; set_error("required ALSA symbol unavailable: " symbol); state_.store(AudioDeviceState::faulted); return false; }
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
    SF_ALSA_LOAD(pcm_readi, "snd_pcm_readi")
    SF_ALSA_LOAD(pcm_recover, "snd_pcm_recover")
    SF_ALSA_LOAD(pcm_prepare, "snd_pcm_prepare")
    SF_ALSA_LOAD(pcm_drop, "snd_pcm_drop")
#undef SF_ALSA_LOAD
    api->strerror_fn_ptr = reinterpret_cast<Api::strerror_fn>(dlsym(api->library, "snd_strerror"));

    void* pcm = nullptr;
    // snd_pcm_stream_t capture == 1.
    int result = api->pcm_open(&pcm, device_address.c_str(), 1, 0);
    if (result < 0 || !pcm) {
        set_error(api->strerror_fn_ptr ? api->strerror_fn_ptr(result) : "snd_pcm_open capture failed");
        dlclose(api->library); delete api; state_.store(AudioDeviceState::faulted); return false;
    }
    const auto channels = static_cast<unsigned int>(config.input_channels);
    const auto rate = static_cast<unsigned int>(std::llround(config.sample_rate));
    const auto buffer_us = static_cast<unsigned int>(std::clamp((static_cast<double>(config.frames_per_buffer) / config.sample_rate) * 2'000'000.0, 2'000.0, 500'000.0));
    const auto requested_format_name = canonical_audio_sample_format_name(pcm_format);
    const int requested_format = api->format_value(requested_format_name.data());
    if (requested_format < 0) {
        set_error("requested ALSA capture format is unavailable");
        api->pcm_close(pcm); dlclose(api->library); delete api; state_.store(AudioDeviceState::faulted); return false;
    }
    result = api->pcm_set_params(pcm, requested_format, 3, channels, rate, 1, buffer_us);
    if (result < 0) {
        set_error(api->strerror_fn_ptr ? api->strerror_fn_ptr(result) : "snd_pcm_set_params capture failed");
        api->pcm_close(pcm); dlclose(api->library); delete api; state_.store(AudioDeviceState::faulted); return false;
    }
    AudioDeviceConfig actual=config; void* current=nullptr; unsigned int actual_rate=0,actual_channels=0; unsigned long actual_period=0; int direction=0,actual_format=-1;
    result=api->hw_params_malloc(&current);
    if(result>=0&&current)result=api->hw_params_current(pcm,current);
    if(result>=0)result=api->hw_params_get_rate(current,&actual_rate,&direction);
    if(result>=0)result=api->hw_params_get_channels(current,&actual_channels);
    if(result>=0)result=api->hw_params_get_period_size(current,&actual_period,&direction);
    if(result>=0)result=api->hw_params_get_format(current,&actual_format);
    if(current)api->hw_params_free(current);
    if(result<0||actual_format!=requested_format||actual_rate<8000||actual_rate>384000||actual_channels<1||actual_channels>32||actual_period<16||actual_period>8192){set_error("unable to query configured ALSA capture parameters");api->pcm_close(pcm);dlclose(api->library);delete api;state_.store(AudioDeviceState::faulted);return false;}
    actual.sample_rate=actual_rate;actual.input_channels=actual_channels;actual.frames_per_buffer=static_cast<std::uint32_t>(actual_period);
    const auto sample_bytes = canonical_audio_sample_bytes(pcm_format);
    try {
        const auto samples = static_cast<std::size_t>(actual.frames_per_buffer) * actual.input_channels;
        float_buffer_.assign(samples, 0.0F);
        pcm_buffer_.assign(samples * sample_bytes, 0U);
        address_ = std::move(device_address);
    } catch (...) {
        api->pcm_close(pcm); dlclose(api->library); delete api; set_error("unable to allocate ALSA capture buffer"); return false;
    }
    api_ = api; pcm_ = pcm; requested_config_=config;config_ = actual;
    sample_format_=std::string(canonical_audio_sample_format_name(pcm_format)); pcm_format_=pcm_format; sample_bytes_=sample_bytes;
    callback_ = callback; callback_context_ = context;
    callback_count_.store(0); xruns_.store(0); stop_requested_.store(false); last_error_.clear();
    state_.store(AudioDeviceState::open, std::memory_order_release);
    return true;
#endif
}

bool AlsaAudioInput::start() noexcept {
#if !defined(__linux__)
    return false;
#else
    if (state_.load(std::memory_order_acquire) != AudioDeviceState::open || !api_ || !pcm_ || !callback_) return false;
    stop_requested_.store(false, std::memory_order_release);
    try { thread_ = std::thread(&AlsaAudioInput::capture_loop, this); }
    catch (...) { set_error("unable to start ALSA capture thread"); state_.store(AudioDeviceState::faulted); return false; }
    state_.store(AudioDeviceState::running, std::memory_order_release);
    return true;
#endif
}

void AlsaAudioInput::stop() noexcept {
    stop_requested_.store(true, std::memory_order_release);
#if defined(__linux__)
    if (api_ && pcm_) api_->pcm_drop(pcm_);
#endif
    if (thread_.joinable()) thread_.join();
    if (state_.load(std::memory_order_acquire) == AudioDeviceState::running) state_.store(AudioDeviceState::open, std::memory_order_release);
}

void AlsaAudioInput::close() noexcept {
    stop();
#if defined(__linux__)
    if (api_ && pcm_) api_->pcm_close(pcm_);
    pcm_ = nullptr;
    if (api_) { if (api_->library) dlclose(api_->library); delete api_; api_ = nullptr; }
#endif
    float_buffer_.clear(); pcm_buffer_.clear(); address_.clear(); sample_format_="unknown";
    pcm_format_=CanonicalAudioSampleFormat::float32; sample_bytes_=sizeof(float); callback_ = nullptr; callback_context_ = nullptr;
    state_.store(AudioDeviceState::closed, std::memory_order_release);
}

bool AlsaAudioInput::available() const noexcept {
    const auto state = state_.load(std::memory_order_acquire);
    return state == AudioDeviceState::open || state == AudioDeviceState::running;
}

AudioDeviceStatus AlsaAudioInput::status() const noexcept {
    return {state_.load(std::memory_order_acquire), config_, callback_count_.load(std::memory_order_acquire), xruns_.load(std::memory_order_acquire)};
}

void AlsaAudioInput::capture_loop() noexcept {
#if defined(__linux__)
    const auto frames = config_.frames_per_buffer;
    const auto channels = config_.input_channels;
    while (!stop_requested_.load(std::memory_order_acquire)) {
        const long read = api_->pcm_readi(pcm_, pcm_buffer_.data(), frames);
        if (read > 0) {
            const auto read_frames = static_cast<std::uint32_t>(read);
            if (!decode_interleaved_pcm(pcm_buffer_.data(), pcm_format_, read_frames, channels, float_buffer_.data())) {
                set_error("ALSA capture PCM conversion failed");
                state_.store(AudioDeviceState::faulted, std::memory_order_release);
                stop_requested_.store(true, std::memory_order_release);
                break;
            }
            callback_(callback_context_, float_buffer_.data(), read_frames, channels);
            callback_count_.fetch_add(1, std::memory_order_relaxed);
            continue;
        }
        if (read < 0) {
            xruns_.fetch_add(1, std::memory_order_relaxed);
            const int recovered = api_->pcm_recover(pcm_, static_cast<int>(read), 1);
            if (recovered < 0) {
                set_error(api_->strerror_fn_ptr ? api_->strerror_fn_ptr(recovered) : "ALSA capture recovery failed");
                state_.store(AudioDeviceState::faulted, std::memory_order_release);
                stop_requested_.store(true, std::memory_order_release);
                break;
            }
            api_->pcm_prepare(pcm_);
        } else {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
#endif
}

} // namespace stagemesh
