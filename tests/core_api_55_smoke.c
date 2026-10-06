#include "stagemesh/core_api.h"
#include <string.h>
int main(void){sf_plugin_delay_graph_status s={0};if(SF_API_VERSION_MINOR(SF_CORE_API_VERSION)!=62u)return 1;if(strcmp(SF_EXT_PLUGIN_DELAY_GRAPH_V1,"org.upp.audio.plugin-delay-graph/1"))return 2;s.struct_size=sizeof(s);return s.physical_outputs_armed;}
