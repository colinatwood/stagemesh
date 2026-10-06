"""Deterministic helpers for HTTP controller/rate-policy qualification."""
from __future__ import annotations

import math
from typing import Any, Callable


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    q = min(1.0, max(0.0, float(quantile)))
    index = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[index]


def summarize_http_results(results: list[dict[str, Any]], expected_statuses: set[int], *, max_p95_ms: float | None = None) -> dict[str, Any]:
    latencies = [float(item["latencyMs"]) for item in results if item.get("latencyMs") is not None]
    counts: dict[str, int] = {}
    errors = 0
    for item in results:
        status = item.get("status")
        key = str(status if status is not None else "error")
        counts[key] = counts.get(key, 0) + 1
        if status not in expected_statuses:
            errors += 1
    p95 = percentile(latencies, 0.95)
    passed = errors == 0 and (max_p95_ms is None or p95 <= max_p95_ms)
    return {
        "requests": len(results), "statusCounts": counts, "unexpected": errors,
        "p50Ms": round(percentile(latencies, 0.50), 3),
        "p95Ms": round(p95, 3), "maxMs": round(max(latencies) if latencies else 0.0, 3),
        "passed": passed,
    }


def simulate_rate_policy(limiter_factory: Callable[[Callable[[], float]], Any], *, ticks: int = 500) -> dict[str, Any]:
    """Replay four 20 rps controllers beside one 300 rps abusive peer for 5 s.

    With StageMesh's default 100 rps per-peer and 200 rps aggregate refill, the
    abusive peer must be bounded while the 80 rps aggregate controller workload is
    admitted. The controlled clock makes this qualification deterministic.
    """
    now = [0.0]
    limiter = limiter_factory(lambda: now[0])
    controllers_allowed = controllers_denied = attacker_allowed = attacker_denied = 0
    for tick in range(ticks):
        # Deliberately give the abusive peer first chance each 10 ms tick.
        for _ in range(3):
            if limiter.allow("abusive-peer"):
                attacker_allowed += 1
            else:
                attacker_denied += 1
        if tick % 5 == 0:  # four controllers x 20 rps = 80 rps total
            for peer in ("controller-a", "controller-b", "controller-c", "controller-d"):
                if limiter.allow(peer):
                    controllers_allowed += 1
                else:
                    controllers_denied += 1
        now[0] += 0.01
    return {
        "durationSeconds": round(ticks * 0.01, 3),
        "controllersAllowed": controllers_allowed,
        "controllersDenied": controllers_denied,
        "attackerAllowed": attacker_allowed,
        "attackerDenied": attacker_denied,
        "passed": controllers_denied == 0 and attacker_denied > 0,
    }
