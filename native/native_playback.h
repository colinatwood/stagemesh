#pragma once
#include "native_endpoint_stream.h"
namespace stagemesh {
using PlaybackStats = EndpointStreamStats;
class NativePlaybackStream final : public NativeEndpointStream {
public:
    explicit NativePlaybackStream(PlaybackRender render = nullptr, void* context = nullptr)
        : NativeEndpointStream(AudioDirection::Playback, render, nullptr, context) {}
};
}
