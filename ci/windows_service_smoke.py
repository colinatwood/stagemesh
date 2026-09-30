#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

KEY = hashlib.sha256(b"stagemesh-windows-service-ci").digest()
CLUSTER = "31" * 16
SESSION = "41" * 32
CAPABILITY = 7


def current_sid() -> str:
    row = next(csv.reader(io.StringIO(subprocess.check_output(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip())))
    return row[1].upper()


def channel(*, server: bool):
    from session_channel import AuthenticatedSessionChannel

    return AuthenticatedSessionChannel(
        KEY,
        CLUSTER,
        SESSION,
        {CAPABILITY},
        send_direction="server" if server else "client",
        receive_direction="client" if server else "server",
    )


def service_mode(args) -> int:
    from local_ipc import WindowsNamedPipeIpcServer
    from windows_service import WindowsServiceHost

    marker = Path(args.marker)
    error_path = Path(str(marker) + ".error")
    server = WindowsNamedPipeIpcServer(
        args.pipe_name,
        lambda: channel(server=True),
        lambda capability, payload: b"service-ci:" + payload,
        max_requests=1,
        allowed_sids=(args.operator_sid,),
        allow_administrators=False,
    )
    worker: threading.Thread | None = None
    worker_errors: list[str] = []

    def on_start() -> None:
        nonlocal worker
        server.start()

        def serve() -> None:
            try:
                server.serve_once()
            except BaseException as exc:
                worker_errors.append(repr(exc))

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        marker.write_text(json.dumps({
            "serviceName": args.service_name,
            "pipeName": args.pipe_name,
            "serviceSid": current_sid(),
            "physicalOutputsArmed": False,
        }, sort_keys=True), encoding="utf-8")

    def on_stop() -> None:
        server.close()
        if worker is not None:
            worker.join(5)
            if worker.is_alive():
                raise RuntimeError("Windows named-pipe accept did not stop within 5 seconds")
        if worker_errors:
            raise RuntimeError(worker_errors[0])

    try:
        WindowsServiceHost(args.service_name, on_start, on_stop).run()
        return 0
    except BaseException as exc:
        try:
            error_path.write_text(repr(exc), encoding="utf-8")
        except OSError:
            pass
        raise


def sc(*parts: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["sc.exe", *parts],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"sc.exe {' '.join(parts)} failed ({result.returncode}): {result.stdout}")
    return result


def service_state(name: str) -> int | None:
    result = sc("query", name, check=False)
    match = re.search(r"STATE\s*:\s*(\d+)", result.stdout)
    return int(match.group(1)) if match else None


def wait_state(name: str, expected: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = service_state(name)
        if state == expected:
            return
        time.sleep(0.25)
    raise RuntimeError(f"service {name} did not reach state {expected}; last={service_state(name)}")


def wait_marker(path: Path, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        error_path = Path(str(path) + ".error")
        if error_path.exists():
            raise RuntimeError(error_path.read_text(encoding="utf-8"))
        time.sleep(0.1)
    raise RuntimeError("Windows service marker did not appear")


def reset_marker(path: Path) -> None:
    path.unlink(missing_ok=True)
    Path(str(path) + ".error").unlink(missing_ok=True)


def roundtrip(pipe_name: str) -> None:
    from multiprocessing.connection import Client
    from local_ipc import decode_transport_packet, encode_transport_packet

    connection = None
    deadline = time.monotonic() + 10
    while connection is None and time.monotonic() < deadline:
        try:
            connection = Client(pipe_name, family="AF_PIPE")
        except OSError:
            time.sleep(0.05)
    if connection is None:
        raise RuntimeError("could not connect to Windows service pipe")
    client = channel(server=False)
    try:
        connection.send_bytes(encode_transport_packet(client.encode(CAPABILITY, b"ping")))
        response = client.decode(decode_transport_packet(connection.recv_bytes()))
    finally:
        connection.close()
    if response["payload"] != b"service-ci:ping":
        raise RuntimeError("Windows service UPPF roundtrip mismatch")


def controller_mode(args) -> int:
    service_name = "StageMeshCI" + uuid.uuid4().hex[:12]
    pipe_name = rf"\\.\pipe\StageMesh\Svc-{uuid.uuid4().hex}"
    operator_sid = current_sid()
    marker = Path(os.environ.get("RUNNER_TEMP", str(ROOT))) / f"{service_name}.json"
    evidence = Path(args.evidence)
    reset_marker(marker)

    command = subprocess.list2cmdline([
        sys.executable,
        str(Path(__file__).resolve()),
        "--service",
        "--service-name", service_name,
        "--pipe-name", pipe_name,
        "--operator-sid", operator_sid,
        "--marker", str(marker),
    ])

    created = False
    first_roundtrip = False
    normal_stop = False
    idle_stop = False
    idle_stop_seconds = None
    restart_after_idle = False
    final_roundtrip = False
    service_sid = None
    try:
        sc("create", service_name, "binPath=", command, "start=", "demand", "obj=", "LocalSystem")
        created = True

        sc("start", service_name)
        wait_state(service_name, 4)
        first_marker = wait_marker(marker)
        service_sid = str(first_marker.get("serviceSid", "")).upper()
        if service_sid != "S-1-5-18":
            raise RuntimeError(f"service did not run as LocalSystem: {service_sid}")
        roundtrip(pipe_name)
        first_roundtrip = True
        sc("stop", service_name)
        wait_state(service_name, 1)
        normal_stop = True

        reset_marker(marker)
        sc("start", service_name)
        wait_state(service_name, 4)
        idle_marker = wait_marker(marker)
        if str(idle_marker.get("serviceSid", "")).upper() != "S-1-5-18":
            raise RuntimeError("idle-stop service identity changed")
        started = time.monotonic()
        sc("stop", service_name)
        wait_state(service_name, 1, timeout=12.0)
        idle_stop_seconds = time.monotonic() - started
        if idle_stop_seconds > 10.0:
            raise RuntimeError(f"idle Windows service stop exceeded bound: {idle_stop_seconds:.3f}s")
        idle_stop = True

        reset_marker(marker)
        sc("start", service_name)
        wait_state(service_name, 4)
        final_marker = wait_marker(marker)
        if str(final_marker.get("serviceSid", "")).upper() != "S-1-5-18":
            raise RuntimeError("post-idle-stop service identity changed")
        restart_after_idle = True
        roundtrip(pipe_name)
        final_roundtrip = True
        sc("stop", service_name)
        wait_state(service_name, 1)
    finally:
        if created:
            sc("delete", service_name, check=False)

    report = {
        "documentType": "org.upp.windows-service-smoke",
        "schemaVersion": 2,
        "serviceControlManagerQualified": created,
        "localSystemIdentityQualified": service_sid == "S-1-5-18",
        "firstAuthenticatedRoundtripQualified": first_roundtrip,
        "cleanStopQualified": normal_stop,
        "idlePendingAcceptStopQualified": idle_stop,
        "idlePendingAcceptStopSeconds": idle_stop_seconds,
        "restartAfterIdleStopQualified": restart_after_idle,
        "postIdleStopAuthenticatedRoundtripQualified": final_roundtrip,
        "serviceDeletionRequested": created,
        "physicalOutputsArmed": False,
        "physicalHardwareQualified": False,
    }
    evidence.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(evidence.read_text(encoding="utf-8"))
    return 0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", action="store_true")
    parser.add_argument("--service-name")
    parser.add_argument("--pipe-name")
    parser.add_argument("--operator-sid")
    parser.add_argument("--marker")
    parser.add_argument("--evidence", default="windows-service-smoke.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.service:
        required = [args.service_name, args.pipe_name, args.operator_sid, args.marker]
        if any(not value for value in required):
            raise SystemExit("service mode requires service/pipe/operator/marker arguments")
        return service_mode(args)
    return controller_mode(args)


if __name__ == "__main__":
    raise SystemExit(main())
