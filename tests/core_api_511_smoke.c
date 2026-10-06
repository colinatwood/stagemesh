#include "stagemesh/core_api.h"
#include <string.h>

int main(void) {
    sf_sampler_voice_engine_status status = {0};
    sf_sampler_sample_descriptor sample = {0};
    sf_native_midi_mapping mapping = {0};
    if (SF_API_VERSION_MAJOR(SF_CORE_API_VERSION) != 1u) return 1;
    if (SF_API_VERSION_MINOR(SF_CORE_API_VERSION) != 57u) return 2;
    if (strcmp(SF_EXT_SAMPLER_VOICE_ENGINE_V1, "org.upp.audio.sampler-voice-engine/1") != 0) return 3;
    status.struct_size = sizeof(status);
    sample.struct_size = sizeof(sample);
    mapping.struct_size = sizeof(mapping);
    mapping.resource_id = 42;
    mapping.action = SF_MIDI_ACTION_SAMPLE_TRIGGER;
    return status.physical_outputs_armed != 0 || sample.sample_id != 0 || mapping.resource_id != 42;
}
