#!/usr/bin/env python3
import json,sys
from pathlib import Path
script = Path(__file__).resolve()
source_backend = script.parents[1] / "backend"
installed_backend = script.parents[2] / "share" / "stagemesh" / "backend"
sys.path.insert(0,str(source_backend if source_backend.is_dir() else installed_backend))
from hardware_qualification import probe_platform
print(json.dumps(probe_platform(),indent=2,sort_keys=True))
