#include "stagemesh/core_api.h"
#include <string.h>
int main(void){sf_realtime_audit_status s={0};if(SF_API_VERSION_MINOR(SF_CORE_API_VERSION)!=63u)return 1;if(strcmp(SF_EXT_REALTIME_AUDIT_V1,"org.upp.core.realtime-audit/1"))return 2;s.struct_size=sizeof(s);return s.physical_outputs_armed;}
