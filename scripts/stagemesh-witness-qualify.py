#!/usr/bin/env python3
"""Reference qualification for the strict independent-witness deployment mode.

This intentionally uses three loopback processes. It proves StageMesh's
identity, credential, quorum and one-/two-witness failure behavior, but it is
not evidence that three production witnesses occupy independent failure domains.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from witness import WitnessQuorumClient  # noqa: E402
from witness_topology import load_witness_topology  # noqa: E402


def private_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), "utf-8")
    path.chmod(0o600)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(url: str, process: subprocess.Popen, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last_error = "not started"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"witness exited during startup with status {process.returncode}")
        try:
            with urlopen(url + "/health", timeout=0.25) as response:
                value = json.loads(response.read(8192).decode("utf-8"))
            if value.get("ok") is True:
                return value
            last_error = str(value.get("error") or value)
        except Exception as exc:  # qualification helper: preserve a bounded diagnostic
            last_error = str(exc)
        time.sleep(0.05)
    raise RuntimeError(f"witness health did not become ready: {last_error[:200]}")


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def main() -> int:
    processes: list[subprocess.Popen] = []
    report: dict = {
        "documentType": "org.upp.independent-witness-qualification",
        "schemaVersion": 1,
        "referenceOnly": True,
        "physicalIndependenceQualified": False,
        "passed": False,
        "phases": [],
    }
    try:
        with tempfile.TemporaryDirectory(prefix="stagemesh-independent-witness-") as raw_root:
            root = Path(raw_root)
            witnesses = []
            for index, suffix in enumerate(("a", "b", "c"), start=1):
                port = free_port()
                witness_id = f"qualification-witness-{suffix}"
                failure_domain = f"qualification-domain-{suffix}"
                keyring = root / f"{witness_id}-keys.json"
                private_json(keyring, {
                    "version": 1,
                    "activeKeyId": "qualification-key",
                    "keys": {"qualification-key": f"stagemesh-independent-{suffix}-qualification-secret-0001"},
                })
                url = f"http://127.0.0.1:{port}"
                env = dict(os.environ)
                for name in (
                    "STAGEMESH_WITNESS_SECRET",
                    "STAGEMESH_REPLICATION_SECRET",
                    "STAGEMESH_REPLICATION_KEYRING_FILE",
                    "STAGEMESH_WITNESS_TOPOLOGY_FILE",
                ):
                    env.pop(name, None)
                env.update({
                    "STAGEMESH_WITNESS_INDEPENDENT": "1",
                    "STAGEMESH_WITNESS_ID": witness_id,
                    "STAGEMESH_WITNESS_FAILURE_DOMAIN": failure_domain,
                    "STAGEMESH_WITNESS_KEYRING_FILE": str(keyring),
                    "STAGEMESH_WITNESS_HOST": "127.0.0.1",
                    "STAGEMESH_WITNESS_PORT": str(port),
                    "STAGEMESH_WITNESS_DATA": str(root / f"{witness_id}-leases.json"),
                    "PYTHONPATH": str(BACKEND),
                })
                process = subprocess.Popen(
                    [sys.executable, str(BACKEND / "witness_server.py")],
                    cwd=str(ROOT), env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                processes.append(process)
                witnesses.append({
                    "url": url,
                    "witnessId": witness_id,
                    "failureDomain": failure_domain,
                    "keyringFile": str(keyring),
                })

            topology_path = root / "topology.json"
            private_json(topology_path, {
                "version": 1,
                "quorum": 2,
                "maxClockSkewMs": 2000,
                "allowInsecureLoopback": True,
                "witnesses": witnesses,
            })
            topology = load_witness_topology(topology_path)
            health = [wait_health(item["url"], process) for item, process in zip(witnesses, processes)]
            report.update({
                "quorum": topology["quorum"],
                "maxClockSkewMs": topology["maxClockSkewMs"],
                "witnessIds": [item["witnessId"] for item in witnesses],
                "declaredFailureDomains": [item["failureDomain"] for item in witnesses],
                "health": health,
            })

            primary = WitnessQuorumClient([], "qualification-show", "node-a", b"",
                                          ttl_ms=5000, timeout_seconds=0.25,
                                          independent_topology=topology)
            initial = primary.acquire()
            phase = {
                "name": "three-witness-acquire",
                "expected": "2-of-3-or-better quorum",
                "leaseValid": initial["leaseValid"],
                "grants": sum(1 for item in initial["results"] if item["granted"]),
            }
            report["phases"].append(phase)
            if not initial["leaseValid"] or phase["grants"] < 2:
                raise RuntimeError("initial independent witness quorum was not acquired")
            source_epoch = int(initial["leaseEpoch"])

            stop(processes[0])
            transfer = primary.transfer(
                target_node_id="node-b", source_epoch=source_epoch,
                target_epoch=source_epoch + 1, transaction_id=48001,
            )
            report["phases"].append({
                "name": "one-witness-loss-transfer",
                "expected": "remaining 2-of-3 witnesses authorize named successor",
                "transferred": bool(transfer["transferred"]),
                "grants": int(transfer["grants"]),
            })
            if not transfer["transferred"] or int(transfer["grants"]) < 2:
                raise RuntimeError("one-witness-loss transfer did not retain quorum")

            successor = WitnessQuorumClient([], "qualification-show", "node-b", b"",
                                            ttl_ms=5000, timeout_seconds=0.25,
                                            independent_topology=topology)
            after_one_loss = successor.acquire()
            report["phases"].append({
                "name": "successor-after-one-witness-loss",
                "expected": "successor renews quorum lease",
                "leaseValid": after_one_loss["leaseValid"],
                "grants": sum(1 for item in after_one_loss["results"] if item["granted"]),
            })
            if not after_one_loss["leaseValid"]:
                raise RuntimeError("successor could not renew a quorum lease")

            stop(processes[1])
            after_two_loss = WitnessQuorumClient([], "qualification-show", "node-b", b"",
                                                 ttl_ms=5000, timeout_seconds=0.25,
                                                 independent_topology=topology).acquire()
            grants_after_two = sum(1 for item in after_two_loss["results"] if item["granted"])
            report["phases"].append({
                "name": "two-witness-loss-denial",
                "expected": "1-of-3 cannot form quorum",
                "leaseValid": after_two_loss["leaseValid"],
                "grants": grants_after_two,
            })
            if after_two_loss["leaseValid"] or grants_after_two >= topology["quorum"]:
                raise RuntimeError("two-witness loss incorrectly retained quorum")

            report["passed"] = True
    except Exception as exc:
        report["error"] = str(exc)[:500]
    finally:
        for process in processes:
            stop(process)

    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
