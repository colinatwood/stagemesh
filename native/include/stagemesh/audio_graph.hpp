#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <span>

namespace stagemesh {

constexpr std::size_t audio_graph_max_sources = 32;
constexpr std::size_t audio_graph_max_outputs = 16;

struct AudioSourceBlock {
    std::uint8_t source{0};
    const float* left{nullptr};
    const float* right{nullptr};
};

struct AudioOutputBlock {
    std::uint8_t output{0};
    float* left{nullptr};
    float* right{nullptr};
};

struct AudioGraphOutputMeter { float peak{0.0F}; float gain_reduction_db{0.0F}; };
struct AudioRouteChange { std::uint8_t source{0}; std::uint8_t output{0}; float linear_gain{0.0F}; };
using AudioOutputEffectFn = void (*)(void*, std::uint8_t, float*, float*, std::size_t) noexcept;

// Fixed-capacity routing matrix intended for the real-time audio thread.
// Route matrices are RCU-published as one immutable generation so a multi-route
// control transaction cannot be observed halfway through by an audio callback.
// Masters/limiter controls remain independent atomics. Route writers are
// control/show-loop operations; process() is wait-free with respect to writers.
class AudioGraph {
public:
    AudioGraph() noexcept;

    void set_route_gain(std::uint8_t source, std::uint8_t output, float linear_gain) noexcept;
    [[nodiscard]] bool apply_route_transaction(std::span<const AudioRouteChange> changes) noexcept;
    [[nodiscard]] float route_gain(std::uint8_t source, std::uint8_t output) const noexcept;

    void set_output_master(std::uint8_t output, float linear_gain) noexcept;
    [[nodiscard]] float output_master(std::uint8_t output) const noexcept;

    void set_limiter_ceiling_db(std::uint8_t output, float ceiling_db) noexcept;
    [[nodiscard]] float limiter_ceiling_db(std::uint8_t output) const noexcept;

    void process(std::span<const AudioSourceBlock> sources, std::span<AudioOutputBlock> outputs, std::size_t frames,
                 AudioOutputEffectFn effect = nullptr, void* effect_context = nullptr) noexcept;
    [[nodiscard]] AudioGraphOutputMeter meter(std::uint8_t output) const noexcept;

private:
    using RouteMatrix = std::array<std::array<float, audio_graph_max_outputs>, audio_graph_max_sources>;
    struct OutputState {
        std::atomic<float> master{1.0F};
        std::atomic<float> ceiling_db{-1.0F};
        std::atomic<float> peak{0.0F};
        std::atomic<float> gain_reduction_db{0.0F};
        float limiter_gain{1.0F};
    };

    [[nodiscard]] static float clamp_gain(float gain) noexcept;
    [[nodiscard]] static float db_to_linear(float db) noexcept;
    [[nodiscard]] static float linear_to_db(float linear) noexcept;
    [[nodiscard]] std::uint8_t pin_routes() const noexcept;
    void unpin_routes(std::uint8_t slot) const noexcept;

    std::array<RouteMatrix, 2> route_slots_{};
    mutable std::array<std::atomic<std::uint32_t>, 2> route_readers_{};
    std::atomic<std::uint8_t> active_route_slot_{0};
    std::atomic_flag route_writer_ = ATOMIC_FLAG_INIT;
    std::array<OutputState, audio_graph_max_outputs> outputs_{};
};

} // namespace stagemesh
