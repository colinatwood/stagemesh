#include "stagemesh/core_api.h"
#include <string.h>
int main(void){
 sf_daw_punch_capture_plan plan={0};sf_daw_punch_capture_status status={0};
 if(SF_API_VERSION_MAJOR(SF_CORE_API_VERSION)!=1u)return 1;
 if(SF_API_VERSION_MINOR(SF_CORE_API_VERSION)!=59u)return 2;
 if(strcmp(SF_EXT_DAW_PUNCH_CAPTURE_V1,"org.upp.daw.punch-loop-capture/1"))return 3;
 plan.struct_size=sizeof(plan);status.struct_size=sizeof(status);
 return status.physical_outputs_armed;
}
