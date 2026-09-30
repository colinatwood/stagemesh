from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

SHOW_STATE_DOCUMENT_TYPE = "org.upp.show-state"
SHOW_STATE_API_VERSION = 1
SHOW_STATE_SCHEMA_VERSION = 1

QUALITY_ORDER = {
    "direct": 100,
    "equivalent": 95,
    "acceptable": 80,
    "degraded": 60,
    "unavailable": 0,
}

LEGACY_API_ALIASES = [
    {"legacy": "/api/v1/audio/stream", "current": "/api/v1/audio/outputs/0", "status": "supported"},
    {"legacy": "/api/v1/audio/activate", "current": "/api/v1/audio/outputs/0/activate", "status": "supported"},
    {"legacy": "/api/v1/audio/deactivate", "current": "/api/v1/audio/outputs/0/deactivate", "status": "supported"},
    {"legacy": "/api/v1/audio/input", "current": "/api/v1/audio/inputs/0", "status": "supported"},
    {"legacy": "/api/v1/audio/input/activate", "current": "/api/v1/audio/inputs/0/activate", "status": "supported"},
    {"legacy": "/api/v1/audio/input/deactivate", "current": "/api/v1/audio/inputs/0/deactivate", "status": "supported"},
]

SCHEMA_MIGRATIONS = [
    {
        "documentType": SHOW_STATE_DOCUMENT_TYPE,
        "fromApiVersion": 0,
        "toApiVersion": 1,
        "losslessUnknownPreservation": True,
        "semanticGuessing": False,
    }
]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compatibility_metadata(*, source_api_version: int | None = None, migrations: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "documentType": SHOW_STATE_DOCUMENT_TYPE,
        "schemaVersion": SHOW_STATE_SCHEMA_VERSION,
        "minimumReaderApiVersion": SHOW_STATE_API_VERSION,
        "unknownFieldsPreserved": True,
    }
    if source_api_version is not None and source_api_version != SHOW_STATE_API_VERSION:
        result["sourceApiVersion"] = int(source_api_version)
    if migrations:
        result["migrations"] = list(migrations)
    return result


def inspect_show_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {
            "readable": False,
            "mode": "invalid",
            "reason": "show state must be an object",
            "readerApiVersion": SHOW_STATE_API_VERSION,
        }
    incoming = _as_int(snapshot.get("apiVersion", 0), 0)
    meta = snapshot.get("compatibility") if isinstance(snapshot.get("compatibility"), dict) else {}
    minimum_reader = _as_int(meta.get("minimumReaderApiVersion", incoming if incoming > 0 else 1), incoming if incoming > 0 else 1)
    document_type = str(meta.get("documentType", SHOW_STATE_DOCUMENT_TYPE))
    if document_type != SHOW_STATE_DOCUMENT_TYPE:
        return {
            "readable": False,
            "mode": "wrong-document-type",
            "reason": f"unsupported document type: {document_type}",
            "incomingApiVersion": incoming,
            "minimumReaderApiVersion": minimum_reader,
            "readerApiVersion": SHOW_STATE_API_VERSION,
        }
    if incoming <= 0:
        return {
            "readable": True,
            "mode": "legacy-migration",
            "incomingApiVersion": incoming,
            "minimumReaderApiVersion": minimum_reader,
            "readerApiVersion": SHOW_STATE_API_VERSION,
            "preserveUnknown": True,
        }
    if minimum_reader > SHOW_STATE_API_VERSION:
        return {
            "readable": False,
            "mode": "reader-too-old",
            "reason": f"document requires reader API {minimum_reader}, this core supports {SHOW_STATE_API_VERSION}",
            "incomingApiVersion": incoming,
            "minimumReaderApiVersion": minimum_reader,
            "readerApiVersion": SHOW_STATE_API_VERSION,
        }
    return {
        "readable": True,
        "mode": "exact" if incoming == SHOW_STATE_API_VERSION else ("forward-compatible" if incoming > SHOW_STATE_API_VERSION else "legacy-migration"),
        "incomingApiVersion": incoming,
        "minimumReaderApiVersion": minimum_reader,
        "readerApiVersion": SHOW_STATE_API_VERSION,
        "preserveUnknown": True,
    }


def migrate_show_state(snapshot: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Normalize a readable show state to API v1 while preserving unknown data.

    API v0 is intentionally tiny and exists only as a compatibility bridge for
    early StageMesh development snapshots. New migrations should be explicit,
    deterministic and reversible at the data level; never guess semantic
    equivalence for unknown fields.
    """
    report = inspect_show_state(snapshot)
    if not report.get("readable"):
        raise ValueError(report.get("reason", "show state is not readable by this core"))
    source = deepcopy(snapshot)
    incoming = _as_int(source.get("apiVersion", 0), 0)
    migrations: list[str] = []

    if incoming <= 0:
        transport = source.get("transport") if isinstance(source.get("transport"), dict) else {}
        if "tempo" in transport and "bpm" not in transport:
            transport["bpm"] = transport.get("tempo")
            migrations.append("transport.tempo->transport.bpm")
        if "positionSeconds" in transport and "seconds" not in transport:
            transport["seconds"] = transport.get("positionSeconds")
            migrations.append("transport.positionSeconds->transport.seconds")
        if transport:
            source["transport"] = transport

        system = source.get("system") if isinstance(source.get("system"), dict) else {}
        if "resourceCapacity" in system and "capacity" not in system:
            system["capacity"] = system.get("resourceCapacity")
            migrations.append("system.resourceCapacity->system.capacity")
        if system:
            source["system"] = system

        audio = source.get("audio") if isinstance(source.get("audio"), dict) else {}
        if "outputDeviceId" in audio and "deviceId" not in audio:
            audio["deviceId"] = audio.get("outputDeviceId")
            migrations.append("audio.outputDeviceId->audio.deviceId")
        if audio:
            source["audio"] = audio

    # Internally we operate on v1 semantics, but the original complete object is
    # retained as the forward-compatibility overlay by ShowState.
    source["apiVersion"] = SHOW_STATE_API_VERSION
    existing_meta = source.get("compatibility") if isinstance(source.get("compatibility"), dict) else {}
    meta = dict(existing_meta)
    meta.update(compatibility_metadata(source_api_version=incoming, migrations=migrations))
    # Preserve a future document's declared minimum reader when it is lower/equal
    # to us, rather than unnecessarily raising it during a no-op edit.
    if incoming > SHOW_STATE_API_VERSION:
        declared = _as_int(existing_meta.get("minimumReaderApiVersion", SHOW_STATE_API_VERSION), SHOW_STATE_API_VERSION)
        meta["minimumReaderApiVersion"] = min(declared, SHOW_STATE_API_VERSION)
        meta["sourceApiVersion"] = incoming
    source["compatibility"] = meta
    report = dict(report)
    report["migrations"] = migrations
    report["normalizedApiVersion"] = SHOW_STATE_API_VERSION
    return source, report


def merge_preserving_unknown(base: Any, current: Any) -> Any:
    """Overlay known/current values while retaining unknown dictionary fields."""
    if isinstance(base, dict) and isinstance(current, dict):
        merged = deepcopy(base)
        for key, value in current.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = merge_preserving_unknown(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(current)


def _capability_set(values: Iterable[Any]) -> set[str]:
    return {str(value).strip() for value in values if str(value).strip()}


def _normalize_versions(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    result: set[int] = set()
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            result.add(parsed)
    return sorted(result)


def _normalize_adapters(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in values:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("from", "")).strip()
        target = str(raw.get("to", "")).strip()
        if not source or not target:
            continue
        quality = str(raw.get("quality", "acceptable")).strip().lower()
        if quality not in QUALITY_ORDER:
            quality = "acceptable"
        result.append({
            **raw,
            "from": source,
            "to": target,
            "quality": quality,
            "qualityScore": QUALITY_ORDER[quality],
            "explicit": True,
        })
    return result


def normalize_participant(data: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(data or {})
    api_versions = _normalize_versions(raw.get("apiVersions")) or [SHOW_STATE_API_VERSION]
    schemas: dict[str, list[int]] = {}
    if isinstance(raw.get("schemaVersions"), dict):
        for name, versions in raw["schemaVersions"].items():
            normalized = _normalize_versions(versions)
            if normalized:
                schemas[str(name)] = normalized
    schemas.setdefault(SHOW_STATE_DOCUMENT_TYPE, [SHOW_STATE_SCHEMA_VERSION])
    return {
        **raw,
        "id": str(raw.get("id", "participant")).strip()[:128] or "participant",
        "apiVersions": api_versions,
        "schemaVersions": schemas,
        "capabilities": sorted(_capability_set(raw.get("capabilities") or [])),
        "requiredCapabilities": sorted(_capability_set(raw.get("requiredCapabilities") or [])),
        "adapters": _normalize_adapters(raw.get("adapters")),
        "preservesUnknown": bool(raw.get("preservesUnknown", True)),
        "offlineCapable": bool(raw.get("offlineCapable", True)),
    }


def compatibility_report(local_data: dict[str, Any], remote_data: dict[str, Any]) -> dict[str, Any]:
    local = normalize_participant(local_data)
    remote = normalize_participant(remote_data)
    common_api = sorted(set(local["apiVersions"]) & set(remote["apiVersions"]))
    selected_api = common_api[-1] if common_api else None

    schema_matches: dict[str, Any] = {}
    all_schema_names = sorted(set(local["schemaVersions"]) | set(remote["schemaVersions"]))
    for name in all_schema_names:
        common = sorted(set(local["schemaVersions"].get(name, [])) & set(remote["schemaVersions"].get(name, [])))
        schema_matches[name] = {
            "selected": common[-1] if common else None,
            "common": common,
            "local": local["schemaVersions"].get(name, []),
            "remote": remote["schemaVersions"].get(name, []),
        }

    local_caps = set(local["capabilities"])
    remote_caps = set(remote["capabilities"])
    direct = sorted(local_caps & remote_caps)
    translations: list[dict[str, Any]] = []
    translated_remote: set[str] = set()
    translated_local: set[str] = set()
    for adapter in local["adapters"] + remote["adapters"]:
        source, target = adapter["from"], adapter["to"]
        if source in local_caps and target in remote_caps:
            translations.append({**adapter, "direction": "local-to-remote"})
            translated_local.add(source)
            translated_remote.add(target)
        elif source in remote_caps and target in local_caps:
            translations.append({**adapter, "direction": "remote-to-local"})
            translated_remote.add(source)
            translated_local.add(target)

    missing_for_local = sorted(set(local["requiredCapabilities"]) - (remote_caps | translated_local))
    missing_for_remote = sorted(set(remote["requiredCapabilities"]) - (local_caps | translated_remote))
    local_only = sorted(local_caps - remote_caps - translated_local)
    remote_only = sorted(remote_caps - local_caps - translated_remote)

    blockers: list[str] = []
    if selected_api is None:
        blockers.append("no common API version")
    show_schema = schema_matches.get(SHOW_STATE_DOCUMENT_TYPE, {})
    if show_schema.get("selected") is None:
        blockers.append("no common show-state schema version")
    if missing_for_local:
        blockers.append("remote lacks local required capabilities: " + ", ".join(missing_for_local))
    if missing_for_remote:
        blockers.append("local lacks remote required capabilities: " + ", ".join(missing_for_remote))
    if (local_only or remote_only) and not (local["preservesUnknown"] and remote["preservesUnknown"]):
        blockers.append("unknown capability preservation is not supported by both participants")

    qualities = [100] * len(direct) + [int(item["qualityScore"]) for item in translations]
    capability_quality = round(sum(qualities) / len(qualities), 1) if qualities else (100.0 if not local_caps and not remote_caps else 0.0)
    grade = "direct"
    if blockers:
        grade = "blocked"
    elif translations:
        minimum = min((int(item["qualityScore"]) for item in translations), default=100)
        grade = "equivalent" if minimum >= 95 else ("acceptable" if minimum >= 80 else "degraded")
    elif local_only or remote_only:
        grade = "partial-preserved"

    return {
        "compatible": not blockers,
        "grade": grade,
        "selectedApiVersion": selected_api,
        "commonApiVersions": common_api,
        "schemas": schema_matches,
        "directCapabilities": direct,
        "translations": translations,
        "localOnlyPreserved": local_only,
        "remoteOnlyPreserved": remote_only,
        "missingForLocal": missing_for_local,
        "missingForRemote": missing_for_remote,
        "capabilityQuality": capability_quality,
        "unknownPreservation": bool(local["preservesUnknown"] and remote["preservesUnknown"]),
        "offlineCompatible": bool(local["offlineCapable"] and remote["offlineCapable"]),
        "blockers": blockers,
        "local": local,
        "remote": remote,
    }


def resolve_requirements(participant_data: dict[str, Any], requirements: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve show intent against one participant without implicit coercion.

    A requirement names a preferred semantic capability and may list explicit
    acceptable fallbacks. Participant-declared adapters may bridge one of its
    actual capabilities to the desired semantic capability. Anything else is
    preserved/unknown, never guessed.
    """
    participant = normalize_participant(participant_data)
    capabilities = set(participant["capabilities"])
    adapters = participant["adapters"]
    decisions: list[dict[str, Any]] = []
    blocked = 0
    minimum_score = 100

    for raw in requirements:
        if not isinstance(raw, dict):
            continue
        requirement_id = str(raw.get("id") or raw.get("preferred") or "requirement").strip()
        preferred = str(raw.get("preferred", "")).strip()
        required = bool(raw.get("required", True))
        choice: dict[str, Any] | None = None

        if preferred and preferred in capabilities:
            choice = {"capability": preferred, "mode": "direct", "quality": "direct", "qualityScore": 100}

        if choice is None and preferred:
            for adapter in adapters:
                source, target = adapter["from"], adapter["to"]
                if target == preferred and source in capabilities:
                    choice = {"capability": source, "mode": "adapter", "adapter": adapter, "quality": adapter["quality"], "qualityScore": adapter["qualityScore"]}
                    break
                if source == preferred and target in capabilities:
                    choice = {"capability": target, "mode": "adapter", "adapter": adapter, "quality": adapter["quality"], "qualityScore": adapter["qualityScore"]}
                    break

        alternatives = raw.get("alternatives") if isinstance(raw.get("alternatives"), list) else []
        if choice is None:
            for alternative in alternatives:
                if not isinstance(alternative, dict):
                    continue
                capability = str(alternative.get("capability", "")).strip()
                if capability not in capabilities:
                    continue
                quality = str(alternative.get("quality", "degraded")).lower()
                if quality not in QUALITY_ORDER:
                    quality = "degraded"
                choice = {"capability": capability, "mode": "fallback", "quality": quality, "qualityScore": QUALITY_ORDER[quality]}
                break

        if choice is None:
            score = 0 if required else 100
            decision = {
                "id": requirement_id,
                "preferred": preferred,
                "required": required,
                "status": "blocked" if required else "optional-unavailable",
                "quality": "unavailable" if required else "optional",
                "qualityScore": score,
                "reason": "no exact capability, explicit adapter, or declared fallback available",
            }
            if required:
                blocked += 1
                minimum_score = 0
        else:
            decision = {
                "id": requirement_id,
                "preferred": preferred,
                "required": required,
                "status": choice["mode"],
                **choice,
            }
            if required:
                minimum_score = min(minimum_score, int(choice["qualityScore"]))
        decisions.append(decision)

    if blocked:
        grade = "blocked"
    elif minimum_score >= 100:
        grade = "direct"
    elif minimum_score >= 95:
        grade = "equivalent"
    elif minimum_score >= 80:
        grade = "acceptable"
    else:
        grade = "degraded"
    return {
        "compatible": blocked == 0,
        "grade": grade,
        "minimumQualityScore": minimum_score,
        "blockedRequirements": blocked,
        "requirements": decisions,
        "participant": participant,
    }


def show_requirements_from_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive semantic show requirements without depending on runtime/hardware.

    This pure helper is shared by the live API and offline venue compatibility
    tooling so pre-arrival planning cannot drift away from runtime behavior.
    """
    audio = snapshot.get("audio") or {}
    lighting = (snapshot.get("lighting") or {}).get("network") or {}
    midi = snapshot.get("midi") or {}
    requirements: list[dict[str, Any]] = [
        {"id": "transport", "preferred": "audio.transport", "required": True, "domain": "audio",
         "timing": {"maxLatencyMs": 20.0, "maxJitterMs": 5.0, "timestamped": True}},
        {"id": "authority-fence", "preferred": "authority.fence", "required": True, "domain": "core"},
    ]
    outputs = audio.get("outputs") if isinstance(audio.get("outputs"), list) else []
    if any(str(item.get("deviceId", "")).strip() for item in outputs if isinstance(item, dict)):
        requirements.append({
            "id": "audio-output", "preferred": "audio.output.multi", "required": True, "domain": "audio", "patchKey": "audio.foh",
            "alternatives": [{"capability": "audio.mix", "quality": "acceptable"}],
            "timing": {"maxLatencyMs": 30.0, "maxJitterMs": 5.0, "timestamped": False},
        })
    inputs = audio.get("inputs") if isinstance(audio.get("inputs"), list) else []
    if any(str(item.get("deviceId", "")).strip() for item in inputs if isinstance(item, dict)):
        requirements.append({"id": "live-audio-input", "preferred": "audio.input.capture", "required": True, "domain": "audio", "patchKey": "audio.live-input",
                             "timing": {"maxLatencyMs": 15.0, "maxJitterMs": 3.0, "timestamped": False}})
    if isinstance(midi.get("bindings"), dict) and midi.get("bindings"):
        requirements.append({"id": "mapped-midi", "preferred": "midi.read", "required": True, "domain": "midi", "patchKey": "midi.performance",
                             "timing": {"maxLatencyMs": 20.0, "maxJitterMs": 5.0, "timestamped": True}})
    if str(lighting.get("target", "")).strip():
        lighting_protocol = str(lighting.get("protocol", "artnet")).strip().lower()
        preferred_lighting = "lighting.sacn.send" if lighting_protocol == "sacn" else "lighting.artnet.send"
        alternate_network = "lighting.artnet.send" if lighting_protocol == "sacn" else "lighting.sacn.send"
        requirements.append({
            "id": "lighting-output", "preferred": preferred_lighting, "required": True, "domain": "lighting", "patchKey": "lighting.primary",
            "alternatives": [
                {"capability": alternate_network, "quality": "equivalent"},
                {"capability": "lighting.schedule", "quality": "acceptable"},
                {"capability": "lighting.state", "quality": "degraded"},
            ],
            "timing": {"maxLatencyMs": 100.0, "maxJitterMs": 25.0, "timestamped": False},
        })
    requirements.append({"id": "personal-monitoring", "preferred": "audio.monitor", "required": False, "domain": "audio", "patchKey": "audio.monitor"})
    return requirements
