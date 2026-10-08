#!/usr/bin/env python3
"""Collect read-only host provenance for later native audio/MIDI evidence review.

Never executes the supplied binary, opens audio/MIDI streams, or interprets a
saved transcript as a test pass. A source snapshot does not prove binary origin.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from hardware_diagnostics import diagnose_hardware


def file_observation(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"evidence input is not a file: {path.name}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    if not size:
        raise ValueError(f"evidence input is empty: {path.name}")
    return {"name": path.name, "bytes": size, "sha256": digest.hexdigest()}


def source_observation(root: Path) -> dict:
    # Use the script's repository, not the shell's working directory.
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True, timeout=20).stdout.strip()
    commit = git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("source commit is invalid")
    dirty = bool(git("status", "--porcelain", "--untracked-files=all"))
    return {"commit": commit, "worktreeDirty": dirty}


def collect(root: Path, binary: Path, transcripts: list[Path]) -> dict:
    binary_info = file_observation(binary)
    artifacts = [file_observation(path) for path in transcripts]
    source = source_observation(root)
    inventory = diagnose_hardware()
    return {
        "documentType": "org.stagemesh.native-host-evidence",
        "schemaVersion": 1,
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "host": {"os": platform.system(), "release": platform.release(),
                 "version": platform.version(), "architecture": platform.machine()},
        "source": source,
        "binary": binary_info,
        "savedTranscripts": artifacts,
        "hardwareInventory": inventory,
        "evidenceBoundary": {
            "readOnlyCollection": True,
            "binaryExecuted": False,
            "audioCaptured": False,
            "physicalOutputsArmed": False,
            "binarySourceBindingVerified": False,
            "transcriptSourceBindingVerified": False,
            "testsPassedInferred": False,
            "ownerReviewComplete": False,
            "physicalHardwareQualified": False,
            "statement": "Hashes identify observed files only; neither file origin nor test success is inferred.",
        },
        "ownerInputsStillRequired": [
            "Build the named binary from the recorded source and preserve the build transcript.",
            "Confirm saved test transcripts belong to that build and record each test exit code and opt-in.",
            "Record device firmware, control-panel version, OS edition and endpoint format/exclusive-mode settings.",
            "Record analog versus loopback capture, exact cables/adapters, routing and gain settings.",
            "Provide separate real MIDI event/hotplug and reviewed audio quality evidence.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    temporary = None
    try:
        inputs = {args.binary.resolve(), *(path.resolve() for path in args.transcript)}
        output = args.output.resolve()
        if output in inputs:
            raise ValueError("output must not overwrite an input file")
        if output.exists():
            raise ValueError("output already exists; use a new session filename")
        report = collect(ROOT, args.binary, args.transcript)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=output.name + ".", suffix=".tmp", delete=False) as target:
            temporary = Path(target.name)
            json.dump(report, target, indent=2, sort_keys=True, allow_nan=False)
            target.write("\n")
        os.replace(temporary, output)
        temporary = None
        print(f"Read-only native host evidence saved to {args.output}")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Native host evidence collection failed: {error}", file=sys.stderr)
        return 2
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
