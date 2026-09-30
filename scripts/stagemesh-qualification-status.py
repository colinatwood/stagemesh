#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
script=Path(__file__).resolve();source=script.parents[1]/"backend";installed=script.parents[2]/"share/stagemesh/backend";sys.path.insert(0,str(source if source.is_dir() else installed))
from qualification_status import summarize_submissions

def main()->int:
    parser=argparse.ArgumentParser(description="Summarize StageMesh external qualification submissions for one exact-build plan")
    parser.add_argument("--plan",type=Path,required=True);parser.add_argument("--submissions-dir",type=Path,required=True)
    parser.add_argument("--review-key-file",type=Path,required=True);parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    try:
        plan=json.loads(args.plan.read_text())
        if not isinstance(plan,dict):raise ValueError("plan must contain a JSON object")
        value=summarize_submissions(plan=plan,submissions_root=args.submissions_dir,review_key_file=args.review_key_file)
    except Exception as exc:
        print(json.dumps({"accepted":False,"error":str(exc)},sort_keys=True));return 1
    payload=json.dumps(value,indent=2,sort_keys=True)+"\n"
    if args.output:args.output.write_text(payload)
    print(payload,end="");return 0
if __name__=="__main__":raise SystemExit(main())
