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
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dev_server import RequestRateLimiter
from http_workload import simulate_rate_policy, summarize_http_results


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request_on_connection(conn: http.client.HTTPConnection, sequence: int,
                           abuse: bool = False) -> dict:
    started = time.perf_counter()
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


def _request(port: int, sequence: int, abuse: bool = False) -> dict:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        return _request_on_connection(conn, sequence, abuse)
    finally:
        conn.close()


def _run_parallel(port: int, count: int, concurrency: int, abuse: bool) -> list[dict]:
    """Run bounded persistent clients, synchronized at the observation boundary.

    Opening a fresh TCP connection for every request makes the offered rate depend
    mostly on host accept/connect latency. A slow host can then refill the default
    token bucket faster than a nominally abusive client drains it. Reusing one
    connection per worker measures the HTTP policy rather than connection setup,
    while keeping concurrency bounded well below the server's connection limit.
    """
    worker_count = min(count, concurrency)
    barrier = threading.Barrier(worker_count)
    sequences = [list(range(index, count, worker_count)) for index in range(worker_count)]

    def worker(items: list[int]) -> list[tuple[int, dict]]:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            barrier.wait(timeout=5)
            return [(sequence, _request_on_connection(conn, sequence, abuse))
                    for sequence in items]
        finally:
            conn.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        grouped = list(pool.map(worker, sequences))
    ordered = sorted((item for group in grouped for item in group), key=lambda item: item[0])
    return [result for _, result in ordered]


def _wait_ready(port: int) -> None:
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        result = _request(port, 0, True)
        if result.get("status") == 200:
            return
        time.sleep(0.05)
    raise RuntimeError("local StageMesh workload server did not become ready")


def _summarize_observation(results: list[dict], duration: float,
                           expected_statuses: set[int], *,
                           max_p95_ms: float | None = None,
                           require_throttle: bool = False) -> dict:
    summary = summarize_http_results(results, expected_statuses, max_p95_ms=max_p95_ms)
    summary["observationSeconds"] = round(duration, 3)
    summary["completedRequestsPerSecond"] = round(len(results) / max(duration, 1e-9), 3)
    if require_throttle:
        summary["throttled"] = summary["statusCounts"].get("429", 0)
        summary["observationStatus"] = (
            "throttling-observed" if summary["throttled"] else "no-throttling-observed"
        )
        summary["passed"] = bool(summary["passed"] and summary["throttled"] > 0)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal-requests", type=int, default=120)
    parser.add_argument("--abuse-requests", type=int, default=1200)
    parser.add_argument("--normal-concurrency", type=int, default=12)
    parser.add_argument("--abuse-concurrency", type=int, default=8)
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
                normal_started = time.perf_counter()
                normal = _run_parallel(port, args.normal_requests, args.normal_concurrency, False)
                normal_duration = time.perf_counter() - normal_started
                abuse_started = time.perf_counter()
                abuse = _run_parallel(port, args.abuse_requests, args.abuse_concurrency, True)
                abuse_duration = time.perf_counter() - abuse_started
            finally:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)
        normal_summary = _summarize_observation(
            normal, normal_duration, {200}, max_p95_ms=args.max_normal_p95_ms
        )
        abuse_summary = _summarize_observation(
            abuse, abuse_duration, {200, 429}, require_throttle=True
        )
        report["configuration"] = {
            "normalRequests": args.normal_requests,
            "normalConcurrency": args.normal_concurrency,
            "abuseRequests": args.abuse_requests,
            "abuseConcurrency": args.abuse_concurrency,
            "maxNormalP95Ms": args.max_normal_p95_ms,
            "productionRatePolicyUnchanged": True,
        }
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
