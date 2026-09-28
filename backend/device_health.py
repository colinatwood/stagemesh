"""Validation and fail-closed interpretation for cross-domain device health."""

from __future__ import annotations

from typing import Any


STATES = {"unknown", "safe", "prepared", "armed", "active", "stopped", "faulted"}
QUALITIES = {"unknown", "good", "degraded", "stale", "fault"}


def validate_health(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["health telemetry must be an object"]
    errors = []
    if value.get("schema") != "stagemesh.device-health": errors.append("schema must be stagemesh.device-health")
    if value.get("version") != "1.0": errors.append("version must be 1.0")
    if not isinstance(value.get("deviceId"), str) or not value.get("deviceId"): errors.append("deviceId must be non-empty")
    for field in ("observedAtMonotonicNs", "sequence"):
        if isinstance(value.get(field), bool) or not isinstance(value.get(field), int) or value[field] < 0: errors.append(f"{field} must be a non-negative integer")
    if value.get("state") not in STATES: errors.append("state is unsupported")
    if value.get("quality") not in QUALITIES: errors.append("quality is unsupported")
    for field in ("freshnessMs", "latencyMs", "jitterMs"):
        if field in value and (isinstance(value[field], bool) or not isinstance(value[field], (int, float)) or value[field] < 0): errors.append(f"{field} must be non-negative")
    authority = value.get("authority")
    if not isinstance(authority, dict): errors.append("authority must be an object")
    else:
        for field in ("localAuthority", "leaseValid", "physicalInterlock", "emergencyStop"):
            if not isinstance(authority.get(field), bool): errors.append(f"authority.{field} must be boolean")
    if not isinstance(value.get("faults", []), list) or any(not isinstance(item, str) for item in value.get("faults", [])): errors.append("faults must be a string array")
    if value.get("physicalOutputsArmed") is not False: errors.append("physicalOutputsArmed must be false")
    return errors


def assess_health(
    value: dict[str, Any],
    *,
    max_freshness_ms: float = 2500.0,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors = validate_health(value)
    if errors:
        return {"status": "unknown", "safeToUse": False, "reasons": errors, "physicalOutputsArmed": False}
    reasons: list[str] = []
    if previous is not None:
        if not isinstance(previous, dict) or previous.get("deviceId") != value["deviceId"]:
            reasons.append("telemetry device identity changed")
        elif value["sequence"] <= previous.get("sequence", -1):
            reasons.append("telemetry sequence replayed or out of order")
        elif value["observedAtMonotonicNs"] <= previous.get("observedAtMonotonicNs", -1):
            reasons.append("telemetry monotonic timestamp regressed")
    authority = value["authority"]
    if not all(authority[field] for field in ("localAuthority", "leaseValid", "physicalInterlock", "emergencyStop")):
        reasons.append("authority or safety interlock unavailable")
    if value["quality"] == "fault" or value["state"] == "faulted" or value.get("faults"):
        reasons.append("device reports a fault")
    if value["quality"] == "stale" or float(value["freshnessMs"]) > max(0.0, float(max_freshness_ms)):
        reasons.append("telemetry is stale")
    if value["quality"] == "unknown" or value["state"] == "unknown":
        reasons.append("device health is unknown")
    if reasons:
        status = "fault" if any("fault" in reason or "authority" in reason for reason in reasons) else ("stale" if "telemetry is stale" in reasons else "degraded")
    else:
        status = "healthy"
    return {"deviceId": value["deviceId"], "sequence": value["sequence"], "status": status, "safeToUse": status == "healthy", "reasons": reasons, "physicalOutputsArmed": False}
