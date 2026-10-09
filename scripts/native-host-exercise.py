#!/usr/bin/env python3
"""Run one native smoke binary and atomically bind its transcript to the run.

This helper records process execution evidence. It does not prove that the
binary was built from the observed source or qualify physical hardware.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_PATH = ROOT / "scripts" / "native-host-evidence.py"
SPEC = importlib.util.spec_from_file_location("native_host_evidence", COLLECTOR_PATH)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)

ALLOWED_OPT_INS = {
    "STAGEMESH_ALLOW_ENDPOINT_CAPTURE_TEST",
    "STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST",
    "STAGEMESH_ALLOW_UNAVAILABLE_NATIVE_MIDI",
    "STAGEMESH_HOSTED_CAPTURE_AUTHORIZED",
    "STAGEMESH_MIDI_DEVICE_NAME",
}


def parse_opt_ins(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        name, separator, value = item.partition("=")
        if not separator or name not in ALLOWED_OPT_INS or not value:
            raise ValueError(
                "opt-in must be a non-empty NAME=VALUE using one of: "
                + ", ".join(sorted(ALLOWED_OPT_INS))
            )
        if name in result:
            raise ValueError(f"opt-in is repeated: {name}")
        if "\x00" in value:
            raise ValueError(f"opt-in contains a null byte: {name}")
        result[name] = value
    return result


def exercise(binary: Path, arguments: list[str], opt_ins: dict[str, str], timeout: float,
             allow_dirty: bool = False) -> tuple[dict, bytes]:
    if timeout <= 0 or timeout > 3600:
        raise ValueError("timeout must be greater than zero and no more than 3600 seconds")
    before_binary = collector.file_observation(binary)
    before_source = collector.source_observation(ROOT)
    if before_source["worktreeDirty"] and not allow_dirty:
        raise ValueError("source worktree is dirty; commit/stash changes or pass --allow-dirty")
    inventory = collector.diagnose_hardware()
    environment = {key: value for key, value in os.environ.items() if not key.startswith("STAGEMESH_")}
    environment.update(opt_ins)
    command = [str(binary.resolve(strict=True)), *arguments]
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = None
        stdout = error.stdout or b""
        stderr = error.stderr or b""
    finished_at = datetime.now(timezone.utc).isoformat()
    duration = time.monotonic() - started
    after_binary = collector.file_observation(binary)
    after_source = collector.source_observation(ROOT)
    if before_binary != after_binary:
        raise ValueError("binary changed during execution")
    if before_source != after_source:
        raise ValueError("source revision or dirty state changed during execution")
    transcript = (
        b"=== stdout ===\n" + stdout + (b"" if stdout.endswith(b"\n") else b"\n")
        + b"=== stderr ===\n" + stderr + (b"" if stderr.endswith(b"\n") else b"\n")
    )
    report = {
        "documentType": "org.stagemesh.native-host-exercise",
        "schemaVersion": 1,
        "startedAt": started_at,
        "finishedAt": finished_at,
        "durationSeconds": round(duration, 6),
        "host": {
            "os": collector.platform.system(),
            "release": collector.platform.release(),
            "version": collector.platform.version(),
            "architecture": collector.platform.machine(),
        },
        "source": before_source,
        "binary": before_binary,
        "hardwareInventory": inventory,
        "execution": {
            "arguments": arguments,
            "optIns": opt_ins,
            "timeoutSeconds": timeout,
            "timedOut": timed_out,
            "exitCode": exit_code,
            "processExitedSuccessfully": exit_code == 0 and not timed_out,
        },
        "evidenceBoundary": {
            "binaryExecuted": True,
            "transcriptCapturedByRunner": True,
            "binaryStableDuringExecution": True,
            "sourceRevisionAndDirtyStateStableDuringExecution": True,
            "cleanSourceSnapshotObserved": not before_source["worktreeDirty"],
            "dirtySourceExplicitlyAllowed": before_source["worktreeDirty"] and allow_dirty,
            "inheritedStageMeshControlsRemoved": True,
            "binarySourceBindingVerified": False,
            "audioCapturedInferred": False,
            "physicalOutputsArmedInferred": False,
            "ownerReviewComplete": False,
            "physicalHardwareQualified": False,
            "statement": "Exit status and transcript belong to this execution; binary origin, dirty-worktree content stability, and hardware qualification remain unverified.",
        },
    }
    return report, transcript


def write_bundle(output: Path, report: dict, transcript: bytes) -> None:
    if output.exists():
        raise ValueError("output already exists; use a new session directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent))
    try:
        transcript_path = temporary / "transcript.txt"
        transcript_path.write_bytes(transcript)
        report["transcript"] = collector.file_observation(transcript_path)
        (temporary / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output)
    except Exception:
        for child in temporary.iterdir():
            child.unlink(missing_ok=True)
        temporary.rmdir()
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--allow-dirty", action="store_true",
                        help="Execute while recording that the source snapshot is not commit-bound")
    parser.add_argument("--opt-in", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="Binary arguments after --")
    args = parser.parse_args(argv)
    arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    try:
        opt_ins = parse_opt_ins(args.opt_in)
        report, transcript = exercise(args.binary, arguments, opt_ins, args.timeout, args.allow_dirty)
        write_bundle(args.output, report, transcript)
        print(f"Native host exercise evidence saved to {args.output}")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Native host exercise failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
