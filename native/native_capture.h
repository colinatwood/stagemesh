#pragma once
#include "native_endpoint_stream.h"
namespace stagemesh {
class NativeCaptureStream final : public NativeEndpointStream {
public:
    explicit NativeCaptureStream(CaptureReceive receive = nullptr, void* context = nullptr)
        : NativeEndpointStream(AudioDirection::Capture, nullptr, receive, context) {}
};
}
