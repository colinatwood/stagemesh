#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
script=Path(__file__).resolve();source=script.parents[1]/"backend";installed=script.parents[2]/"share/stagemesh/backend";sys.path.insert(0,str(source if source.is_dir() else installed))
from device_permissions import qualify_device_permissions

def main()->int:
    parser=argparse.ArgumentParser(description="Verify explicit StageMesh device nodes as the service identity")
    parser.add_argument("--service-user",default="stagemesh")
    parser.add_argument("--device",action="append",default=[],help="absolute device path optionally suffixed with :r, :w or :rw")
    args=parser.parse_args()
    try:value=qualify_device_permissions(service_user=args.service_user,device_specs=args.device)
    except Exception as exc:
        print(json.dumps({"qualification":"service-device-permissions","passed":False,"error":str(exc),"physicalOutputsArmed":False},sort_keys=True));return 1
    print(json.dumps(value,sort_keys=True));return 0 if value["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
