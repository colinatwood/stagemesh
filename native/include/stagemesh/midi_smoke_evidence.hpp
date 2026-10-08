#pragma once

#include <cstdint>
#include <sstream>
#include <string>
#include <string_view>

namespace stagemesh {

inline std::string midi_evidence_json_string(std::string_view value) {
    constexpr char hex[] = "0123456789abcdef";
    std::string result = "\"";
    for (unsigned char byte : value) {
        if (byte == '"' || byte == '\\') {
            result += '\\';
            result += static_cast<char>(byte);
        } else if (byte < 0x20) {
            result += "\\u00";
            result += hex[byte >> 4];
            result += hex[byte & 0x0f];
        } else {
            result += static_cast<char>(byte);
        }
    }
    result += '"';
    return result;
}

inline std::string midi_smoke_evidence(std::string_view endpoint, std::string_view matched,
                                      std::uint64_t events, std::uint64_t callbacks,
                                      bool physical_outputs_armed) {
    std::ostringstream output;
    output << std::boolalpha
           << "{\"endpointName\":" << midi_evidence_json_string(endpoint)
           << ",\"matchedName\":" << midi_evidence_json_string(matched)
           << ",\"attached\":true,\"eventsObserved\":" << events
           << ",\"callbackMessages\":" << callbacks
           << ",\"physicalOutputsArmed\":" << physical_outputs_armed
           << ",\"callbackDeliveryObserved\":" << (events > 0)
           << ",\"hardwareQualified\":false}";
    return output.str();
}

} // namespace stagemesh
