#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
script=Path(__file__).resolve();source=script.parents[1]/"backend";installed=script.parents[2]/"share/stagemesh/backend";sys.path.insert(0,str(source if source.is_dir() else installed))
from qualification_review import create_review,validate_review

def _read(path:Path):
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise ValueError(f"{path} must contain a JSON object")
    return value

def main()->int:
    parser=argparse.ArgumentParser(description="Verify and authenticate a StageMesh external qualification result")
    parser.add_argument("--plan",type=Path,required=True);parser.add_argument("--result",type=Path,required=True)
    parser.add_argument("--artifacts-dir",type=Path,required=True);parser.add_argument("--review-key-file",type=Path,required=True)
    parser.add_argument("--decision",choices=("approve","reject","needs-evidence"),required=True)
    parser.add_argument("--reviewed-at");parser.add_argument("--note",action="append",default=[]);parser.add_argument("--output",type=Path)
    parser.add_argument("--verify",type=Path,help="verify an existing review document instead of creating one")
    args=parser.parse_args()
    try:
        plan=_read(args.plan);result=_read(args.result)
        if args.verify:
            value=validate_review(plan=plan,result=result,review=_read(args.verify),review_key_file=args.review_key_file)
        else:
            value=create_review(plan=plan,result=result,artifact_root=args.artifacts_dir,review_key_file=args.review_key_file,
                                decision=args.decision,reviewed_at=args.reviewed_at,notes=args.note)
    except Exception as exc:
        print(json.dumps({"accepted":False,"error":str(exc)},sort_keys=True));return 1
    payload=json.dumps(value,indent=2,sort_keys=True)+"\n"
    if args.output:args.output.write_text(payload)
    print(payload,end="");return 0
if __name__=="__main__":raise SystemExit(main())
