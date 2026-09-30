#include "stagemesh/core_api.h"
#include <string.h>
int main(void){
 sf_transport_discipline_status transport={0};sf_midi_clock_status midi={0};
 if(SF_API_VERSION_MAJOR(SF_CORE_API_VERSION)!=1u)return 1;
 if(SF_API_VERSION_MINOR(SF_CORE_API_VERSION)!=58u)return 2;
 if(strcmp(SF_EXT_TRANSPORT_DISCIPLINE_V1,"org.upp.timing.transport-discipline/1")||strcmp(SF_EXT_MIDI_CLOCK_V1,"org.upp.midi.clock-24ppqn/1"))return 3;
 transport.struct_size=sizeof(transport);midi.struct_size=sizeof(midi);
 return transport.physical_outputs_armed||midi.physical_outputs_armed;
}
