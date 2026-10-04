#!/usr/bin/env python3
"""Target-OS CI smoke evidence for StageForge.

This is a software/platform reference exercise, not physical hardware qualification.
It never arms physical outputs. Windows exercises the native protected named-pipe
listener and an authenticated UPPF roundtrip. macOS executes the real CoreAudio
endpoint evidence probe. Linux records the ordinary platform/native build context.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _find_engine() -> Path:
    candidates=[]
    env = os.environ.get("STAGEFORGE_NATIVE_ENGINE")
    if env:
        candidates.append(Path(env))
    candidates += [
        ROOT / "build" / "native" / "stagemesh_engine",
        ROOT / "build" / "native" / "stagemesh_engine.exe",
        ROOT / "build" / "native" / "Release" / "stagemesh_engine.exe",
        ROOT / "build" / "native" / "Release" / "stagemesh_engine",
    ]
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise RuntimeError("platform CI smoke requires a built StageForge native engine")


def _current_windows_sid() -> str:
    text = subprocess.check_output(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()
    import csv, io
    row = next(csv.reader(io.StringIO(text)))
    if len(row) < 2 or not row[1].upper().startswith("S-1-"):
        raise RuntimeError("could not determine current Windows user SID")
    return row[1].upper()


def _windows_pipe_smoke() -> dict:
    from multiprocessing.connection import Client
    from local_ipc import (
        WindowsNamedPipeIpcServer,
        decode_transport_packet,
        encode_transport_packet,
    )
    from session_channel import AuthenticatedSessionChannel

    sid = _current_windows_sid()
    name = rf"\\.\pipe\StageForge\CI-{uuid.uuid4().hex}"
    key = hashlib.sha256(b"stageforge-ci-smoke-session-key").digest()
    cluster_id = "11" * 16
    session_id = "22" * 32
    capabilities = {7}

    def server_channel():
        return AuthenticatedSessionChannel(
            key, cluster_id, session_id, capabilities,
            send_direction="server", receive_direction="client",
        )

    server = WindowsNamedPipeIpcServer(
        name,
        server_channel,
        lambda capability, payload: b"stageforge-ci:" + payload,
        max_requests=1,
        allowed_sids=(sid,),
        allow_administrators=False,
    )
    server.start()
    outcome: dict[str, object] = {}
    error: list[BaseException] = []

    def run_server():
        try:
            server.serve_once()
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    connection = None
    deadline = time.monotonic() + 10.0
    while connection is None and time.monotonic() < deadline:
        try:
            connection = Client(name, family="AF_PIPE")
        except OSError:
            time.sleep(0.05)
    if connection is None:
        server.close()
        raise RuntimeError("could not connect to StageForge Windows named-pipe smoke endpoint")

    client = AuthenticatedSessionChannel(
        key, cluster_id, session_id, capabilities,
        send_direction="client", receive_direction="server",
    )
    try:
        request = client.encode(7, b"ping")
        # AF_PIPE adds its own message envelope. StageForge additionally requires
        # the explicit local-IPC big-endian length prefix inside that message,
        # exactly as WindowsNamedPipeIpcServer.recv_message_frame expects.
        connection.send_bytes(encode_transport_packet(request))
        response = decode_transport_packet(connection.recv_bytes())
        decoded = client.decode(response)
        if decoded["payload"] != b"stageforge-ci:ping":
            raise RuntimeError("Windows named-pipe authenticated roundtrip returned unexpected payload")
        outcome = {
            "authorizedRoundtripQualified": True,
            "currentUserSidHash": hashlib.sha256(sid.encode("ascii")).hexdigest(),
            "aclKernelAttestationQualified": True,
            "unauthorizedClientDenialQualified": False,
            "note": "Kernel DACL attestation and authorized client roundtrip passed; a separate denied principal is not available on the hosted runner.",
        }
    finally:
        connection.close()
        thread.join(timeout=10.0)
        server.close()
    if thread.is_alive():
        raise RuntimeError("Windows named-pipe smoke server did not terminate")
    if error:
        raise RuntimeError(f"Windows named-pipe smoke server failed: {error[0]}")
    return outcome


def _macos_audio_smoke() -> dict:
    from audio_endpoint_evidence import macos_endpoint_probe

    def command_json(command):
        payload = subprocess.check_output(command, text=True, encoding="utf-8", errors="replace")
        return json.loads(payload)

    endpoints, drivers = macos_endpoint_probe(command_json)
    return {
        "coreAudioProbeQualified": True,
        "endpointCount": len(endpoints),
        "driverRecordCount": len(drivers),
        "physicalInterfaceQualified": False,
        "note": "Real system_profiler CoreAudio evidence probe executed on the hosted macOS runner; no named external interface qualification is claimed.",
    }


def build_report() -> dict:
    engine = _find_engine()
    system = platform.system()
    report = {
        "documentType": "org.upp.platform-ci-smoke",
        "schemaVersion": 1,
        "host": {
            "os": system,
            "release": platform.release(),
            "architecture": platform.machine(),
        },
        "python": platform.python_version(),
        "nativeEngine": {
            "pathBasename": engine.name,
            "sha256": _sha256_file(engine),
        },
        "physicalOutputsArmed": False,
        "physicalHardwareQualified": False,
        "platformExecutionQualified": True,
        "checks": {},
    }
    if system == "Windows":
        report["checks"]["windowsNamedPipe"] = _windows_pipe_smoke()
    elif system == "Darwin":
        report["checks"]["macosAudioEvidence"] = _macos_audio_smoke()
    else:
        report["checks"]["linuxReference"] = {
            "nativeEnginePresent": True,
            "note": "Linux CI reference only; RT release qualification is a separate job.",
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = build_report()
        encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0
    except Exception as exc:
        print(f"platform CI smoke failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
