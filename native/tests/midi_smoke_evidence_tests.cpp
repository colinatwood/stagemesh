#include "stagemesh/midi_smoke_evidence.hpp"

#include <iostream>
#include <stdexcept>

void require(bool condition) {
    if (!condition) throw std::runtime_error("MIDI evidence serialization contract failed");
}

int main() {
    const auto empty = stagemesh::midi_smoke_evidence("", "", 0, 0, false);
    require(empty.find("\"callbackDeliveryObserved\":false") != std::string::npos);
    require(empty.find("\"hardwareQualified\":false") != std::string::npos);
    const std::string hostile = "FLkey \"Mini\"\\\n\r\t";
    const auto observed = stagemesh::midi_smoke_evidence(hostile, hostile, 1, 2, false);
    require(observed.find("\"callbackDeliveryObserved\":true") != std::string::npos);
    require(observed.find("\"hardwareQualified\":false") != std::string::npos);
    require(observed.find("\"physicalOutputsArmed\":false") != std::string::npos);
    require(stagemesh::midi_evidence_json_string(std::string("\0\x1f", 2)) == "\"\\u0000\\u001f\"");
    require(stagemesh::midi_evidence_json_string("MIDI \xc3\xa9") == "\"MIDI \xc3\xa9\"");
    std::cout << observed << '\n';
    return 0;
}
