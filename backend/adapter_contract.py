"""Vendor-neutral adapter manifest audit and deterministic capability selection."""

from __future__ import annotations

from typing import Any, Iterable


REQUIRED = {"id", "name", "kind", "priority", "capabilities", "fallbacks"}
KINDS = {"audio", "lighting", "video", "robotics", "sensor", "controller", "bridge", "midi", "simulator", "core", "production", "notation", "visual", "governance", "ai"}


def validate_manifest(value: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["manifest must be an object"]
    missing = sorted(REQUIRED - set(value))
    errors.extend(f"missing required field: {field}" for field in missing)
    if not isinstance(value.get("id"), str) or not value.get("id"):
        errors.append("id must be a non-empty string")
    if not isinstance(value.get("name"), str) or not value.get("name"):
        errors.append("name must be a non-empty string")
    if value.get("kind") not in KINDS:
        errors.append("kind is unsupported")
    priority = value.get("priority")
    if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 5:
        errors.append("priority must be an integer from 0 through 5")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities or any(not isinstance(item, str) or not item for item in capabilities):
        errors.append("capabilities must be a non-empty string array")
    elif len(set(capabilities)) != len(capabilities):
        errors.append("capabilities must be unique")
    fallbacks = value.get("fallbacks")
    if not isinstance(fallbacks, list) or not fallbacks or any(not isinstance(item, str) or not item for item in fallbacks):
        errors.append("fallbacks must be a non-empty string array")
    if "estimatedCpu" in value and (isinstance(value["estimatedCpu"], bool) or not isinstance(value["estimatedCpu"], (int, float)) or value["estimatedCpu"] < 0):
        errors.append("estimatedCpu must be non-negative")
    if "estimatedMemoryMb" in value and (isinstance(value["estimatedMemoryMb"], bool) or not isinstance(value["estimatedMemoryMb"], int) or value["estimatedMemoryMb"] < 0):
        errors.append("estimatedMemoryMb must be a non-negative integer")
    for field in ("realtime", "documentedInterface", "supportsSafeStop", "readOnly", "physicalOutput"):
        if field in value and not isinstance(value[field], bool):
            errors.append(f"{field} must be boolean")
    if value.get("physicalOutput") is True:
        if value.get("documentedInterface") is not True:
            errors.append("physical-output adapters require documentedInterface=true")
        if value.get("supportsSafeStop") is not True:
            errors.append("physical-output adapters require supportsSafeStop=true")
        if value.get("safetyContract") != "stagemesh.device-safety-contract@1.0":
            errors.append("physical-output adapters require the device safety contract")
    if value.get("directPhysicalCommands") is True:
        errors.append("directPhysicalCommands is forbidden; adapters expose bounded intent only")
    return errors


def audit_manifests(values: Iterable[object]) -> dict[str, Any]:
    results = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        errors = validate_manifest(value)
        adapter_id = value.get("id") if isinstance(value, dict) else f"manifest-{index}"
        if isinstance(adapter_id, str) and adapter_id in seen:
            errors.append("duplicate adapter id")
        if isinstance(adapter_id, str):
            seen.add(adapter_id)
        results.append({"id": adapter_id, "valid": not errors, "errors": errors, "physicalOutputsArmed": False})
    return {"valid": all(item["valid"] for item in results), "manifests": results, "physicalOutputsArmed": False}


def select_capability(values: Iterable[dict[str, Any]], required: Iterable[str], *, mode: str = "full") -> dict[str, Any]:
    required_set = {str(item).strip() for item in required if str(item).strip()}
    candidates = []
    for value in values:
        if validate_manifest(value):
            continue
        if not required_set.issubset(set(value.get("capabilities", []))):
            continue
        if mode != "full" and value.get("realtime") and mode == "safe":
            continue
        candidates.append(value)
    selected = sorted(candidates, key=lambda item: (int(item.get("priority", 5)), str(item.get("id"))))[0] if candidates else None
    return {"selected": selected.get("id") if selected else None, "candidates": [item.get("id") for item in sorted(candidates, key=lambda item: (int(item.get("priority", 5)), str(item.get("id"))))], "requiredCapabilities": sorted(required_set), "physicalOutputsArmed": False}
