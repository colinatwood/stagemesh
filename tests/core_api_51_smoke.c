#include "stagemesh/core_api.h"
#include <string.h>

int main(void) {
    sf_native_midi_performance_status status = {0};
    sf_native_midi_mapping mapping = {0};
    if (SF_API_VERSION_MAJOR(SF_CORE_API_VERSION) != 1u) return 1;
    if (SF_API_VERSION_MINOR(SF_CORE_API_VERSION) != 56u) return 2;
    if (strcmp(SF_EXT_NATIVE_MIDI_PERFORMANCE_V1, "org.upp.midi.native-performance/1") != 0) return 3;
    status.struct_size = sizeof(status);
    mapping.struct_size = sizeof(mapping);
    mapping.message = SF_MIDI_MAP_CC;
    mapping.behavior = SF_MIDI_MAP_ABSOLUTE;
    mapping.action = SF_MIDI_ACTION_AUTOMATION;
    return status.physical_outputs_armed != 0 || mapping.parameter_id != 0;
}
