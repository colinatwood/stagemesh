#include "stagemesh/core_api.h"
#include <string.h>
int main(void){sf_streaming_sample_bank_status s={0};if(SF_API_VERSION_MINOR(SF_CORE_API_VERSION)!=61u)return 1;if(strcmp(SF_EXT_STREAMING_SAMPLE_BANK_V1,"org.upp.audio.streaming-sample-bank/1"))return 2;s.struct_size=sizeof(s);return s.disk_io_in_audio_callback||s.physical_outputs_armed;}
