#include "stagemesh/core_api.h"
#include <string.h>
int main(void){
 sf_stage_launcher_status status={0};
 if(SF_API_VERSION_MAJOR(SF_CORE_API_VERSION)!=1u)return 1;
 if(SF_API_VERSION_MINOR(SF_CORE_API_VERSION)!=60u)return 2;
 if(strcmp(SF_EXT_STAGE_LAUNCHER_V1,"org.upp.stage.launcher-projection/1"))return 3;
 status.struct_size=sizeof(status);return status.physical_outputs_armed;
}
