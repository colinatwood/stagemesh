#!/usr/bin/env python3
"""Build target-tagged Tauri sidecars for the StageMesh desktop package."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
BINARY_DIR = ROOT / "desktop" / "src-tauri" / "binaries"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Rust target triple used by Tauri")
    parser.add_argument("--native-engine", required=True, type=Path)
    args = parser.parse_args()

    engine = args.native_engine.resolve()
    if not engine.is_file():
        parser.error(f"native engine does not exist: {engine}")

    extension = ".exe" if engine.suffix.lower() == ".exe" else ""
    BINARY_DIR.mkdir(parents=True, exist_ok=True)
    runtime_target = BINARY_DIR / f"stagemesh-runtime-{args.target}{extension}"
    engine_target = BINARY_DIR / f"stagemesh_engine-{args.target}{extension}"

    with tempfile.TemporaryDirectory(prefix="stagemesh-desktop-runtime-") as temporary:
        scratch = Path(temporary)
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--onefile",
            "--name",
            "stagemesh-runtime",
            "--paths",
            str(ROOT / "backend"),
            "--add-data",
            f"{ROOT / 'packaging' / 'driver-catalog.json'}{';' if sys.platform == 'win32' else ':'}packaging",
            "--distpath",
            str(scratch / "dist"),
            "--workpath",
            str(scratch / "work"),
            "--specpath",
            str(scratch / "spec"),
            str(ROOT / "backend" / "dev_server.py"),
        ]
        subprocess.run(command, cwd=ROOT, check=True)
        built_runtime = scratch / "dist" / f"stagemesh-runtime{extension}"
        if not built_runtime.is_file():
            raise RuntimeError(f"PyInstaller did not create {built_runtime}")
        shutil.copy2(built_runtime, runtime_target)
    shutil.copy2(engine, engine_target)
    print(runtime_target.relative_to(ROOT))
    print(engine_target.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
