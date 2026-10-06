#!/usr/bin/env python3
"""Run local-reference HTTP controller and rate-policy qualification."""
from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dev_server import RequestRateLimiter
from http_workload import simulate_rate_policy, summarize_http_results


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(port: int, sequence: int, abuse: bool = False) -> dict:
    started = time.perf_counter()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        if abuse or sequence % 3 != 2:
            conn.request("GET", "/healthz")
        else:
            payload = json.dumps({"targetNs": 1_000_000_000 + sequence})
            conn.request("POST", "/api/v1/timing/plan", body=payload,
                         headers={"Content-Type": "application/json", "Content-Length": str(len(payload))})
        response = conn.getresponse(); response.read()
        return {"status": response.status, "latencyMs": (time.perf_counter() - started) * 1000.0}
    except Exception as exc:
        return {"status": None, "latencyMs": (time.perf_counter() - started) * 1000.0,
                "error": type(exc).__name__}
    finally:
        conn.close()


def _run_parallel(port: int, count: int, concurrency: int, abuse: bool) -> list[dict]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(lambda index: _request(port, index, abuse), range(count)))


def _wait_ready(port: int) -> None:
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        result = _request(port, 0, True)
        if result.get("status") == 200:
            return
        time.sleep(0.05)
    raise RuntimeError("local StageMesh workload server did not become ready")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal-requests", type=int, default=120)
    parser.add_argument("--abuse-requests", type=int, default=320)
    parser.add_argument("--normal-concurrency", type=int, default=12)
    parser.add_argument("--abuse-concurrency", type=int, default=24)
    parser.add_argument("--max-normal-p95-ms", type=float, default=1000.0)
    parser.add_argument("--model-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    model = simulate_rate_policy(lambda clock: RequestRateLimiter(clock=clock))
    report = {
        "documentType": "org.upp.http-workload-qualification-report",
        "schemaVersion": 1,
        "referenceOnly": True,
        "physicalControllerQualified": False,
        "deployedLanQualified": False,
        "ratePolicyModel": model,
    }
    if not args.model_only:
        if min(args.normal_requests, args.abuse_requests, args.normal_concurrency, args.abuse_concurrency) <= 0:
            raise ValueError("request counts and concurrency must be positive")
        port = _free_port()
        with tempfile.TemporaryDirectory(prefix="stagemesh-http-workload-") as raw:
            env = os.environ.copy()
            env["STAGEMESH_DATA_DIR"] = str(Path(raw) / "data")
            env["STAGEMESH_NATIVE_ENGINE"] = "off"
            # This qualification exercises the default direct-loopback bridge;
            # deployed proxy/IdP/firewall qualification remains a separate gate.
            for name in ("STAGEMESH_DEPLOYMENT_PROFILE", "STAGEMESH_REQUIRE_API_TOKEN",
                         "STAGEMESH_HTTP_CREDENTIAL_FILE", "STAGEMESH_HTTP_AUTHORIZATION_FILE"):
                env.pop(name, None)
            process = subprocess.Popen(
                [sys.executable, str(ROOT / "backend/dev_server.py"), "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                _wait_ready(port)
                normal = _run_parallel(port, args.normal_requests, args.normal_concurrency, False)
                abuse = _run_parallel(port, args.abuse_requests, args.abuse_concurrency, True)
            finally:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)
        normal_summary = summarize_http_results(normal, {200}, max_p95_ms=args.max_normal_p95_ms)
        abuse_summary = summarize_http_results(abuse, {200, 429})
        abuse_summary["throttled"] = abuse_summary["statusCounts"].get("429", 0)
        abuse_summary["passed"] = bool(abuse_summary["passed"] and abuse_summary["throttled"] > 0)
        report["normalControllerBurst"] = normal_summary
        report["abusiveBurst"] = abuse_summary
        report["passed"] = bool(model["passed"] and normal_summary["passed"] and abuse_summary["passed"])
    else:
        report["passed"] = bool(model["passed"])

    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
