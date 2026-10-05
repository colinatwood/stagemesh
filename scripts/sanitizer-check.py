#!/usr/bin/env python3
"""Build and run native tests under ASan/UBSan without touching hardware."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--detect-leaks",action="store_true",help="enable LeakSanitizer; requires an untraced host with readable /proc")
    args=parser.parse_args()
    missing=[name for name in ("cmake","ctest") if shutil.which(name) is None]
    if missing:
        print("Missing sanitizer prerequisites: "+", ".join(missing),file=sys.stderr);return 1
    env=os.environ.copy();env["ASAN_OPTIONS"]=f"detect_leaks={1 if args.detect_leaks else 0}:halt_on_error=1:strict_string_checks=1";env["UBSAN_OPTIONS"]="halt_on_error=1:print_stacktrace=1"
    try:
        with tempfile.TemporaryDirectory(prefix="stageforge-sanitizer-") as temporary:
            build=Path(temporary)/"build"
            subprocess.run(["cmake","-S",str(ROOT),"-B",str(build),"-DCMAKE_BUILD_TYPE=Debug","-DSTAGEMESH_BUILD_TESTS=ON","-DSTAGEMESH_ENABLE_SANITIZERS=ON"],cwd=ROOT,check=True,env=env)
            subprocess.run(["cmake","--build",str(build),"--parallel","2"],cwd=ROOT,check=True,env=env)
            subprocess.run(["ctest","--test-dir",str(build),"--output-on-failure"],cwd=ROOT,check=True,env=env)
        suffix=" with leak detection" if args.detect_leaks else " (leak detection disabled; use --detect-leaks on an untraced host)"
        print("Native ASan/UBSan gate passed"+suffix+". Hardware execution remains disabled.");return 0
    except subprocess.CalledProcessError as exc:
        print(str(exc),file=sys.stderr);return 1

if __name__=="__main__":sys.exit(main())
