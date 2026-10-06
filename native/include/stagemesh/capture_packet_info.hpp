#pragma once

namespace stagemesh {

// Capture metadata travels with a borrowed endpoint packet until the bounded
// engine ingress has copied its samples. It is not retained by the callback.
struct CapturePacketInfo {
    bool discontinuity = false;
    bool timestamp_valid = false;
    double sample_position = 0;
};

} // namespace stagemesh
