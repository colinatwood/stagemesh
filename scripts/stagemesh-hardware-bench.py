#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from hardware_bench import analyze_hardware_samples

def main():
    p=argparse.ArgumentParser(description="Analyze captured StageMesh LE-UWB timing evidence without arming outputs")
    p.add_argument("--input",type=Path,required=True,help="JSON Lines timing samples captured by an adapter")
    p.add_argument("--source",choices=("loopback","hardware"),default="loopback");p.add_argument("--duration-ms",type=int,default=0)
    p.add_argument("--uwb-device");p.add_argument("--le-controller");p.add_argument("--output",type=Path);a=p.parse_args()
    samples=[json.loads(line) for line in a.input.read_text("utf-8").splitlines() if line.strip()]
    report=analyze_hardware_samples(samples,source=a.source,duration_ms=a.duration_ms,uwb_device=a.uwb_device,le_controller=a.le_controller)
    encoded=json.dumps(report,indent=2)+"\n"
    if a.output:a.output.write_text(encoded,"utf-8")
    else:print(encoded,end="")
    return 0
if __name__=="__main__":raise SystemExit(main())
