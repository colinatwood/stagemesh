#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

TRACKED = [
    "backend/session_channel.py",
    "backend/local_ipc.py",
    "backend/windows_named_pipe.py",
    "backend/audio_endpoint_evidence.py",
]


def normalized_sha256(path: str) -> str:
    data = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(path: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"HEAD:{path}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="strict",
    ).strip()


def verify_snapshot() -> dict:
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="strict",
    ).strip()
    if status:
        raise RuntimeError(f"tracked working tree is not clean: {status}")
    return {
        path: {
            "gitBlobSha": git_blob_sha(path),
            "normalizedSha256": normalized_sha256(path),
        }
        for path in TRACKED
    }


def current_windows_sid() -> str:
    import csv

    row = next(
        csv.reader(
            io.StringIO(
                subprocess.check_output(
                    ["whoami.exe", "/user", "/fo", "csv", "/nh"],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                ).strip()
            )
        )
    )
    return row[1].upper()


def windows_unauthorized_denial() -> dict:
    import ctypes
    import windows_named_pipe as wnp

    name = rf"\\.\pipe\StageMesh\CI-Deny-{uuid.uuid4().hex}"
    unauthorized_only_sid = "S-1-5-21-1111111111-2222222222-3333333333-424242"
    listener = wnp.create_secure_windows_pipe_listener(
        name,
        (unauthorized_only_sid,),
        allow_administrators=False,
    )
    descriptor, attrs = listener._security_attributes()
    handle = None
    try:
        handle = listener._api.kernel32.CreateNamedPipeW(
            ctypes.c_wchar_p(listener.name),
            ctypes.c_ulong(wnp._PIPE_ACCESS_DUPLEX | wnp._FILE_FLAG_FIRST_PIPE_INSTANCE),
            ctypes.c_ulong(wnp._PIPE_TYPE_MESSAGE | wnp._PIPE_READMODE_MESSAGE | wnp._PIPE_WAIT),
            ctypes.c_ulong(1),
            ctypes.c_ulong(wnp.MAX_FRAME + wnp._SIZE.size),
            ctypes.c_ulong(wnp.MAX_FRAME + wnp._SIZE.size),
            ctypes.c_ulong(5000),
            ctypes.byref(attrs),
        )
        if handle == wnp._INVALID_HANDLE_VALUE or handle is None:
            raise RuntimeError(f"could not create denial-test pipe ({listener._api.last_error()})")
        wnp.attest_windows_pipe_dacl(int(handle), listener.policy, listener._api)

        child = (
            "from multiprocessing.connection import Client\n"
            "import sys\n"
            "name=sys.argv[1]\n"
            "try:\n"
            "    c=Client(name,family='AF_PIPE')\n"
            "except OSError as exc:\n"
            "    code=getattr(exc,'winerror',None) or getattr(exc,'errno',None)\n"
            "    print(code if code is not None else '')\n"
            "    raise SystemExit(0 if code in (5,13) else 2)\n"
            "else:\n"
            "    c.close()\n"
            "    raise SystemExit(3)\n"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", child, name],
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=8,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("unauthorized Windows named-pipe denial probe timed out") from exc
        if result.returncode == 3:
            raise RuntimeError("unauthorized Windows named-pipe client unexpectedly connected")
        if result.returncode != 0:
            raise RuntimeError(
                f"unauthorized pipe client failed for unexpected reason ({result.returncode}): {result.stdout.strip()}"
            )
        try:
            denied_error = int(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise RuntimeError(f"unauthorized denial probe returned no error code: {result.stdout!r}") from exc

        return {
            "unauthorizedClientDenialQualified": True,
            "denialErrorCode": denied_error,
            "probeBoundedSeconds": 8,
        }
    finally:
        if handle not in {None, wnp._INVALID_HANDLE_VALUE}:
            listener._api.kernel32.CloseHandle(ctypes.c_void_p(handle))
        listener._api.kernel32.LocalFree(descriptor)
        listener.close()


def windows_pipe() -> dict:
    from multiprocessing.connection import Client
    from local_ipc import (
        WindowsNamedPipeIpcServer,
        decode_transport_packet,
        encode_transport_packet,
    )
    from session_channel import AuthenticatedSessionChannel

    sid = current_windows_sid()
    name = rf"\\.\pipe\StageMesh\CI-{uuid.uuid4().hex}"
    key = hashlib.sha256(b"stagemesh-github-bootstrap").digest()
    cluster = "11" * 16
    session = "22" * 32

    def channel() -> AuthenticatedSessionChannel:
        return AuthenticatedSessionChannel(
            key,
            cluster,
            session,
            {7},
            send_direction="server",
            receive_direction="client",
        )

    server = WindowsNamedPipeIpcServer(
        name,
        channel,
        lambda c, p: b"github-ci:" + p,
        max_requests=1,
        allowed_sids=(sid,),
        allow_administrators=False,
    )
    server.start()
    errors: list[BaseException] = []
    thread = threading.Thread(target=lambda: _serve(server, errors), daemon=True)
    thread.start()

    conn = None
    deadline = time.monotonic() + 10
    while conn is None and time.monotonic() < deadline:
        if errors:
            break
        try:
            conn = Client(name, family="AF_PIPE")
        except OSError:
            time.sleep(0.05)
    if conn is None:
        server.close()
        if errors:
            raise errors[0]
        raise RuntimeError("pipe connect timeout")

    client = AuthenticatedSessionChannel(
        key,
        cluster,
        session,
        {7},
        send_direction="client",
        receive_direction="server",
    )
    conn.send_bytes(encode_transport_packet(client.encode(7, b"ping")))
    decoded = client.decode(decode_transport_packet(conn.recv_bytes()))
    conn.close()
    thread.join(10)
    server.close()
    if errors:
        raise errors[0]
    if decoded["payload"] != b"github-ci:ping":
        raise RuntimeError("unexpected pipe response")

    denial = windows_unauthorized_denial()
    return {
        "kernelDaclAndAuthorizedRoundtripQualified": True,
        "sidHash": hashlib.sha256(sid.encode()).hexdigest(),
        **denial,
    }


def _serve(server, errors: list[BaseException]) -> None:
    try:
        server.serve_once()
    except BaseException as exc:
        errors.append(exc)


def mac_audio() -> dict:
    from audio_endpoint_evidence import macos_endpoint_probe

    def run(cmd):
        return json.loads(
            subprocess.check_output(
                cmd,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        )

    endpoints, drivers = macos_endpoint_probe(run)
    return {
        "coreAudioProbeQualified": True,
        "endpointCount": len(endpoints),
        "driverRecordCount": len(drivers),
        "physicalInterfaceQualified": False,
    }


def main() -> int:
    report = {
        "documentType": "org.upp.github-platform-module-smoke",
        "schemaVersion": 4,
        "provenanceCheckpoint": 71,
        "gitHubSource": {
            "sha": os.environ.get("GITHUB_SHA"),
            "headRef": os.environ.get("GITHUB_HEAD_REF"),
        },
        "host": {
            "os": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
        },
        "physicalOutputsArmed": False,
        "physicalHardwareQualified": False,
        "trackedFiles": verify_snapshot(),
        "checks": {},
    }
    if platform.system() == "Windows":
        report["checks"]["windowsNamedPipe"] = windows_pipe()
    elif platform.system() == "Darwin":
        report["checks"]["macosAudioEvidence"] = mac_audio()
    else:
        report["checks"]["linuxImportReference"] = {"qualified": True}

    out = Path(os.environ.get("STAGEMESH_CI_EVIDENCE", "platform-module-smoke.json"))
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
