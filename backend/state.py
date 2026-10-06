from __future__ import annotations

from dataclasses import dataclass, field, asdict
from ipaddress import IPv4Address
from threading import Condition, RLock
from time import monotonic, time
from typing import Any

from notation import NotationRegistry
from handoff import DEFAULT_HANDOFF_POLICY, default_live_input_redundancy, normalize_deterministic_sources, normalize_live_inputs, normalize_policy
from technology import DEFAULT_TECHNOLOGY_POLICY, normalize_technology_extensions, normalize_technology_policy
from compatibility import compatibility_metadata, inspect_show_state, migrate_show_state, merge_preserving_unknown


MONITOR_KEYS = ("master", "self", "vocals", "band", "click", "talkback", "ambient")
SYSTEM_MODES = {"full", "reduced", "safe", "audio"}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class RevisionConflict(RuntimeError):
    def __init__(self, expected: int, actual: int, scope: str = "global") -> None:
        super().__init__(f"revision conflict for {scope}: expected {expected}, current {actual}")
        self.expected = expected
        self.actual = actual
        self.scope = scope


@dataclass
class MonitorMix:
    master: float = 72.0
    self: float = 76.0
    vocals: float = 58.0
    band: float = 62.0
    click: float = 38.0
    talkback: float = 45.0
    ambient: float = 28.0
    muted: bool = False
    output: str = "IEM A"

    def patch(self, data: dict[str, Any]) -> None:
        for key in MONITOR_KEYS:
            if key in data:
                setattr(self, key, clamp(float(data[key]), 0.0, 100.0))
        if "muted" in data:
            self.muted = bool(data["muted"])
        if "output" in data:
            value = str(data["output"]).strip()
            if value:
                self.output = value[:64]


@dataclass
class Player:
    id: str
    name: str
    role: str
    monitor: MonitorMix = field(default_factory=MonitorMix)
    mode: str = "local"
    available: bool = True


class ShowState:
    """Authoritative non-audio show state for the development bridge.

    The native StageMesh core can later implement this contract. The UI never
    owns transport/player state. Revisions make concurrent control points
    explicit rather than silently last-write-wins.
    """

    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        self._lock = RLock()
        self._event_condition = Condition(self._lock)
        self._running = False
        self._elapsed = 0.0
        self._started_at = monotonic()
        self._bpm = 120.0
        self._key = "C"
        self._capacity = 78.0
        self._system_mode = "full"
        self._venue = "Small Club"
        self._production_manager = "Touring Default"
        self._audio_device_id = "null-audio"
        self._audio_input_device_id = ""
        self._audio_input_player_id = ""
        self._audio_input_route_output = 0
        self._audio_input_route_gain = 0.0
        self._audio_inputs: list[dict[str, Any]] = [
            {"slot": slot, "deviceId": "", "playerId": "", "sampleRate": 192000.0, "route": {"output": 0, "gain": 0.0}}
            for slot in range(4)
        ]
        self._audio_outputs: list[dict[str, Any]] = [
            {
                "slot": slot,
                "deviceId": "null-audio" if slot == 0 else "",
                "purpose": "foh" if slot == 0 else ("monitor" if slot in {1, 2} else "broadcast"),
                "playerId": "",
                "graphOutput": 0 if slot == 0 else slot,
                "master": 1.0,
                "limiterCeilingDb": -1.0,
                "driftCompensation": {"enabled": True, "maxCorrectionPpm": 2000.0, "queueGainPpm": 1000.0},
            }
            for slot in range(4)
        ]
        self._audio_sample_rate = 192000.0
        self._audio_buffer_frames = 256
        self._audio_limiter_ceiling_db = -1.0
        self._lighting_protocol = "artnet"
        self._lighting_target = ""
        self._lighting_port = 6454
        self._lighting_universe_base = 1
        self._handoff_policy = dict(DEFAULT_HANDOFF_POLICY)
        self._handoff_live_inputs = default_live_input_redundancy()
        self._handoff_deterministic_sources: list[dict[str, Any]] = []
        self._technology_policy = dict(DEFAULT_TECHNOLOGY_POLICY)
        self._technology_ecosystem_participants = 1
        self._technology_extensions: list[dict[str, Any]] = []
        self._compatibility_overlay: dict[str, Any] = {}
        self._compatibility_report: dict[str, Any] = {"readable": True, "mode": "new", "readerApiVersion": 1}
        self._revision = 1
        self._resource_revisions: dict[str, int] = {"transport": 1, "show": 1, "system": 1, "midi-bindings": 1, "audio": 1, "lighting-network": 1, "handoff": 1, "technology": 1}
        self._next_event_id = 1
        self._events: list[dict[str, Any]] = []
        self._players: dict[str, Player] = self._default_players()
        self._midi_bindings: dict[str, str] = {}
        self._midi_received = 0
        self._midi_activity: list[dict[str, Any]] = []
        self._notation = NotationRegistry(list(self._players))
        for player_id in self._players:
            self._resource_revisions[f"monitor:{player_id}"] = 1
            self._resource_revisions[f"midi:{player_id}"] = 1
            self._resource_revisions[f"notation:{player_id}"] = 1

        if snapshot:
            normalized_snapshot, compatibility_report = migrate_show_state(snapshot)
            self._compatibility_overlay = normalized_snapshot
            self._compatibility_report = compatibility_report
            self._restore(normalized_snapshot)
            self._event("recovery", "Recovered persisted show state; transport held paused")
        else:
            self._event("system", "Development show state initialized")

    @staticmethod
    def _default_players() -> dict[str, Player]:
        return {
            "alex": Player("alex", "Alex", "Drums", MonitorMix(self=82, click=42)),
            "sam": Player("sam", "Sam", "Bass", MonitorMix(self=74, click=28)),
            "maya": Player("maya", "Maya", "Keys", MonitorMix(vocals=70, ambient=36), mode="remote"),
            "jordan": Player("jordan", "Jordan", "Lead Vocal", MonitorMix(self=84, band=52, click=22)),
        }

    def _restore(self, snapshot: dict[str, Any], *, hold_transport: bool = True) -> None:
        transport = snapshot.get("transport") or {}
        system = snapshot.get("system") or {}
        self._elapsed = clamp(float(transport.get("seconds", 0.0)), 0.0, 7 * 24 * 3600.0)
        self._running = False if hold_transport else bool(transport.get("running", False))
        self._started_at = monotonic()
        self._bpm = clamp(float(transport.get("bpm", 120.0)), 30.0, 300.0)
        key = str(transport.get("key", "C")).strip()
        self._key = key[:12] or "C"
        self._capacity = clamp(float(system.get("capacity", 78.0)), 0.0, 100.0)
        mode = str(system.get("mode", "full")).strip().lower()
        self._system_mode = mode if mode in SYSTEM_MODES else "safe"
        self._venue = str(system.get("venue", "Small Club")).strip()[:80] or "Small Club"
        self._production_manager = str(system.get("productionManager", "Touring Default")).strip()[:80] or "Touring Default"
        handoff = snapshot.get("handoff") or {}
        self._handoff_policy = normalize_policy(handoff.get("policy") if isinstance(handoff, dict) else None)
        self._handoff_live_inputs = normalize_live_inputs(handoff.get("liveInputs") if isinstance(handoff, dict) else None)
        self._handoff_deterministic_sources = normalize_deterministic_sources(handoff.get("deterministicSources") if isinstance(handoff, dict) else None)
        technology = snapshot.get("technology")
        if isinstance(technology, dict) and technology:
            if "policy" in technology:
                self._technology_policy = normalize_technology_policy(technology.get("policy"))
            if "ecosystemParticipants" in technology:
                try:
                    self._technology_ecosystem_participants = max(1, min(1_000_000, int(technology.get("ecosystemParticipants", 1))))
                except (TypeError, ValueError):
                    pass
            # Live/replication summaries intentionally omit extensions. In that
            # case preserve the node-local catalog rather than replacing it.
            if "extensions" in technology:
                self._technology_extensions = normalize_technology_extensions(technology.get("extensions"))
        audio = snapshot.get("audio") or {}
        device_id = str(audio.get("deviceId", "null-audio")).strip()[:96]
        self._audio_device_id = device_id if device_id and not any(ch.isspace() for ch in device_id) else "null-audio"
        raw_inputs = audio.get("inputs")
        restored_inputs: list[dict[str, Any]] = [
            {"slot": slot, "deviceId": "", "playerId": "", "sampleRate": clamp(float(audio.get("sampleRate", 192000.0)), 8000.0, 768000.0), "route": {"output": 0, "gain": 0.0}}
            for slot in range(4)
        ]
        if isinstance(raw_inputs, list):
            for raw in raw_inputs[:16]:
                if not isinstance(raw, dict):
                    continue
                try:
                    slot = int(raw.get("slot", -1))
                except (TypeError, ValueError):
                    continue
                if not 0 <= slot < 4:
                    continue
                device_id = str(raw.get("deviceId", "")).strip()[:96]
                if device_id and any(ch.isspace() for ch in device_id):
                    device_id = ""
                player_id = str(raw.get("playerId", "")).strip()[:64]
                route = raw.get("route") or {}
                try:
                    output = max(0, min(15, int(route.get("output", 0))))
                    gain = clamp(float(route.get("gain", 0.0)), 0.0, 4.0)
                except (TypeError, ValueError):
                    output, gain = 0, 0.0
                input_rate = clamp(float(raw.get("sampleRate", audio.get("sampleRate", 192000.0))), 8000.0, 768000.0)
                restored_inputs[slot] = {"slot": slot, "deviceId": device_id, "playerId": player_id, "sampleRate": input_rate, "route": {"output": output, "gain": gain}}
        else:
            input_device_id = str(audio.get("inputDeviceId", "")).strip()[:96]
            if input_device_id and any(ch.isspace() for ch in input_device_id):
                input_device_id = ""
            restored_audio_input_player_id = str(audio.get("inputPlayerId", "")).strip()[:64]
            input_route = audio.get("inputRoute") or {}
            try:
                output = max(0, min(15, int(input_route.get("output", 0))))
                gain = clamp(float(input_route.get("gain", 0.0)), 0.0, 4.0)
            except (TypeError, ValueError):
                output, gain = 0, 0.0
            restored_inputs[0] = {"slot": 0, "deviceId": input_device_id, "playerId": restored_audio_input_player_id, "sampleRate": clamp(float(audio.get("sampleRate", 192000.0)), 8000.0, 768000.0), "route": {"output": output, "gain": gain}}
        # Compatibility aliases remain authoritative for slot 0 when explicitly
        # present. This lets older tools edit a current snapshot without knowing
        # about the multi-input array yet.
        if isinstance(raw_inputs, list):
            if "inputDeviceId" in audio:
                device_id = str(audio.get("inputDeviceId", "")).strip()[:96]
                if not (device_id and any(ch.isspace() for ch in device_id)):
                    restored_inputs[0]["deviceId"] = device_id
            if "inputPlayerId" in audio:
                restored_inputs[0]["playerId"] = str(audio.get("inputPlayerId", "")).strip()[:64]
            if "inputRoute" in audio and isinstance(audio.get("inputRoute"), dict):
                route = audio["inputRoute"]
                try:
                    restored_inputs[0]["route"] = {"output": max(0, min(15, int(route.get("output", 0)))), "gain": clamp(float(route.get("gain", 0.0)), 0.0, 4.0)}
                except (TypeError, ValueError):
                    pass
        self._audio_sample_rate = clamp(float(audio.get("sampleRate", 192000.0)), 8000.0, 768000.0)
        try:
            self._audio_buffer_frames = max(16, min(8192, int(audio.get("bufferFrames", 256))))
        except (TypeError, ValueError):
            self._audio_buffer_frames = 256
        self._audio_limiter_ceiling_db = clamp(float(audio.get("limiterCeilingDb", -1.0)), -24.0, 0.0)
        restored_outputs: list[dict[str, Any]] = [
            {
                "slot": slot,
                "deviceId": "null-audio" if slot == 0 else "",
                "purpose": "foh" if slot == 0 else ("monitor" if slot in {1, 2} else "broadcast"),
                "playerId": "",
                "graphOutput": 0 if slot == 0 else slot,
                "master": 1.0,
                "limiterCeilingDb": -1.0,
                "driftCompensation": {"enabled": True, "maxCorrectionPpm": 2000.0, "queueGainPpm": 1000.0},
            }
            for slot in range(4)
        ]
        raw_outputs = audio.get("outputs")
        if isinstance(raw_outputs, list):
            allowed_purposes = {"foh", "monitor", "broadcast", "record", "aux"}
            for raw in raw_outputs[:16]:
                if not isinstance(raw, dict):
                    continue
                try:
                    slot = int(raw.get("slot", -1))
                except (TypeError, ValueError):
                    continue
                if not 0 <= slot < 4:
                    continue
                current = restored_outputs[slot]
                out_device = str(raw.get("deviceId", current["deviceId"])).strip()[:96]
                if out_device and any(ch.isspace() for ch in out_device):
                    out_device = current["deviceId"]
                purpose = str(raw.get("purpose", current["purpose"])).strip().lower()
                if purpose not in allowed_purposes:
                    purpose = current["purpose"]
                player_id = str(raw.get("playerId", current["playerId"])).strip()[:64]
                drift_raw = raw.get("driftCompensation", current["driftCompensation"])
                if not isinstance(drift_raw, dict):
                    drift_raw = current["driftCompensation"]
                try:
                    graph_output = max(0, min(15, int(raw.get("graphOutput", current["graphOutput"]))))
                    master = clamp(float(raw.get("master", current["master"])), 0.0, 4.0)
                    ceiling = clamp(float(raw.get("limiterCeilingDb", current["limiterCeilingDb"])), -24.0, 0.0)
                    drift = {
                        "enabled": bool(drift_raw.get("enabled", current["driftCompensation"]["enabled"])),
                        "maxCorrectionPpm": clamp(float(drift_raw.get("maxCorrectionPpm", current["driftCompensation"]["maxCorrectionPpm"])), 0.0, 10000.0),
                        "queueGainPpm": clamp(float(drift_raw.get("queueGainPpm", current["driftCompensation"]["queueGainPpm"])), 0.0, 10000.0),
                    }
                except (TypeError, ValueError):
                    graph_output, master, ceiling = current["graphOutput"], current["master"], current["limiterCeilingDb"]
                    drift = dict(current["driftCompensation"])
                restored_outputs[slot] = {
                    "slot": slot, "deviceId": out_device, "purpose": purpose, "playerId": player_id,
                    "graphOutput": graph_output, "master": master, "limiterCeilingDb": ceiling, "driftCompensation": drift,
                }
        # Legacy top-level output fields remain slot-0 aliases when supplied.
        if not isinstance(raw_outputs, list) or "deviceId" in audio:
            restored_outputs[0]["deviceId"] = self._audio_device_id
        if not isinstance(raw_outputs, list) or "limiterCeilingDb" in audio:
            restored_outputs[0]["limiterCeilingDb"] = self._audio_limiter_ceiling_db
        self._audio_outputs = restored_outputs
        self._audio_device_id = str(restored_outputs[0]["deviceId"] or "null-audio")
        self._audio_limiter_ceiling_db = float(restored_outputs[0]["limiterCeilingDb"])
        lighting = snapshot.get("lighting") or {}
        network = lighting.get("network") or {}
        protocol = str(network.get("protocol", "artnet")).strip().lower()
        self._lighting_protocol = protocol if protocol in {"artnet", "sacn"} else "artnet"
        target = str(network.get("target", "")).strip()[:64]
        try:
            address = IPv4Address(target) if target else None
            if address and (address.is_multicast or address.is_unspecified or int(address) == 0xFFFFFFFF):
                target = ""
        except ValueError:
            target = ""
        self._lighting_target = target
        try:
            self._lighting_port = max(1, min(65535, int(network.get("port", 6454))))
        except (TypeError, ValueError):
            self._lighting_port = 6454
        try:
            self._lighting_universe_base = max(1, min(63984, int(network.get("universeBase", 1))))
        except (TypeError, ValueError):
            self._lighting_universe_base = 1
        self._revision = max(1, int(snapshot.get("revision", 1)))
        restored_resource_revisions = snapshot.get("resourceRevisions") or {}
        if isinstance(restored_resource_revisions, dict):
            for key, value in restored_resource_revisions.items():
                try:
                    self._resource_revisions[str(key)] = max(1, int(value))
                except (TypeError, ValueError):
                    continue

        players: dict[str, Player] = {}
        for raw in snapshot.get("players") or []:
            try:
                player_id = str(raw["id"]).strip()
                monitor_raw = raw.get("monitor") or {}
                monitor = MonitorMix()
                monitor.patch(monitor_raw)
                players[player_id] = Player(
                    id=player_id,
                    name=str(raw.get("name", player_id))[:80],
                    role=str(raw.get("role", "Player"))[:80],
                    monitor=monitor,
                    mode=str(raw.get("mode", "local"))[:32],
                    available=bool(raw.get("available", True)),
                )
            except (KeyError, TypeError, ValueError):
                continue
        if players:
            self._players = players
        for config in restored_inputs:
            if config["playerId"] and config["playerId"] not in self._players:
                config["playerId"] = ""
        for config in self._audio_outputs:
            if config["playerId"] and config["playerId"] not in self._players:
                config["playerId"] = ""
        self._audio_inputs = restored_inputs
        slot0 = self._audio_inputs[0]
        self._audio_input_device_id = str(slot0["deviceId"])
        self._audio_input_player_id = str(slot0["playerId"])
        self._audio_input_route_output = int(slot0["route"]["output"])
        self._audio_input_route_gain = float(slot0["route"]["gain"])

        midi = snapshot.get("midi") or {}
        raw_bindings = midi.get("bindings") or snapshot.get("midiBindings") or {}
        if isinstance(raw_bindings, dict):
            self._midi_bindings = {
                str(device_id)[:96]: str(player_id)[:64]
                for device_id, player_id in raw_bindings.items()
                if str(device_id).strip() and str(player_id) in self._players
            }
        try:
            self._midi_received = max(0, int(midi.get("received", 0)))
        except (TypeError, ValueError):
            self._midi_received = 0
        activity = midi.get("activity") or []
        if isinstance(activity, list):
            self._midi_activity = [dict(item) for item in activity[-512:] if isinstance(item, dict)]

        self._notation = NotationRegistry(list(self._players), snapshot.get("notation") or {})
        for player_id in self._players:
            self._resource_revisions.setdefault(f"monitor:{player_id}", 1)
            self._resource_revisions.setdefault(f"midi:{player_id}", 1)
            self._resource_revisions.setdefault(f"notation:{player_id}", 1)

        restored_events = []
        highest_event_id = 0
        for event in snapshot.get("events") or []:
            if not isinstance(event, dict):
                continue
            try:
                event_id = int(event.get("eventId", 0))
            except (TypeError, ValueError):
                continue
            highest_event_id = max(highest_event_id, event_id)
            restored_events.append(dict(event))
        self._events = restored_events[:100]
        self._next_event_id = max(highest_event_id + 1, 1)

    def apply_replica_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Replace authoritative state from a verified standby replication envelope.

        Unlike crash recovery, replication preserves the incoming running
        transport state so the standby clock can remain warm. Physical output
        authority is handled by StageMeshRuntime and is never implied here.
        """
        if not isinstance(snapshot, dict):
            raise ValueError("unsupported replica show state")
        normalized_snapshot, compatibility_report = migrate_show_state(snapshot)
        try:
            incoming_revision = int(normalized_snapshot["revision"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("replica state requires an integer revision") from exc
        with self._event_condition:
            if incoming_revision < self._revision:
                raise RevisionConflict(incoming_revision, self._revision, "replica")
            self._compatibility_overlay = normalized_snapshot
            self._compatibility_report = compatibility_report
            self._restore(normalized_snapshot, hold_transport=False)
            self._event_condition.notify_all()
            return self.snapshot()

    def _clock_seconds(self) -> float:
        if self._running:
            return self._elapsed + (monotonic() - self._started_at)
        return self._elapsed

    def _event(self, category: str, text: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._event_condition:
            event = {
                "eventId": self._next_event_id,
                "category": category,
                "text": text,
                "showTimeSeconds": round(self._clock_seconds(), 3),
                "wallTimeUnixMs": int(time() * 1000),
                "revision": self._revision,
                "payload": payload or {},
            }
            self._next_event_id += 1
            self._events.insert(0, event)
            del self._events[100:]
            self._event_condition.notify_all()
            return event

    def _touch_resources(self, *resource_keys: str) -> None:
        self._revision += 1
        for resource_key in dict.fromkeys(resource_keys):
            self._resource_revisions[resource_key] = self._resource_revisions.get(resource_key, 1) + 1

    def _touch(self, resource_key: str) -> None:
        self._touch_resources(resource_key)

    def _check_revision(
        self,
        expected_revision: int | None,
        resource_key: str,
        expected_resource_revision: int | None = None,
    ) -> None:
        if expected_resource_revision is not None:
            actual = self._resource_revisions.get(resource_key, 1)
            if expected_resource_revision != actual:
                raise RevisionConflict(expected_resource_revision, actual, resource_key)
            return
        if expected_revision is not None and expected_revision != self._revision:
            raise RevisionConflict(expected_revision, self._revision)

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def latest_event(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._events[0]) if self._events else None

    def events_since(self, event_id: int) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in reversed(self._events) if int(event.get("eventId", 0)) > event_id]

    def record_external_event(self, category: str, text: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record an audited non-show-state event without changing show revision.

        Environment/governance layers use this for transactions whose history
        matters but whose state intentionally lives outside the replicated show
        model.
        """
        with self._lock:
            return self._event(str(category)[:64], str(text)[:240], payload or {})

    def wait_for_events(self, event_id: int, timeout: float = 15.0) -> list[dict[str, Any]]:
        with self._event_condition:
            ready = self.events_since(event_id)
            if ready:
                return ready
            self._event_condition.wait(timeout=max(0.0, min(timeout, 30.0)))
            return self.events_since(event_id)

    def snapshot(self, notation_detail: bool = False, technology_detail: bool = False) -> dict[str, Any]:
        with self._lock:
            clock = self._clock_seconds()
            generated = {
                "apiVersion": 1,
                "compatibility": compatibility_metadata(),
                "revision": self._revision,
                "resourceRevisions": dict(self._resource_revisions),
                "transport": {
                    "running": self._running,
                    "seconds": round(clock, 3),
                    "bpm": self._bpm,
                    "key": self._key,
                },
                "system": {
                    "capacity": self._capacity,
                    "mode": self._system_mode,
                    "quality": self._quality_score(),
                    "venue": self._venue,
                    "productionManager": self._production_manager,
                },
                "audio": {
                    "deviceId": self._audio_device_id,
                    "inputDeviceId": self._audio_input_device_id,
                    "inputPlayerId": self._audio_input_player_id,
                    "inputRoute": {"output": self._audio_input_route_output, "gain": self._audio_input_route_gain},
                    "inputs": [
                        {"slot": int(item["slot"]), "deviceId": str(item["deviceId"]), "playerId": str(item["playerId"]), "sampleRate": float(item["sampleRate"]), "route": dict(item["route"])}
                        for item in self._audio_inputs
                    ],
                    "outputs": [
                        {
                            "slot": int(item["slot"]), "deviceId": str(item["deviceId"]), "purpose": str(item["purpose"]),
                            "playerId": str(item["playerId"]), "graphOutput": int(item["graphOutput"]),
                            "master": float(item["master"]), "limiterCeilingDb": float(item["limiterCeilingDb"]),
                            "driftCompensation": dict(item["driftCompensation"]),
                        }
                        for item in self._audio_outputs
                    ],
                    "sampleRate": self._audio_sample_rate,
                    "engineSampleRate": 192000.0,
                    "engineSampleFormat": "float32",
                    "bufferFrames": self._audio_buffer_frames,
                    "limiterCeilingDb": self._audio_limiter_ceiling_db,
                },
                "handoff": {
                    "policy": dict(self._handoff_policy),
                    "liveInputs": [dict(item) for item in self._handoff_live_inputs],
                    "deterministicSources": [dict(item) for item in self._handoff_deterministic_sources],
                },
                "technology": {
                    "policy": dict(self._technology_policy),
                    "ecosystemParticipants": self._technology_ecosystem_participants,
                    "extensionCount": len(self._technology_extensions),
                    **({"extensions": [dict(item) for item in self._technology_extensions]} if technology_detail else {}),
                },
                "lighting": {
                    "network": {
                        "protocol": self._lighting_protocol,
                        "target": self._lighting_target,
                        "port": self._lighting_port,
                        "universeBase": self._lighting_universe_base,
                        "armed": False,
                    }
                },
                "players": [asdict(player) for player in self._players.values()],
                "midi": {
                    "bindings": dict(self._midi_bindings),
                    "received": self._midi_received,
                    "activity": list(self._midi_activity[-512:] if notation_detail else self._midi_activity[-16:]),
                },
                "notation": self._notation.snapshot(self._key, include_raw=notation_detail, note_limit=None if notation_detail else 16),
                "events": list(self._events),
            }
            # A compatible newer document may contain fields this core does not
            # understand. Keep them byte-for-JSON-value intact while current
            # known fields overwrite their older values. This is the core of
            # UPP forward-compatible read/edit/write behavior.
            merged = merge_preserving_unknown(self._compatibility_overlay, generated)
            output_api_version = int(self._compatibility_report.get("incomingApiVersion", 1)) if self._compatibility_report.get("mode") == "forward-compatible" else 1
            merged["apiVersion"] = max(1, output_api_version)
            meta = merged.get("compatibility") if isinstance(merged.get("compatibility"), dict) else {}
            meta.update(compatibility_metadata())
            if self._compatibility_report.get("mode") == "forward-compatible":
                meta["sourceApiVersion"] = int(self._compatibility_report.get("incomingApiVersion", 1))
            migrations = self._compatibility_report.get("migrations") or []
            if migrations:
                meta["migrations"] = list(migrations)
            merged["compatibility"] = meta
            return merged

    def compatibility_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                **dict(self._compatibility_report),
                "documentType": "org.upp.show-state",
                "currentApiVersion": 1,
                "unknownFieldsPreserved": True,
            }

    def persistence_snapshot(self) -> dict[str, Any]:
        """Full recoverable state for disk checkpoints, not routine control traffic."""
        return self.snapshot(notation_detail=True, technology_detail=True)

    def replication_snapshot(self) -> dict[str, Any]:
        """Show-continuity snapshot that excludes non-critical technology catalog data."""
        snapshot = self.snapshot(notation_detail=True, technology_detail=False)
        snapshot.pop("technology", None)
        resource_revisions = snapshot.get("resourceRevisions")
        if isinstance(resource_revisions, dict):
            resource_revisions.pop("technology", None)
        return snapshot

    def technology_snapshot(self) -> dict[str, Any]:
        """Full technology registry for governance/catalog calls, not live control traffic."""
        with self._lock:
            return {
                "policy": dict(self._technology_policy),
                "ecosystemParticipants": self._technology_ecosystem_participants,
                "extensionCount": len(self._technology_extensions),
                "extensions": [dict(item) for item in self._technology_extensions],
                "resourceRevision": int(self._resource_revisions.get("technology", 1)),
            }

    def _quality_score(self) -> int:
        base = min(100.0, self._capacity + 18.0)
        if self._system_mode == "reduced":
            base = max(base, 90.0)
        elif self._system_mode == "safe":
            base = max(base, 94.0)
        elif self._system_mode == "audio":
            base = 100.0
        return int(round(clamp(base, 0.0, 100.0)))

    def transport(self, action: str, expected_revision: int | None = None, expected_resource_revision: int | None = None) -> dict[str, Any]:
        with self._lock:
            self._check_revision(expected_revision, "transport", expected_resource_revision)
            action = action.lower().strip()
            changed = False
            if action == "play":
                if not self._running:
                    self._running = True
                    self._started_at = monotonic()
                    changed = True
            elif action == "pause":
                if self._running:
                    self._elapsed = self._clock_seconds()
                    self._running = False
                    changed = True
            elif action == "stop":
                self._running = False
                self._elapsed = 0.0
                self._started_at = monotonic()
                changed = True
            elif action == "rewind":
                self._elapsed = 0.0
                self._started_at = monotonic()
                changed = True
            else:
                raise ValueError("action must be play, pause, stop, or rewind")
            if changed:
                self._touch("transport")
                self._event("transport", action.capitalize(), {"action": action})
            return self.snapshot()

    def patch_show(self, data: dict[str, Any], expected_revision: int | None = None, expected_resource_revision: int | None = None) -> dict[str, Any]:
        with self._lock:
            self._check_revision(expected_revision, "show", expected_resource_revision)
            changes: list[str] = []
            if "bpm" in data:
                self._bpm = clamp(float(data["bpm"]), 30.0, 300.0)
                changes.append(f"BPM {self._bpm:g}")
            if "key" in data:
                key = str(data["key"]).strip()
                if key:
                    self._key = key[:12]
                    changes.append(f"key {self._key}")
            if changes:
                self._touch("show")
                self._event("show", "Updated " + ", ".join(changes), {"changes": changes})
            return self.snapshot()

    def patch_system(self, data: dict[str, Any], expected_revision: int | None = None, expected_resource_revision: int | None = None) -> dict[str, Any]:
        with self._lock:
            self._check_revision(expected_revision, "system", expected_resource_revision)
            changes: list[str] = []
            if "capacity" in data:
                self._capacity = clamp(float(data["capacity"]), 0.0, 100.0)
                changes.append(f"capacity {self._capacity:g}%")
            if "mode" in data:
                mode = str(data["mode"]).lower().strip()
                if mode not in SYSTEM_MODES:
                    raise ValueError(f"mode must be one of {sorted(SYSTEM_MODES)}")
                self._system_mode = mode
                changes.append(f"mode {mode}")
            if "venue" in data:
                self._venue = str(data["venue"]).strip()[:80] or self._venue
                changes.append(f"venue {self._venue}")
            if "productionManager" in data:
                self._production_manager = str(data["productionManager"]).strip()[:80] or self._production_manager
                changes.append(f"manager {self._production_manager}")
            if changes:
                self._touch("system")
                self._event("system", "Updated " + ", ".join(changes), {"changes": changes})
            return self.snapshot()

    def patch_handoff(
        self,
        data: dict[str, Any],
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            resource_key = "handoff"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            changes: list[str] = []
            if "policy" in data:
                if not isinstance(data["policy"], dict):
                    raise ValueError("handoff policy must be an object")
                merged = {**self._handoff_policy, **data["policy"]}
                policy = normalize_policy(merged)
                if policy != self._handoff_policy:
                    self._handoff_policy = policy
                    changes.append("policy")
            if "liveInputs" in data:
                if not isinstance(data["liveInputs"], list):
                    raise ValueError("handoff liveInputs must be an array")
                merged = [dict(item) for item in self._handoff_live_inputs]
                for raw in data["liveInputs"]:
                    if not isinstance(raw, dict):
                        raise ValueError("each handoff live input must be an object")
                    try:
                        slot = int(raw.get("slot", -1))
                    except (TypeError, ValueError) as exc:
                        raise ValueError("handoff live input slot must be an integer") from exc
                    if not 0 <= slot < 4:
                        raise ValueError("handoff live input slot must be 0..3")
                    merged[slot] = {**merged[slot], **raw, "slot": slot}
                normalized = normalize_live_inputs(merged)
                if normalized != self._handoff_live_inputs:
                    self._handoff_live_inputs = normalized
                    changes.append("live-input redundancy")
            if "deterministicSources" in data:
                if not isinstance(data["deterministicSources"], list):
                    raise ValueError("handoff deterministicSources must be an array")
                normalized = normalize_deterministic_sources(data["deterministicSources"])
                if normalized != self._handoff_deterministic_sources:
                    self._handoff_deterministic_sources = normalized
                    changes.append("deterministic sources")
            if changes:
                self._touch(resource_key)
                self._event("handoff", "Updated " + ", ".join(changes), {"changes": changes})
            return self.snapshot()

    def patch_technology(
        self,
        data: dict[str, Any],
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            resource_key = "technology"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            changes: list[str] = []
            if "policy" in data:
                if not isinstance(data["policy"], dict):
                    raise ValueError("technology policy must be an object")
                policy = normalize_technology_policy({**self._technology_policy, **data["policy"]})
                if policy != self._technology_policy:
                    self._technology_policy = policy
                    changes.append("openness policy")
            if "ecosystemParticipants" in data:
                try:
                    participants = max(1, min(1_000_000, int(data["ecosystemParticipants"])))
                except (TypeError, ValueError) as exc:
                    raise ValueError("technology ecosystemParticipants must be an integer") from exc
                if participants != self._technology_ecosystem_participants:
                    self._technology_ecosystem_participants = participants
                    changes.append(f"ecosystem participants {participants}")
            if "extensions" in data:
                if not isinstance(data["extensions"], list):
                    raise ValueError("technology extensions must be an array")
                by_id = {item["id"]: dict(item) for item in self._technology_extensions}
                for raw in data["extensions"]:
                    if not isinstance(raw, dict):
                        raise ValueError("each technology extension must be an object")
                    extension_id = str(raw.get("id", "")).strip()[:160]
                    if not extension_id:
                        raise ValueError("technology extension id required")
                    existing = by_id.get(extension_id, {})
                    merged = {**existing, **raw, "id": extension_id}
                    if isinstance(existing.get("dependencies"), dict) and isinstance(raw.get("dependencies"), dict):
                        merged["dependencies"] = {**existing["dependencies"], **raw["dependencies"]}
                    by_id[extension_id] = merged
                normalized = normalize_technology_extensions(list(by_id.values()))
                if normalized != self._technology_extensions:
                    self._technology_extensions = normalized
                    changes.append("technology registry")
            if "removeExtensionIds" in data:
                raw_ids = data["removeExtensionIds"]
                if not isinstance(raw_ids, list):
                    raise ValueError("removeExtensionIds must be an array")
                remove_ids = {str(item).strip()[:160] for item in raw_ids if str(item).strip()}
                protected = [item["id"] for item in self._technology_extensions if item["id"] in remove_ids and (item.get("maturity") == "standard" or item.get("mandatoryCore"))]
                if protected:
                    raise ValueError("standard/core technology cannot be deleted; deprecate or supersede it instead: " + ", ".join(protected))
                kept = [item for item in self._technology_extensions if item["id"] not in remove_ids]
                if kept != self._technology_extensions:
                    self._technology_extensions = kept
                    changes.append("technology registry removals")
            if changes:
                self._touch(resource_key)
                self._event("technology", "Updated " + ", ".join(changes), {"changes": changes})
            return self.snapshot(technology_detail=True)

    def patch_audio(
        self,
        data: dict[str, Any],
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            resource_key = "audio"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            changes: list[str] = []
            if "outputs" in data:
                raw_outputs = data["outputs"]
                if not isinstance(raw_outputs, list):
                    raise ValueError("audio outputs must be an array")
                allowed_purposes = {"foh", "monitor", "broadcast", "record", "aux"}
                for raw in raw_outputs:
                    if not isinstance(raw, dict):
                        raise ValueError("each audio output must be an object")
                    try:
                        slot = int(raw.get("slot", -1))
                    except (TypeError, ValueError) as exc:
                        raise ValueError("audio output slot must be an integer") from exc
                    if not 0 <= slot < 4:
                        raise ValueError("audio output slot must be 0..3")
                    current = self._audio_outputs[slot]
                    device_id = str(raw.get("deviceId", current["deviceId"])).strip()[:96]
                    if device_id and any(ch.isspace() for ch in device_id):
                        raise ValueError("audio output device id must be an empty value or non-empty token")
                    purpose = str(raw.get("purpose", current["purpose"])).strip().lower()
                    if purpose not in allowed_purposes:
                        raise ValueError(f"audio output purpose must be one of {sorted(allowed_purposes)}")
                    player_id = str(raw.get("playerId", current["playerId"])).strip()[:64]
                    if player_id and player_id not in self._players:
                        raise ValueError("audio output playerId must reference an existing player or be empty")
                    graph_output = max(0, min(15, int(raw.get("graphOutput", current["graphOutput"]))))
                    master = clamp(float(raw.get("master", current["master"])), 0.0, 4.0)
                    ceiling = clamp(float(raw.get("limiterCeilingDb", current["limiterCeilingDb"])), -24.0, 0.0)
                    drift_raw = raw.get("driftCompensation", current["driftCompensation"])
                    if not isinstance(drift_raw, dict):
                        raise ValueError("audio driftCompensation must be an object")
                    drift = {
                        "enabled": bool(drift_raw.get("enabled", current["driftCompensation"]["enabled"])),
                        "maxCorrectionPpm": clamp(float(drift_raw.get("maxCorrectionPpm", current["driftCompensation"]["maxCorrectionPpm"])), 0.0, 10000.0),
                        "queueGainPpm": clamp(float(drift_raw.get("queueGainPpm", current["driftCompensation"]["queueGainPpm"])), 0.0, 10000.0),
                    }
                    updated = {
                        "slot": slot, "deviceId": device_id, "purpose": purpose, "playerId": player_id,
                        "graphOutput": graph_output, "master": master, "limiterCeilingDb": ceiling, "driftCompensation": drift,
                    }
                    if updated != current:
                        self._audio_outputs[slot] = updated
                        changes.append(f"output slot {slot}")
                self._audio_device_id = str(self._audio_outputs[0]["deviceId"] or "null-audio")
                self._audio_limiter_ceiling_db = float(self._audio_outputs[0]["limiterCeilingDb"])
            if "inputs" in data:
                raw_inputs = data["inputs"]
                if not isinstance(raw_inputs, list):
                    raise ValueError("audio inputs must be an array")
                for raw in raw_inputs:
                    if not isinstance(raw, dict):
                        raise ValueError("each audio input must be an object")
                    try:
                        slot = int(raw.get("slot", -1))
                    except (TypeError, ValueError) as exc:
                        raise ValueError("audio input slot must be an integer") from exc
                    if not 0 <= slot < 4:
                        raise ValueError("audio input slot must be 0..3")
                    current = self._audio_inputs[slot]
                    device_id = str(raw.get("deviceId", current["deviceId"])).strip()[:96]
                    if device_id and any(ch.isspace() for ch in device_id):
                        raise ValueError("audio input device id must be an empty value or non-empty token")
                    player_id = str(raw.get("playerId", current["playerId"])).strip()[:64]
                    if player_id and player_id not in self._players:
                        raise ValueError("audio input playerId must reference an existing player or be empty")
                    route_raw = raw.get("route", current["route"])
                    if not isinstance(route_raw, dict):
                        raise ValueError("audio input route must be an object")
                    output = max(0, min(15, int(route_raw.get("output", current["route"]["output"]))))
                    gain = clamp(float(route_raw.get("gain", current["route"]["gain"])), 0.0, 4.0)
                    sample_rate = clamp(float(raw.get("sampleRate", current["sampleRate"])), 8000.0, 768000.0)
                    updated = {"slot": slot, "deviceId": device_id, "playerId": player_id, "sampleRate": sample_rate, "route": {"output": output, "gain": gain}}
                    if updated != current:
                        self._audio_inputs[slot] = updated
                        changes.append(f"input slot {slot}")
                slot0 = self._audio_inputs[0]
                self._audio_input_device_id = str(slot0["deviceId"])
                self._audio_input_player_id = str(slot0["playerId"])
                self._audio_input_route_output = int(slot0["route"]["output"])
                self._audio_input_route_gain = float(slot0["route"]["gain"])
            if "deviceId" in data:
                device_id = str(data["deviceId"]).strip()[:96]
                if not device_id or any(ch.isspace() for ch in device_id):
                    raise ValueError("audio device id must be a non-empty token")
                if device_id != self._audio_device_id:
                    self._audio_device_id = device_id
                    self._audio_outputs[0]["deviceId"] = device_id
                    changes.append(f"device {device_id}")
            if "inputDeviceId" in data:
                input_device_id = str(data["inputDeviceId"]).strip()[:96]
                if input_device_id and any(ch.isspace() for ch in input_device_id):
                    raise ValueError("audio input device id must be an empty value or non-empty token")
                if input_device_id != self._audio_input_device_id:
                    self._audio_input_device_id = input_device_id
                    self._audio_inputs[0]["deviceId"] = input_device_id
                    changes.append(f"input device {input_device_id or 'none'}")
            if "inputPlayerId" in data:
                player_id = str(data["inputPlayerId"]).strip()[:64]
                if player_id and player_id not in self._players:
                    raise ValueError("audio inputPlayerId must reference an existing player or be empty")
                if player_id != self._audio_input_player_id:
                    self._audio_input_player_id = player_id
                    self._audio_inputs[0]["playerId"] = player_id
                    changes.append(f"input player {player_id or 'unassigned'}")
            if "inputRoute" in data:
                route = data["inputRoute"]
                if not isinstance(route, dict):
                    raise ValueError("audio inputRoute must be an object")
                output = max(0, min(15, int(route.get("output", self._audio_input_route_output))))
                gain = clamp(float(route.get("gain", self._audio_input_route_gain)), 0.0, 4.0)
                if output != self._audio_input_route_output or gain != self._audio_input_route_gain:
                    self._audio_input_route_output = output
                    self._audio_input_route_gain = gain
                    self._audio_inputs[0]["route"] = {"output": output, "gain": gain}
                    changes.append(f"input route source 24 -> output {output} gain {gain:g}")
            if "sampleRate" in data:
                sample_rate = clamp(float(data["sampleRate"]), 8000.0, 768000.0)
                if sample_rate != self._audio_sample_rate:
                    previous_sample_rate = self._audio_sample_rate
                    self._audio_sample_rate = sample_rate
                    if "inputs" not in data:
                        for audio_input in self._audio_inputs:
                            if float(audio_input["sampleRate"]) == previous_sample_rate:
                                audio_input["sampleRate"] = sample_rate
                    changes.append(f"sample rate {sample_rate:g}")
            if "bufferFrames" in data:
                buffer_frames = max(16, min(8192, int(data["bufferFrames"])))
                if buffer_frames != self._audio_buffer_frames:
                    self._audio_buffer_frames = buffer_frames
                    changes.append(f"buffer {buffer_frames}")
            if "limiterCeilingDb" in data:
                ceiling = clamp(float(data["limiterCeilingDb"]), -24.0, 0.0)
                if ceiling != self._audio_limiter_ceiling_db:
                    self._audio_limiter_ceiling_db = ceiling
                    self._audio_outputs[0]["limiterCeilingDb"] = ceiling
                    changes.append(f"limiter {ceiling:g} dBFS")
            if changes:
                self._touch(resource_key)
                self._event("audio", "Audio desired state updated: " + ", ".join(changes), {"changes": changes})
            return self.snapshot()

    def patch_lighting_network(
        self,
        data: dict[str, Any],
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            resource_key = "lighting-network"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            changes: list[str] = []
            if "protocol" in data:
                protocol = str(data["protocol"]).strip().lower()
                if protocol not in {"artnet", "sacn"}:
                    raise ValueError("lighting protocol must be artnet or sacn")
                if protocol != self._lighting_protocol:
                    previous_default_port = 5568 if self._lighting_protocol == "sacn" else 6454
                    self._lighting_protocol = protocol
                    changes.append("protocol")
                    if "port" not in data and self._lighting_port == previous_default_port:
                        self._lighting_port = 5568 if protocol == "sacn" else 6454
                        changes.append("port")
            if "target" in data:
                target = str(data["target"]).strip()[:64]
                if target:
                    try:
                        address = IPv4Address(target)
                    except ValueError as exc:
                        raise ValueError("lighting target must be an IPv4 address") from exc
                    if address.is_multicast or address.is_unspecified or int(address) == 0xFFFFFFFF:
                        raise ValueError("lighting target must be unicast IPv4")
                if target != self._lighting_target:
                    self._lighting_target = target
                    changes.append("target")
            if "port" in data:
                try:
                    port = int(data["port"])
                except (TypeError, ValueError) as exc:
                    raise ValueError("lighting port must be an integer") from exc
                if not 1 <= port <= 65535:
                    raise ValueError("lighting port must be 1..65535")
                if port != self._lighting_port:
                    self._lighting_port = port
                    changes.append("port")
            if "universeBase" in data:
                try:
                    universe_base = int(data["universeBase"])
                except (TypeError, ValueError) as exc:
                    raise ValueError("lighting universeBase must be an integer") from exc
                if not 1 <= universe_base <= 63984:
                    raise ValueError("lighting universeBase must be 1..63984")
                if universe_base != self._lighting_universe_base:
                    self._lighting_universe_base = universe_base
                    changes.append("universeBase")
            if changes:
                self._touch(resource_key)
                self._event("lighting", "Lighting network desired state updated: " + ", ".join(changes), {"changes": changes})
            return self.snapshot()

    def patch_monitor(self, player_id: str, data: dict[str, Any], expected_revision: int | None = None, expected_resource_revision: int | None = None) -> dict[str, Any]:
        with self._lock:
            resource_key = f"monitor:{player_id}"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            player = self._players.get(player_id)
            if player is None:
                raise KeyError(player_id)
            player.monitor.patch(data)
            self._touch(resource_key)
            self._event(
                "monitor",
                f"{player.name} personal monitor updated; FOH unchanged",
                {"playerId": player_id, "fields": sorted(set(data) & (set(MONITOR_KEYS) | {"muted", "output"}))},
            )
            return self.snapshot()
    def bind_midi_device(
        self,
        device_id: str,
        player_id: str,
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            resource_key = "midi-bindings"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            device_id = str(device_id).strip()[:96]
            if not device_id or any(ch.isspace() for ch in device_id):
                raise ValueError("MIDI device id must be a non-empty token")
            player = self._players.get(player_id)
            if player is None:
                raise KeyError(player_id)
            if self._midi_bindings.get(device_id) == player_id:
                return self.snapshot()
            self._midi_bindings[device_id] = player_id
            self._touch(resource_key)
            self._event("midi", f"MIDI device {device_id} bound to {player.name}", {"deviceId": device_id, "playerId": player_id})
            return self.snapshot()

    def unbind_midi_device(
        self,
        device_id: str,
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            resource_key = "midi-bindings"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            device_id = str(device_id).strip()[:96]
            previous = self._midi_bindings.pop(device_id, None)
            if previous is None:
                return self.snapshot()
            self._touch(resource_key)
            self._event("midi", f"MIDI device {device_id} unbound", {"deviceId": device_id, "playerId": previous})
            return self.snapshot()

    def notation_snapshot(self, player_id: str) -> dict[str, Any]:
        with self._lock:
            player = self._players.get(player_id)
            if player is None:
                raise KeyError(player_id)
            return self._notation.part_snapshot(player_id, self._key)

    def patch_notation_settings(
        self,
        player_id: str,
        data: dict[str, Any],
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            resource_key = f"notation:{player_id}"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            player = self._players.get(player_id)
            if player is None:
                raise KeyError(player_id)
            self._notation.patch_settings(player_id, data)
            self._touch(resource_key)
            self._event(
                "notation",
                f"{player.name} notation settings updated; performance capture preserved",
                {"playerId": player_id, "settings": self._notation.part_snapshot(player_id, self._key)["settings"]},
            )
            return self.snapshot()

    def notation_note(
        self,
        player_id: str,
        data: dict[str, Any],
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            resource_key = f"notation:{player_id}"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            player = self._players.get(player_id)
            if player is None:
                raise KeyError(player_id)
            part = self._notation.part_snapshot(player_id, self._key)
            if not part["settings"]["enabled"]:
                return self.snapshot()
            action = str(data.get("action", "")).strip().lower()
            if "pitch" not in data:
                raise ValueError("pitch is required")
            pitch = int(data.get("pitch"))
            velocity = int(data.get("velocity", 100))
            seconds_value = data.get("showTimeSeconds")
            seconds = self._clock_seconds() if seconds_value is None else max(0.0, float(seconds_value))
            self._notation.note(player_id, action, pitch, velocity, seconds, self._bpm)
            self._touch(resource_key)
            self._event(
                "notation",
                f"{player.name} note {action} captured for auto notation",
                {"playerId": player_id, "action": action, "pitch": pitch, "velocity": velocity},
            )
            return self.snapshot()

    def clear_notation(
        self,
        player_id: str,
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            resource_key = f"notation:{player_id}"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            player = self._players.get(player_id)
            if player is None:
                raise KeyError(player_id)
            self._notation.clear(player_id)
            self._touch(resource_key)
            self._event("notation", f"{player.name} notation capture cleared", {"playerId": player_id})
            return self.snapshot()

    def ingest_midi(
        self,
        player_id: str,
        data: dict[str, Any],
        expected_revision: int | None = None,
        expected_resource_revision: int | None = None,
    ) -> dict[str, Any]:
        """Ingest a timestamped player MIDI message and fan it out to observers.

        MIDI activity is authoritative performance/control input. Auto notation
        observes note messages but cannot block or transform this path. The
        bounded MIDI activity journal is for live diagnostics; a future native
        recording service can consume the same event stream for durable takes.
        """
        with self._lock:
            resource_key = f"midi:{player_id}"
            self._check_revision(expected_revision, resource_key, expected_resource_revision)
            player = self._players.get(player_id)
            if player is None:
                raise KeyError(player_id)
            try:
                status = int(data["status"])
                data1 = int(data["data1"])
                data2 = int(data.get("data2", 0))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("MIDI input requires integer status, data1 and optional data2") from exc
            if not (0 <= status <= 255 and 0 <= data1 <= 127 and 0 <= data2 <= 127):
                raise ValueError("MIDI bytes out of range")
            seconds_value = data.get("showTimeSeconds")
            seconds = self._clock_seconds() if seconds_value is None else max(0.0, float(seconds_value))
            device_id = str(data.get("deviceId", "direct")).strip()[:96] or "direct"
            message = status & 0xF0
            action: str | None = None
            if message == 0x90 and data2 > 0:
                action = "on"
            elif message == 0x80 or (message == 0x90 and data2 == 0):
                action = "off"

            notation_observed = False
            if action is not None:
                part = self._notation.part_snapshot(player_id, self._key)
                if part["settings"]["enabled"]:
                    self._notation.note(player_id, action, data1, max(1, data2) if action == "on" else 0, seconds, self._bpm)
                    notation_observed = True

            self._midi_received += 1
            activity = {
                "playerId": player_id,
                "deviceId": device_id,
                "showTimeSeconds": round(seconds, 6),
                "status": status,
                "channel": (status & 0x0F) + 1 if status < 0xF0 else None,
                "data1": data1,
                "data2": data2,
                "notationObserved": notation_observed,
            }
            self._midi_activity.append(activity)
            del self._midi_activity[:-512]
            touched = [resource_key]
            if notation_observed:
                touched.append(f"notation:{player_id}")
            self._touch_resources(*touched)
            self._event(
                "midi",
                f"{player.name} MIDI input received" + (f"; auto notation observed note {action}" if notation_observed else ""),
                activity,
            )
            return self.snapshot()

    def notation_musicxml(self, player_id: str) -> str:
        with self._lock:
            player = self._players.get(player_id)
            if player is None:
                raise KeyError(player_id)
            return self._notation.musicxml(player_id, f"{player.name} - {player.role}", self._bpm, self._key)
