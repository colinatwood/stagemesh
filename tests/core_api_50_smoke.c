#include "stagemesh/core_api.h"
#include <string.h>

int main(void) {
    if (SF_API_VERSION_MAJOR(SF_CORE_API_VERSION) != 1u) return 1;
    if (SF_API_VERSION_MINOR(SF_CORE_API_VERSION) != 55u) return 2;
    if (strcmp(SF_EXT_MIDI_LEARN_MAPPING_V1, "org.upp.midi.learn-mapping/1") != 0) return 3;
    if (strcmp(SF_EXT_MASTER_MUSICAL_SYNC_V1, "org.upp.midi.master-musical-sync/1") != 0) return 4;
    return 0;
}
