#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
script=Path(__file__).resolve();source=script.parents[1]/"backend";installed=script.parents[2]/"share/stagemesh/backend";sys.path.insert(0,str(source if source.is_dir() else installed))
from qualification_bundle import create_plan,result_template

def main()->int:
    parser=argparse.ArgumentParser(description="Generate an exact-build StageMesh external qualification plan")
    parser.add_argument("--build-dir",default=os.environ.get("STAGEMESH_BUILD_DIR",str(script.parents[1]/"build")))
    parser.add_argument("--output",type=Path)
    parser.add_argument("--template",help="emit a result template for one task instead of the full plan")
    args=parser.parse_args();root=script.parents[1] if source.is_dir() else script.parents[2]/"share/stagemesh";engine=Path(args.build_dir)/"native/stagemesh_engine"
    try:
        plan=create_plan(root=root,engine_path=engine);value=result_template(plan,args.template) if args.template else plan
    except Exception as exc:
        print(json.dumps({"passed":False,"error":str(exc)}));return 1
    payload=json.dumps(value,indent=2,sort_keys=True)+"\n"
    if args.output:args.output.write_text(payload)
    print(payload,end="");return 0
if __name__=="__main__":raise SystemExit(main())
