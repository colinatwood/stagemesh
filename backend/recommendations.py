from __future__ import annotations

from typing import Any


GOALS = {"balanced", "clarity", "low-latency", "reliability", "recording", "mobility"}


def _text(value: Any, *, maximum: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("recommendation text inputs must be strings")
    value = " ".join(value.strip().split())
    if len(value) > maximum:
        raise ValueError(f"recommendation text input must not exceed {maximum} characters")
    return value


def _recommendation(
    identifier: str,
    title: str,
    summary: str,
    *,
    category: str,
    priority: str,
    confidence: str,
    evidence: list[str],
    why: str,
    target: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "title": title,
        "summary": summary,
        "category": category,
        "priority": priority,
        "confidence": confidence,
        "evidence": evidence,
        "why": why,
        "actionTarget": target,
        "automaticApply": False,
        "physicalOutputsArmed": False,
    }


def build_recommendations(
    state: dict[str, Any],
    audio_inventory: dict[str, Any],
    midi_inventory: dict[str, Any],
    adapter_plan: dict[str, Any],
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build bounded, explainable local recommendations without mutating show state."""
    if request is None:
        request = {}
    if not isinstance(request, dict):
        raise ValueError("recommendation request must be an object")
    unexpected = sorted(set(request) - {"playerId", "goal", "notes"})
    if unexpected:
        raise ValueError(f"unexpected recommendation field: {unexpected[0]}")
    player_id = _text(request.get("playerId"), maximum=64)
    goal = _text(request.get("goal", "balanced"), maximum=32).lower() or "balanced"
    notes = _text(request.get("notes"), maximum=1000).lower()
    if goal not in GOALS:
        raise ValueError(f"goal must be one of: {', '.join(sorted(GOALS))}")

    players = [item for item in state.get("players", []) if isinstance(item, dict)]
    player = next((item for item in players if str(item.get("id", "")) == player_id), None) if player_id else None
    if player_id and player is None:
        raise ValueError("selected performer is not present in the current show")

    system = state.get("system") or {}
    audio = state.get("audio") or {}
    audio_devices = [item for item in audio_inventory.get("devices", []) if isinstance(item, dict)]
    midi_devices = [item for item in midi_inventory.get("devices", []) if isinstance(item, dict)]
    physical_outputs = [item for item in audio_devices if item.get("output") and str(item.get("backend", "")) not in {"null", "bridge-only"}]
    physical_inputs = [item for item in audio_devices if item.get("input") and str(item.get("backend", "")) not in {"null", "bridge-only"}]
    connected_midi = [item for item in midi_devices if item.get("attached") or item.get("connected", True)]
    bindings = midi_inventory.get("bindings") or {}
    performer_inputs = [item for item in audio.get("inputs", []) if player and item.get("playerId") == player.get("id") and item.get("deviceId")]
    performer_midi = [device_id for device_id, assigned in bindings.items() if player and assigned == player.get("id")]
    capacity = max(0.0, min(100.0, float(system.get("capacity", 0.0))))
    mode = str(system.get("mode", "safe"))
    role = str((player or {}).get("role", "show")).lower()
    recommendations: list[dict[str, Any]] = []

    if not physical_outputs:
        recommendations.append(_recommendation(
            "verify-audio-output", "Verify one physical audio output",
            "Select and preflight a connected output before rehearsal; keep activation manual.",
            category="hardware", priority="critical", confidence="high",
            evidence=["No physical output endpoint is currently available", f"Configured output: {audio.get('deviceId', 'none')}"],
            why="StageMesh cannot validate audible routing or loss recovery through a null or bridge-only endpoint.", target="#operations",
        ))
    elif not audio_inventory.get("desiredConnected"):
        recommendations.append(_recommendation(
            "reconcile-audio-output", "Reconnect the configured audio output",
            "Choose a currently connected endpoint or explicitly reconcile its recorded identity.",
            category="hardware", priority="critical", confidence="high",
            evidence=[f"{len(physical_outputs)} physical output endpoint(s) detected", "Configured output is not connected"],
            why="An unavailable desired endpoint must fail closed rather than silently selecting a replacement.", target="#operations",
        ))
    else:
        recommendations.append(_recommendation(
            "preflight-audio-output", "Run endpoint preflight before the show",
            "Confirm sample rate, channel count, buffer, and selected-endpoint identity before activation.",
            category="hardware", priority="medium", confidence="high",
            evidence=[f"{len(physical_outputs)} physical output endpoint(s) detected", "Configured output is connected"],
            why="A connected endpoint still needs exact-format and post-start identity validation.", target="#operations",
        ))

    if player:
        display_name = str(player.get("name", player_id))
        if not performer_inputs and (goal == "recording" or any(word in notes for word in ("record", "mic", "vocal", "input"))):
            recommendations.append(_recommendation(
                "assign-performer-input", f"Assign an input to {display_name}",
                "Route a verified capture endpoint to this performer before preparing a take.",
                category="routing", priority="high", confidence="high",
                evidence=[f"No configured audio input is assigned to {display_name}", f"{len(physical_inputs)} physical input endpoint(s) detected"],
                why="Recording and performer-specific processing need an explicit, reviewable source assignment.", target="#operations",
            ))
        if not performer_midi and connected_midi and ("keys" in role or "drum" in role or goal == "mobility" or "controller" in notes):
            recommendations.append(_recommendation(
                "bind-performer-controller", f"Offer a controller to {display_name}",
                "Use MIDI Learn for one intentional control, then test disconnect and reconnect behavior.",
                category="control", priority="medium", confidence="medium",
                evidence=[f"{len(connected_midi)} MIDI device(s) detected", f"No desired MIDI binding exists for {display_name}"],
                why="A role-aware binding reduces manual setup without coupling the show role to a transient device ID.", target="#operations",
            ))

        monitor = player.get("monitor") or {}
        if "drum" in role or goal == "low-latency" or "click" in notes:
            recommendations.append(_recommendation(
                "protect-performer-timing", f"Protect {display_name}'s timing path",
                "Prioritize the click and direct monitor path; defer background analysis if capacity falls.",
                category="performer", priority="high" if goal == "low-latency" else "medium", confidence="medium",
                evidence=[f"Role: {player.get('role', 'performer')}", f"Current click mix: {round(float(monitor.get('click', 0)))}%", f"Available capacity: {round(capacity)}%"],
                why="Timing-sensitive performers benefit from a short, stable path before spatial or analytical features.", target="#show-control",
            ))
        elif "vocal" in role or goal == "clarity" or any(word in notes for word in ("voice", "vocal", "speech", "clarity")):
            recommendations.append(_recommendation(
                "review-performer-clarity", f"Review {display_name}'s clarity mix",
                "Start with self, vocals, and talkback; keep band and ambience changes small and reversible.",
                category="performer", priority="medium", confidence="medium",
                evidence=[f"Role: {player.get('role', 'performer')}", f"Self {round(float(monitor.get('self', 0)))}% · vocals {round(float(monitor.get('vocals', 0)))}%"],
                why="The role and stated goal suggest intelligibility is more useful than a generic monitor preset.", target="#show-control",
            ))
        elif "keys" in role:
            recommendations.append(_recommendation(
                "review-keyboard-control", f"Simplify {display_name}'s keyboard controls",
                "Map only the highest-value control first, then add pads or transport after reconnect testing.",
                category="control", priority="medium", confidence="medium",
                evidence=[f"Role: {player.get('role', 'performer')}", f"{len(performer_midi)} desired MIDI binding(s)"],
                why="A small control surface is easier to verify and recover during a live show.", target="#operations",
            ))

    if capacity < 55 or mode == "audio":
        recommendations.append(_recommendation(
            "protect-audio-core", "Use Audio Only protection mode",
            "Suspend AI analysis, visualization, and nonessential processing until capacity recovers.",
            category="capacity", priority="critical", confidence="high",
            evidence=[f"Available capacity: {round(capacity)}%", f"Current mode: {mode}"],
            why="Core audio, transport, and show state must outrank advisory work.", target="#operations",
        ))
    elif capacity < 75 or mode in {"reduced", "safe"}:
        recommendations.append(_recommendation(
            "reduce-background-work", "Reduce background analysis",
            "Keep recommendations on demand and reduce visualization or spatial processing first.",
            category="capacity", priority="high", confidence="high",
            evidence=[f"Available capacity: {round(capacity)}%", f"Current mode: {mode}"],
            why="On-demand analysis preserves headroom while keeping the live path deterministic.", target="#operations",
        ))
    else:
        ai_decision = next((item for item in adapter_plan.get("decisions", []) if item.get("id") == "ai-connector"), {})
        recommendations.append(_recommendation(
            "retain-capacity-reserve", "Keep a rehearsal capacity reserve",
            "Use recommendations on demand and preserve headroom for device recovery or venue changes.",
            category="capacity", priority="low", confidence="high",
            evidence=[f"Available capacity: {round(capacity)}%", f"AI adapter policy: {ai_decision.get('status', 'unknown')}"],
            why="Healthy current capacity is not a reason to move advisory work into the real-time path.", target="#operations",
        ))

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recommendations.sort(key=lambda item: (order[item["priority"]], item["id"]))
    recommendations = recommendations[:4]
    blocking = sum(item["priority"] == "critical" for item in recommendations)
    return {
        "documentType": "org.stagemesh.advisor-recommendations",
        "schemaVersion": 1,
        "engine": "local-evidence-advisor-v1",
        "modelConnection": "not-configured",
        "privacy": "performer input is processed locally and is not retained by this endpoint",
        "generatedFromRevision": int(state.get("revision", 0)),
        "player": None if not player else {"id": player.get("id"), "name": player.get("name"), "role": player.get("role")},
        "goal": goal,
        "inputAcknowledged": bool(notes),
        "summary": "Resolve critical setup gaps before rehearsal." if blocking else "No critical setup gap was found; review the advisory items before rehearsal.",
        "hardwareSummary": {
            "audioOutputs": len(physical_outputs),
            "audioInputs": len(physical_inputs),
            "midiDevices": len(connected_midi),
            "capacityPercent": round(capacity, 1),
            "mode": mode,
        },
        "recommendations": recommendations,
        "automaticApply": False,
        "physicalOutputsArmed": False,
    }
