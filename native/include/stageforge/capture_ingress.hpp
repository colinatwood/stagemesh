#pragma once

#include <algorithm>
#include <atomic>
#include <cstddef>
#include <cmath>
#include <cstdint>
#include "stageforge/capture_packet_info.hpp"

namespace stageforge {

struct CaptureIngressResult {
    std::uint64_t blocks{0};
    std::uint64_t rejected{0};
    std::uint64_t nonfinite_samples{0};
};

// Shared non-blocking handoff used by native endpoint callbacks and the Linux
// ALSA reader. The borrowed input is consumed synchronously and never retained.
// A native discontinuity reserves a sequence number so the recording consumer
// can preserve it as an explicit gap in its take evidence.
template <class Ring, class RecordingQueue>
CaptureIngressResult submit_capture_packet(
    Ring& ring,
    RecordingQueue* recording,
    std::size_t recording_track,
    std::atomic<std::uint64_t>& sequence,
    std::atomic<std::uint64_t>& show_frame,
    const std::atomic<std::uint64_t>& generation,
    const float* interleaved,
    std::uint32_t frames,
    std::uint32_t channels,
    bool discontinuity = false) noexcept {
    CaptureIngressResult result{};
    if (!interleaved || frames == 0 || channels == 0) return result;

    (void)ring.push_interleaved(interleaved, frames, channels);
    if (!recording) return result;

    if (discontinuity) sequence.fetch_add(1, std::memory_order_relaxed);
    using Block = typename RecordingQueue::Block;
    constexpr std::uint32_t block_frames = Block{}.left.size();
    for (std::uint32_t offset = 0; offset < frames; offset += block_frames) {
        const auto amount = std::min(block_frames, frames - offset);
        Block block{};
        block.generation = generation.load(std::memory_order_acquire);
        block.sequence = sequence.fetch_add(1, std::memory_order_relaxed) + 1;
        block.show_frame = show_frame.fetch_add(amount, std::memory_order_relaxed);
        block.frames = amount;
        for (std::uint32_t index = 0; index < amount; ++index) {
            const float raw_left = interleaved[(offset + index) * channels];
            const float raw_right = channels > 1 ? interleaved[(offset + index) * channels + 1] : raw_left;
            block.left[index] = std::isfinite(raw_left) ? raw_left : 0.0F;
            block.right[index] = std::isfinite(raw_right) ? raw_right : 0.0F;
            result.nonfinite_samples += !std::isfinite(raw_left) ? 1U : 0U;
            result.nonfinite_samples += !std::isfinite(raw_right) ? 1U : 0U;
        }
        ++result.blocks;
        if (!recording->submit(recording_track, block)) ++result.rejected;
    }
    return result;
}

template <class Ring, class RecordingQueue>
CaptureIngressResult submit_capture_packet(
    Ring& ring,
    RecordingQueue* recording,
    std::size_t recording_track,
    std::atomic<std::uint64_t>& sequence,
    std::atomic<std::uint64_t>& show_frame,
    const std::atomic<std::uint64_t>& generation,
    const float* interleaved,
    std::uint32_t frames,
    std::uint32_t channels,
    const CapturePacketInfo& info) noexcept {
    return submit_capture_packet(ring, recording, recording_track, sequence, show_frame,
        generation, interleaved, frames, channels, info.discontinuity);
}

} // namespace stageforge
