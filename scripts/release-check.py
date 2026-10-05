#!/usr/bin/env python3
"""Clean Linux developer-alpha gate. Does not publish or activate hardware."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def prerequisites():
    missing = [name for name in ("cmake", "ctest", "node") if shutil.which(name) is None]
    if missing:
        raise RuntimeError("Missing release prerequisites: " + ", ".join(missing))

def run(command, env=None):
    subprocess.run(command, cwd=ROOT, env=env, check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-prerequisites", action="store_true")
    args = parser.parse_args()
    try:
        prerequisites()
        if args.check_prerequisites:
            print("Release prerequisites available")
            return 0
        # Never reuse a developer build tree or delete user-selected paths.
        with tempfile.TemporaryDirectory(prefix="stageforge-release-") as temporary:
            build = Path(temporary) / "build"
            run(["cmake", "-S", str(ROOT), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                 "-DSTAGEMESH_BUILD_TESTS=ON", "-DSTAGEMESH_RT_QUALIFICATION=ON"])
            run(["cmake", "--build", str(build), "--parallel", "2"])
            run(["ctest", "--test-dir", str(build), "--output-on-failure"])
            engine = build / "native" / "stagemesh_engine"
            if not engine.is_file():
                raise RuntimeError("Fresh native engine missing; refusing Python fallback")
            env = os.environ.copy()
            env["STAGEMESH_NATIVE_ENGINE"] = str(engine)
            env["STAGEFORGE_REQUIRE_RT_QUALIFICATION"] = "1"
            env["STAGEFORGE_DATA_DIR"] = str(Path(temporary) / "data")
            run([sys.executable, str(ROOT / "scripts/release-python-tests.py")], env)
            run([sys.executable, str(ROOT / "scripts/automation-performance.py"), "--json"], env)
            for schema in sorted((ROOT / "schemas").glob("*.json")):
                json.loads(schema.read_text(encoding="utf-8"))
            for script in sorted((ROOT / "frontend").glob("*.js")):
                run(["node", "--check", str(script)])
        print("Developer-alpha software gate passed. Hardware and installer qualification remain separate.")
        return 0
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
