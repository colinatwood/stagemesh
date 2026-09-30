#!/usr/bin/env python3
"""Audit StageMesh reviewed driver-catalog freshness without contacting vendors."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

script=Path(__file__).resolve()
source=script.parents[1]/"backend"
installed=script.parents[2]/"share"/"stagemesh"/"backend"
sys.path.insert(0,str(source if source.is_dir() else installed))
from driver_compatibility import audit_catalog

def main()->int:
    parser=argparse.ArgumentParser()
    default_catalog=(script.parents[1]/"packaging"/"driver-catalog.json") if source.is_dir() else (script.parents[2]/"share"/"stagemesh"/"packaging"/"driver-catalog.json")
    parser.add_argument("--catalog",default=str(default_catalog))
    parser.add_argument("--as-of",help="ISO date used for deterministic review checks")
    parser.add_argument("--warn-days",type=int,default=30)
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    try:as_of=date.fromisoformat(args.as_of) if args.as_of else None
    except ValueError:parser.error("--as-of must be YYYY-MM-DD")
    report=audit_catalog(Path(args.catalog),as_of=as_of,warn_days=args.warn_days)
    if args.json:print(json.dumps(report,sort_keys=True))
    else:
        c=report["counts"];print(f"driver catalog: total={c['total']} current={c['current']} due={c['reviewDue']} stale={c['stale']} unreviewed={c['unreviewed']} invalid={c['invalid']}")
        for item in report["entries"]:
            if item["reviewDue"]:print(f"REVIEW {item.get('hardwareId','?')} {item.get('product','?')} state={item['reviewState']} days={item['daysUntilExpiry']}")
    return 0 if report["catalogUsable"] else 1

if __name__=="__main__":raise SystemExit(main())
