#!/usr/bin/env python3
"""Print a read-only USB PnP diagnosis and OS-specific driver lookup links."""
import json
import sys
from pathlib import Path

script = Path(__file__).resolve()
source = script.parents[1] / "backend"
installed = script.parents[2] / "share" / "stagemesh" / "backend"
sys.path.insert(0, str(source if source.is_dir() else installed))
from hardware_diagnostics import diagnose_hardware

if __name__ == "__main__":
    print(json.dumps(diagnose_hardware(), indent=2))
