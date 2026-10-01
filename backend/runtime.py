from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from functools import wraps
import os
from ipaddress import IPv4Address
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic, monotonic_ns, time_ns
from typing import Any, Callable

from adapters import AdapterRegistry
from native_engine import NativeEngineClient
from persistence import StateRepository
from state import ShowState
from replication import ReplicationTracker, verify_envelope
from cluster_secrets import RotatingHmacKeyring
from peer_replication import ReplicationPushClient
from witness import WitnessQuorumClient
from witness_topology import load_witness_topology
from timing import timing_plan as local_timing_plan
from handoff import HandoffExecutionRegistry, HandoffFacts, evaluate_handoff
from technology import (
    evaluate_technology_extension,
    evaluate_technology_registry,
    negotiate_technology_capabilities,
    technology_evidence_digest,
)
from admin_mail import AdminMailer
from community_governance import CommunityGovernance
from community_auth import CommunitySessionManager
from compatibility import compatibility_report, inspect_show_state, migrate_show_state, resolve_requirements, show_requirements_from_snapshot, LEGACY_API_ALIASES, SCHEMA_MIGRATIONS, SHOW_STATE_API_VERSION, SHOW_STATE_SCHEMA_VERSION, SHOW_STATE_DOCUMENT_TYPE
from venue import VenueProfileStore, inspect_venue_profile, normalize_venue_profile, venue_compatibility_plan, resolve_lighting_fixture_intent
from adaptation import VenueAdaptationManager, VENUE_PATCH_LAYER_SCHEMA_VERSION
from reconciliation import RealizationEvidenceRegistry, evaluate_realization
from authority_leases import AuthorityLeaseRegistry
from planned_handoff import make_offer,make_ready_receipt,verify_offer,verify_ready_receipt
from user_profiles import UserProfileStore, inspect_user_profile, resolve_user_preferences, DOCUMENT_TYPE as USER_PROFILE_DOCUMENT_TYPE, SCHEMA_VERSION as USER_PROFILE_SCHEMA_VERSION
from interoperability_sessions import CapabilityRegistry, InteroperabilitySessionManager, make_authenticated_offer, project_profile
from security_store import SecurityStateStore
from public_record import PublicRecordStore
from hardware_qualification import probe_platform
from hardware_diagnostics import diagnose_hardware
from audio_preflight import audio_preflight
from audio_conversion import audio_conversion_plan
from audio_identity import AudioIdentityStore, describe_audio_device
from midi_identity import MidiIdentityStore, describe_midi_device
from daw_session import DawSessionStore, render_plan
from daw_media import inspect_wav, resolve_media_path
from daw_production import AutosaveStore, MediaLibrary, OfflineRenderer, PluginCatalog, TakeManager, beat_to_frame, tempo_map
from daw_runtime import playback_prefetch_plan
from daw_playback import ArrangementProducer
from daw_capture import CaptureDrainer
from plugin_latency import latency_compensation_plan
from plugin_host import plugin_host_audit_status,plugin_host_scratch_cleanup,plugin_host_scratch_status
from midi_mapping import MidiMappingEngine
from sampler_preload import SamplerPreloadRegistry
from stage_launcher import launcher_projection
from streaming_bank import StreamingSampleBanks
from streaming_voice_producer import PolyphonicStreamingProducer
from media_snapshot import MediaSnapshot
from staged_resources import StagedResourceRegistry
from overload_policy import overload_shedding_plan
from stage_templates import StageTemplateStore

CANONICAL_SAMPLE_RATE = 192000
MAX_API_FRAME = (1 << 53) - 1


def _audio_controlled(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._audio_control_lock:
            return method(self, *args, **kwargs)
    return guarded


def _api_frame(data: dict[str, Any], key: str, default: int | None = None) -> int:
    value = data.get(key, default)
    if type(value) is not int:
        raise ValueError(f"{key} must be a JSON integer")
    if value < 0 or value > MAX_API_FRAME:
        raise ValueError(f"{key} must be between 0 and {MAX_API_FRAME}")
    return value


def _physical_audio_execution(value: object) -> bool:
    return str(value or "").strip().lower() not in {"", "none", "null", "null-audio", "bridge-only"}


class StageForgeRuntime:
    """Composition root for state, persistence, adapters and command dedupe.

    The native engine is an execution follower during this development phase.
    A lightweight background pump drains native MIDI input into the same
    authoritative show state used by HTTP/SSE control clients.
    """

    def __init__(self, data_dir: Path) -> None:
        self.repository = StateRepository(data_dir)
        self.state = ShowState(self.repository.load_snapshot())
        self.admin_mailer = AdminMailer(data_dir)
        self.venue_profiles = VenueProfileStore(data_dir / "venue-profile.json")
        self.user_profiles = UserProfileStore(data_dir / "user-profile.json")
        self.daw_sessions = DawSessionStore(data_dir / "daw-session.json")
        self.daw_media_root = data_dir / "media"
        self.daw_media_root.mkdir(parents=True, exist_ok=True)
        self._launcher_feedback={"sequence":0,"action":"","source":"","accepted":False}
        self._launcher_action_ids:OrderedDict[str,None]=OrderedDict()
        self.daw_import_root = data_dir / "imports"; self.daw_import_root.mkdir(parents=True, exist_ok=True)
        self.daw_exports_root = data_dir / "exports"; self.daw_exports_root.mkdir(parents=True, exist_ok=True)
        self.daw_media = MediaLibrary(self.daw_media_root)
        self.daw_renderer = OfflineRenderer(self.daw_media_root)
        self.daw_takes = TakeManager(self.daw_media_root)
        self.daw_plugins = PluginCatalog(data_dir / "plugin-manifests")
        self.daw_autosaves = AutosaveStore(data_dir / "autosaves")
        self.midi_mapping = MidiMappingEngine(data_dir / "midi-mappings.json")
        self.midi_identities = MidiIdentityStore(data_dir / "midi-identities.json")
        self.audio_identities = AudioIdentityStore(data_dir / "audio-identities.json")
        self._native_midi_mapping_ids: set[str] = set()
        self.venue_adaptations = VenueAdaptationManager(data_dir / "venue-adaptations.json")
        self.venue_realization = RealizationEvidenceRegistry()
        self.venue_authority_leases = AuthorityLeaseRegistry()
        self.stage_templates = StageTemplateStore(data_dir / "stage-templates.json")
        node_id = os.environ.get("STAGEFORGE_NODE_ID", "node-local")
        node_role = os.environ.get("STAGEFORGE_NODE_ROLE", "primary")
        self.replication = ReplicationTracker(node_id, node_role)
        self.interop_capabilities = CapabilityRegistry()
        self.interop_sessions = InteroperabilitySessionManager(node_id)
        self.security_store = SecurityStateStore(data_dir / "security-state.json")
        self.public_record = PublicRecordStore(
            data_dir / "public-record.jsonl", signer_id=node_id, signing_secret=self.security_store.root_key,
            witness_policy_path=os.environ.get("STAGEFORGE_PUBLIC_RECORD_WITNESS_FILE", ""),
        )
        self.community = CommunityGovernance(
            data_dir,
            self.admin_mailer,
            public_record_append=self.public_record.append,
        )
        try:
            community_session_ttl = int(os.environ.get("STAGEFORGE_COMMUNITY_SESSION_TTL_SECONDS", "900"))
        except ValueError:
            community_session_ttl = 900
        self.community_sessions = CommunitySessionManager(
            self.security_store.root_key, ttl_seconds=community_session_ttl
        )
        configured_interop_secret = os.environ.get("STAGEFORGE_INTEROP_SECRET", "").encode("utf-8")
        self._interop_secret = configured_interop_secret or self.security_store.root_key
        self._interop_sequence = 0
        raw_replication_secret = os.environ.get("STAGEFORGE_REPLICATION_SECRET", "")
        self._replication_secret = raw_replication_secret.encode("utf-8") if raw_replication_secret else None
        self._replication_keyring = RotatingHmacKeyring(
            os.environ.get("STAGEFORGE_REPLICATION_KEYRING_FILE", ""), self._replication_secret
        )
        self.adapters = AdapterRegistry()
        self.native = NativeEngineClient()
        self.sampler_preloads = SamplerPreloadRegistry(self.native, self.daw_media_root)
        self.daw_producer = ArrangementProducer(self.native, self.daw_media_root)
        self.streaming_voice_producer=PolyphonicStreamingProducer(self.native,self.daw_media_root)
        self.streaming_banks = StreamingSampleBanks(self.daw_media_root,self.streaming_voice_producer)
        self.daw_capture = CaptureDrainer(self.native, self.daw_media_root)
        self._dedupe_lock = RLock()
        self._mutation_lock = RLock()
        self._venue_adaptation_lock = RLock()
        self._command_results: OrderedDict[str, dict[str, Any]] = OrderedDict()
        latest = self.state.latest_event()
        self._last_persisted_event_id = int(latest.get("eventId", 0)) if latest else 0
        self._stop = Event()
        self._midi_thread: Thread | None = None
        self._audio_thread: Thread | None = None
        self._lighting_thread: Thread | None = None
        self._replication_thread: Thread | None = None
        self._witness_thread: Thread | None = None
        self._adaptation_thread: Thread | None = None
        self._reconciliation_thread: Thread | None = None
        self._last_reconciliation_state: tuple[Any, ...] | None = None
        self._next_lighting_event_id = 1
        self._last_midi_scan = 0.0
        self._midi_devices: list[dict[str, Any]] = []
        self._midi_scan_lock = RLock()
        self._midi_hotplug_generation = 0
        self._midi_hotplug_changes: list[dict[str, Any]] = []
        self._audio_devices: list[dict[str, Any]] = []
        self._audio_control_lock = RLock()
        self._audio_scan_lock = RLock()
        self._audio_hotplug_generation = 0
        self._audio_hotplug_changes: list[dict[str, Any]] = []
        self._last_audio_scan = 0.0
        self._audio_activation_preflight: dict[tuple[str, int], dict[str, Any]] = {}
        self._lighting_armed = False
        self._replicated_execution_telemetry: dict[str, Any] = {}
        self.handoff_execution = HandoffExecutionRegistry()
        self._planned_handoff: dict[str, Any] | None = None
        self._last_failover_continuity: dict[str, Any] = {
            "measured": False,
            "timelineErrorMs": None,
            "grade": "unmeasured",
            "replicaAgeMs": None,
            "firstAudioArmAfterMs": None,
            "firstAudioWriteAfterMs": None,
            "maxObservedOutputGapMs": None,
            "audioResumptionGrade": "not-rearmed",
            "activeAudioOutputSlots": [],
            "firstLightingArmAfterMs": None,
            "sourceLastProgramShowNs": None,
            "newFirstProgramShowNs": None,
            "crossNodeProgramGapMs": None,
            "crossNodeProgramOverlapMs": None,
            "crossNodeProgramGrade": "unmeasured",
            "handoffMode": "state-warm",
            "deterministicPrebufferEligible": False,
            "prebufferReady": False,
            "handoffTargetShowNs": None,
            "handoffAdjustmentMs": 0.0,
            "physicalOutputsAutoArmed": False,
        }
        self._promotion_at: float | None = None
        self._promotion_at_ns: int | None = None
        peer_url = os.environ.get("STAGEFORGE_PEER_URL", "").strip()
        try:
            peer_timeout = float(os.environ.get("STAGEFORGE_PEER_TIMEOUT_SECONDS", "0.75"))
        except ValueError:
            peer_timeout = 0.75
        self._peer = ReplicationPushClient(peer_url, timeout_seconds=peer_timeout)
        witness_topology_path = os.environ.get("STAGEFORGE_WITNESS_TOPOLOGY_FILE", "").strip()
        independent_topology = load_witness_topology(witness_topology_path) if witness_topology_path else None
        witness_urls = ([item["url"] for item in independent_topology["witnesses"]] if independent_topology else
                        [item.strip() for item in os.environ.get("STAGEFORGE_WITNESS_URLS", "").split(",") if item.strip()])
        raw_witness_secret = "" if independent_topology else os.environ.get("STAGEFORGE_WITNESS_SECRET", raw_replication_secret)
        witness_secret = raw_witness_secret.encode("utf-8") if raw_witness_secret else b""
        witness_keyring_path = "" if independent_topology else os.environ.get(
            "STAGEFORGE_WITNESS_KEYRING_FILE", os.environ.get("STAGEFORGE_REPLICATION_KEYRING_FILE", "")
        )
        witness_keyring = None if independent_topology else RotatingHmacKeyring(witness_keyring_path, witness_secret)
        cluster_id = os.environ.get("STAGEFORGE_CLUSTER_ID", "stageforge-local")
        try:
            witness_ttl_ms = int(os.environ.get("STAGEFORGE_WITNESS_TTL_MS", "3000"))
            witness_timeout = float(os.environ.get("STAGEFORGE_WITNESS_TIMEOUT_SECONDS", "0.5"))
        except ValueError:
            witness_ttl_ms, witness_timeout = 3000, 0.5
        self._witness = WitnessQuorumClient(
            witness_urls, cluster_id, node_id, witness_secret, ttl_ms=witness_ttl_ms, timeout_seconds=witness_timeout,
            fence_path=data_dir / "handoff-acquisition-fence.json", keyring=witness_keyring,
            independent_topology=independent_topology
        )
        if self._witness.status().get("acquisitionSuspended"):
            self.replication.set_role("standby")
        self._auto_failover = os.environ.get("STAGEFORGE_AUTO_FAILOVER", "0").strip().lower() in {"1", "true", "yes", "on"}
        try:
            self._replication_interval = max(0.1, float(os.environ.get("STAGEFORGE_REPLICATION_INTERVAL_SECONDS", "0.5")))
            self._replication_heartbeat = max(self._replication_interval, float(os.environ.get("STAGEFORGE_REPLICATION_HEARTBEAT_SECONDS", "2.0")))
            self._failover_suspect_ms = max(100, int(os.environ.get("STAGEFORGE_FAILOVER_SUSPECT_MS", "2500")))
            self._failover_promote_ms = max(self._failover_suspect_ms + 100, int(os.environ.get("STAGEFORGE_FAILOVER_PROMOTE_MS", "5000")))
        except ValueError:
            self._replication_interval, self._replication_heartbeat = 0.5, 2.0
            self._failover_suspect_ms, self._failover_promote_ms = 2500, 5000

        initial = self.state.snapshot()
        self.repository.save_snapshot(self.state.persistence_snapshot())
        try:
            self.native.sync_state(initial)
            self._persist_core_journal()
            if self.native.available:
                self._sync_native_midi_mappings()
                self._refresh_audio_devices(reselect=True)
                self._configure_lighting_from_state()
                self._refresh_midi_devices(rebind=True)
                self._midi_thread = Thread(target=self._midi_loop, name="stageforge-midi-input", daemon=True)
                self._midi_thread.start()
                self._audio_thread = Thread(target=self._audio_hotplug_loop, name="stageforge-audio-hotplug", daemon=True)
                self._audio_thread.start()
                self._lighting_thread = Thread(target=self._lighting_loop, name="stageforge-lighting-dispatch", daemon=True)
                self._lighting_thread.start()
        except RuntimeError:
            pass
        if self._peer.configured:
            self._replication_thread = Thread(target=self._replication_loop, name="stageforge-replication", daemon=True)
            self._replication_thread.start()
        if self._witness.configured:
            self._witness_thread = Thread(target=self._witness_loop, name="stageforge-witness-lease", daemon=True)
            self._witness_thread.start()
        self._adaptation_thread = Thread(target=self._adaptation_loop, name="stageforge-venue-adaptation", daemon=True)
        self._adaptation_thread.start()
        self._reconciliation_thread = Thread(target=self._reconciliation_loop, name="stageforge-venue-reconciliation", daemon=True)
        self._reconciliation_thread.start()

    def _has_authority(self) -> bool:
        return (self.replication.is_primary() and
                not self._witness.status().get("acquisitionSuspended", False) and
                (not self._witness.configured or self._witness.valid()))

    def _fence_physical_outputs(self) -> None:
        if self.native.available:
            try:
                self.native.arm_lighting_network(False)
            except RuntimeError:
                pass
            with self._audio_control_lock:
                try:
                    self.native.deactivate_all_audio_inputs()
                except RuntimeError:
                    pass
                try:
                    self.native.deactivate_all_audio_outputs()
                except RuntimeError:
                    pass
            for device in self._midi_devices:
                if device.get("attached") and device.get("id"):
                    try:
                        self.native.detach_midi_input(str(device["id"]))
                    except RuntimeError:
                        pass
        self._lighting_armed = False
        # Operational authority leases are ephemeral authority state. Any
        # physical-output fence means this node must reacquire scoped ownership
        # after authority is safely established again.
        if hasattr(self, "venue_authority_leases"):
            self.venue_authority_leases.clear()
            self._last_reconciliation_state = None

    def _persist_new_events(self) -> None:
        events = self.state.events_since(self._last_persisted_event_id)
        for event in events:
            self.repository.append_event(event)
            self._last_persisted_event_id = max(self._last_persisted_event_id, int(event.get("eventId", 0)))

    def _persist_core_journal(self, limit: int = 512) -> int:
        """Drain deterministic native execution records into the durable ledger.

        Core never performs filesystem I/O. The bridge/persistence service is the
        journal sink and can later be replaced without changing the native record
        contract. Native hashes are retained as provenance inside the repository's
        independent SHA-256 hash chain.
        """
        if not self.native.available:
            return 0
        persisted = 0
        for _ in range(max(0, int(limit))):
            try:
                raw = self.native.next_journal_record()
            except RuntimeError:
                break
            if raw.get("available") != "1":
                break
            event = {
                "type": "native-core",
                "sequence": int(raw.get("sequence", "0")),
                "kind": int(raw.get("kind", "0")),
                "showNs": int(raw.get("showNs", "0")),
                "eventId": int(raw.get("eventId", "0")),
                "subjectId": int(raw.get("subjectId", "0")),
                "revision": int(raw.get("revision", "0")),
                "nativePreviousHash": int(raw.get("previousHash", "0")),
                "nativeHash": int(raw.get("hash", "0")),
            }
            self.repository.append_event(event)
            persisted += 1
        return persisted

    def _after_mutation(self, result: dict[str, Any], *, sync_native: bool = True) -> dict[str, Any]:
        self._persist_new_events()
        self.repository.save_snapshot(self.state.persistence_snapshot())
        if sync_native:
            try:
                self.native.sync_state(result)
                self._persist_core_journal()
            except RuntimeError:
                pass
        return result

    def mutate(self, command_id: str | None, operation: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], bool]:
        if not self._has_authority():
            if not self.replication.is_primary():
                raise RuntimeError("standby node is read-only; apply replicated state or promote authority first")
            raise RuntimeError("primary node lacks witness quorum lease")
        if command_id:
            command_id = command_id.strip()[:128]
        with self._dedupe_lock:
            if command_id and command_id in self._command_results:
                cached = self._command_results[command_id]
                self._command_results.move_to_end(command_id)
                return cached, True

        # Serialize state mutation -> persistence -> native execution sync so
        # revisions cannot reach the native follower out of order when several
        # control points write concurrently.
        with self._mutation_lock:
            before_revision = self.state.revision
            result = operation()
            if result["revision"] != before_revision:
                result = self._after_mutation(result)

            if command_id:
                with self._dedupe_lock:
                    self._command_results[command_id] = result
                    self._command_results.move_to_end(command_id)
                    while len(self._command_results) > 256:
                        self._command_results.popitem(last=False)
            return result, False

    def _active_venue_mapping(self, logical_key: str) -> dict[str, Any] | None:
        active = self.venue_adaptations.snapshot().get("active")
        if isinstance(active, dict):
            try:
                minimum = max(1, int(active.get("minimumReaderSchemaVersion", 1)))
            except (TypeError, ValueError):
                return None
            if minimum > VENUE_PATCH_LAYER_SCHEMA_VERSION:
                return None
        mappings = (active or {}).get("mappings") if isinstance(active, dict) else None
        value = (mappings or {}).get(str(logical_key)) if isinstance(mappings, dict) else None
        return dict(value) if isinstance(value, dict) else None

    def _mapped_execution_device(self, logical_key: str) -> str | None:
        mapping = self._active_venue_mapping(logical_key)
        if not mapping:
            return None
        patch = mapping.get("patch") if isinstance(mapping.get("patch"), dict) else {}
        execution = patch.get("execution") if isinstance(patch.get("execution"), dict) else {}
        explicit = str(execution.get("deviceId", "")).strip()
        if explicit:
            return explicit[:160]
        provider = mapping.get("provider") if isinstance(mapping.get("provider"), dict) else {}
        discovered = str(provider.get("discoveredId", "")).strip()
        return discovered[:160] if discovered else None

    def _mapped_lighting_execution(self) -> dict[str, Any] | None:
        mapping = self._active_venue_mapping("lighting.primary")
        if not mapping:
            return None
        patch = mapping.get("patch") if isinstance(mapping.get("patch"), dict) else {}
        execution = patch.get("execution") if isinstance(patch.get("execution"), dict) else {}
        target = str(execution.get("target", "")).strip()
        if not target:
            return None
        protocol = str(execution.get("protocol", "artnet")).strip().lower() or "artnet"
        if protocol in {"artnet", "sacn"}:
            try:
                address = IPv4Address(target)
            except ValueError:
                return None
            if address.is_multicast or address.is_unspecified or int(address) == 0xFFFFFFFF:
                return None
        else:
            return None
        try:
            port = int(execution.get("port", 5568 if protocol == "sacn" else 6454))
        except (TypeError, ValueError):
            port = 5568 if protocol == "sacn" else 6454
        try:
            universe_base = int(execution.get("universeBase", 1))
        except (TypeError, ValueError):
            universe_base = 1
        return {
            "target": target[:64],
            "port": max(1, min(port, 65535)),
            "protocol": protocol,
            "universeBase": max(1, min(universe_base, 63984)),
            "fixtures": deepcopy(execution.get("fixtures")) if isinstance(execution.get("fixtures"), dict) else {},
            "source": "venue-patch-layer",
        }

    def _audio_output_configs(self, audio_state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        audio = audio_state or (self.state.snapshot().get("audio") or {})
        outputs = audio.get("outputs")
        defaults = [
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
        if isinstance(outputs, list):
            for item in outputs:
                if not isinstance(item, dict):
                    continue
                try:
                    slot = int(item.get("slot", -1))
                except (TypeError, ValueError):
                    continue
                if 0 <= slot < 4:
                    defaults[slot].update(item)
        else:
            defaults[0].update({"deviceId": audio.get("deviceId", "null-audio"), "limiterCeilingDb": audio.get("limiterCeilingDb", -1.0)})
        return defaults

    def _audio_input_configs(self, audio_state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        audio = audio_state or (self.state.snapshot().get("audio") or {})
        inputs = audio.get("inputs")
        if isinstance(inputs, list):
            configs = [dict(item) for item in inputs if isinstance(item, dict) and 0 <= int(item.get("slot", -1)) < 4]
            by_slot = {int(item["slot"]): item for item in configs}
            return [by_slot.get(slot, {"slot": slot, "deviceId": "", "playerId": "", "sampleRate": audio.get("sampleRate", 192000.0), "route": {"output": 0, "gain": 0.0}}) for slot in range(4)]
        return [{"slot": 0, "deviceId": audio.get("inputDeviceId", ""), "playerId": audio.get("inputPlayerId", ""), "sampleRate": audio.get("sampleRate", 192000.0), "route": audio.get("inputRoute") or {"output": 0, "gain": 0.0}}] + [
            {"slot": slot, "deviceId": "", "playerId": "", "sampleRate": audio.get("sampleRate", 192000.0), "route": {"output": 0, "gain": 0.0}} for slot in range(1, 4)
        ]

    @_audio_controlled
    def _refresh_audio_devices(self, *, reselect: bool = False) -> list[dict[str, Any]]:
        if not self.native.available:
            with self._audio_scan_lock:self._audio_devices = []
            return []
        devices = self.native.scan_audio_devices()
        for device in devices:
            device.update(describe_audio_device(device));device["identityRecorded"]=self.audio_identities.expected(str(device.get("id",""))) is not None
        previous_by_id={str(item.get("id","")):item for item in self._audio_devices}
        current_by_id={str(item.get("id","")):item for item in devices}
        previous_ids={str(item.get("id","")) for item in self._audio_devices}
        current_ids={str(item.get("id","")) for item in devices}
        disconnected=previous_ids-current_ids
        prior_identity={device_id:(previous_by_id.get(device_id) or self.audio_identities.expected(device_id) or {}).get("persistentId") for device_id in current_ids}
        identity_changed={device_id for device_id in current_ids if prior_identity.get(device_id) and current_by_id[device_id].get("persistentId") and prior_identity[device_id]!=current_by_id[device_id].get("persistentId") and (device_id not in previous_by_id or previous_by_id[device_id].get("persistentId")!=current_by_id[device_id].get("persistentId"))}
        unsafe_ids=disconnected|identity_changed
        stopped_outputs=[];stopped_inputs=[]
        for slot in range(4):
            try:
                status=self.native.audio_stream_status(slot)
                if status.get("selected") in unsafe_ids and _physical_audio_execution(status.get("execution")) and status.get("state")=="2":
                    self.native.deactivate_audio(slot);stopped_outputs.append(slot)
            except (RuntimeError,ValueError):pass
            try:
                status=self.native.audio_input_status(slot)
                if status.get("selected") in unsafe_ids and _physical_audio_execution(status.get("execution")) and status.get("state")=="2":
                    self.native.deactivate_audio_input(slot);stopped_inputs.append(slot)
            except (RuntimeError,ValueError):pass
        audio_state = self.state.snapshot().get("audio") or {}
        output_configs = self._audio_output_configs(audio_state)
        input_configs = self._audio_input_configs(audio_state)
        def resolved(device_id, direction):
            return self.audio_identities.resolve(device_id,devices,direction)
        if reselect:
            for config in output_configs:
                device_id = str(config.get("deviceId", ""))
                device=resolved(device_id,"output")
                if device:
                    try:
                        self.native.select_audio_device(str(device["id"]), int(config.get("slot", 0)))
                    except (RuntimeError, ValueError):
                        pass
            for config in input_configs:
                device_id = str(config.get("deviceId", ""))
                device=resolved(device_id,"input")
                if device:
                    try:
                        self.native.select_audio_input(str(device["id"]), int(config.get("slot", 0)))
                    except (RuntimeError, ValueError):
                        pass
        for device in devices:
            device_id = str(device.get("id", ""))
            output_slots = [int(config["slot"]) for config in output_configs if resolved(str(config.get("deviceId","")),"output") is device]
            device["desired"] = 0 in output_slots
            device["desiredOutput"] = bool(output_slots)
            device["desiredOutputSlots"] = output_slots
            device["desiredInput"] = any(resolved(str(config.get("deviceId","")),"input") is device for config in input_configs if config.get("deviceId"))
            device["desiredInputSlots"] = [int(config["slot"]) for config in input_configs if resolved(str(config.get("deviceId","")),"input") is device]
            reconnects=[str(config.get("deviceId","")) for config in output_configs+input_configs if str(config.get("deviceId",""))!=device_id and self.audio_identities.reconnect_match(str(config.get("deviceId","")),devices) is device]
            device["reconnectsDeviceIds"]=list(dict.fromkeys(reconnects));device["reconnectStatus"]="serial-match" if reconnects else ("eligible" if device.get("automaticReconnectEligible") else "explicit-recovery-required")
        with self._audio_scan_lock:
            changes=[{"kind":"connected","deviceId":value} for value in sorted(current_ids-previous_ids)]+[{"kind":"disconnected","deviceId":value,"stoppedOutputSlots":stopped_outputs,"stoppedInputSlots":stopped_inputs} for value in sorted(disconnected)]+[{"kind":"identity-changed","deviceId":value,"previousPersistentId":prior_identity[value],"currentPersistentId":current_by_id[value]["persistentId"],"stoppedOutputSlots":stopped_outputs,"stoppedInputSlots":stopped_inputs} for value in sorted(identity_changed)]
            if changes:
                self._audio_hotplug_generation+=1
                for change in changes:change.update({"generation":self._audio_hotplug_generation,"observedMonotonicNs":monotonic_ns()})
                self._audio_hotplug_changes=(self._audio_hotplug_changes+changes)[-128:]
            self._audio_devices=devices;self._last_audio_scan=monotonic()
        for device in devices:self.audio_identities.record(str(device.get("id","")),device)
        return [dict(device) for device in devices]

    @_audio_controlled
    def replace_audio_identity(self,data:dict[str,Any])->dict[str,Any]:
        if data.get("acknowledgeIdentityReplacement") is not True:
            raise ValueError("audio identity replacement requires acknowledgeIdentityReplacement=true")
        desired_id=str(data.get("desiredDeviceId","")).strip();current_id=str(data.get("currentDeviceId","")).strip();direction=str(data.get("direction","")).strip()
        if not desired_id or not current_id:raise ValueError("desiredDeviceId and currentDeviceId are required")
        if direction not in {"output","input"}:raise ValueError("direction must be output or input")
        self._refresh_audio_devices(reselect=False)
        current=next((item for item in self._audio_devices if str(item.get("id",""))==current_id and item.get("connected") and item.get(direction)),None)
        if current is None:raise ValueError(f"current audio {direction} endpoint is not connected")
        status_reader=self.native.audio_stream_status if direction=="output" else self.native.audio_input_status
        for slot in range(4):
            try:
                status=status_reader(slot)
            except (RuntimeError,ValueError):continue
            if status.get("execution")!="none" and str(status.get("state","0"))=="2":
                raise ValueError(f"stop all active audio {direction} streams before replacing endpoint identity")
        previous,replacement=self.audio_identities.replace(desired_id,current)
        self._refresh_audio_devices(reselect=True)
        selected=self._find_audio_device(desired_id,direction)
        return {"documentType":"org.upp.audio-identity-replacement","schemaVersion":1,"desiredDeviceId":desired_id,"currentDeviceId":current_id,"direction":direction,"previousPersistentId":previous.get("persistentId"),"currentPersistentId":replacement.get("persistentId"),"identityStrength":replacement.get("identityStrength"),"automaticReconnectEligible":replacement.get("automaticReconnectEligible") is True,"selected":selected is not None and str(selected.get("id"))==current_id,"streamsStarted":False,"physicalOutputsArmed":False}

    def _find_audio_device(self, desired: str, direction: str) -> dict[str, Any] | None:
        return self.audio_identities.resolve(desired,self._audio_devices,direction)

    def _audio_hotplug_loop(self) -> None:
        while not self._stop.wait(2.0):
            if not self.native.available:continue
            try:self._refresh_audio_devices(reselect=True)
            except (RuntimeError,ValueError,OSError):continue

    def audio_hotplug_status(self, after: int = 0) -> dict[str, Any]:
        with self._audio_scan_lock:
            return {"generation":self._audio_hotplug_generation,"changes":[dict(item) for item in self._audio_hotplug_changes if int(item["generation"])>int(after)],"scanIntervalMs":2000,"automaticActivation":False,"physicalOutputsArmed":False}

    def audio_devices(self, *, rescan: bool = False) -> dict[str, Any]:
        if rescan or not self._audio_devices:
            try:
                self._refresh_audio_devices(reselect=True)
            except RuntimeError:
                self._audio_devices = []
        audio = self.state.snapshot().get("audio") or {}
        output_configs = self._audio_output_configs(audio)
        input_configs = self._audio_input_configs(audio)
        output_statuses = [self.audio_stream_status(slot) for slot in range(4)]
        input_statuses = [self.audio_input_status(slot) for slot in range(4)]
        slot0 = input_statuses[0]
        out0 = output_statuses[0]
        return {
            "available": self.native.available,
            "devices": [dict(device) for device in self._audio_devices],
            "hotplug": self.audio_hotplug_status(),
            "desiredDeviceId": output_configs[0].get("deviceId", "null-audio"),
            "desiredConnected": bool(out0.get("desiredConnected")),
            "desiredInputDeviceId": slot0.get("desiredDeviceId", ""),
            "desiredInputConnected": bool(slot0.get("desiredConnected")),
            "executionBackend": out0.get("executionBackend", "bridge-only"),
            "executionState": out0.get("state", 0),
            "callbacks": out0.get("callbacks", 0),
            "xruns": out0.get("xruns", 0),
            "executionOutput": out0.get("output", 0),
            "inputExecutionBackend": slot0.get("executionBackend", "none"),
            "inputExecutionState": 2 if slot0.get("active") else 0,
            "inputCallbacks": slot0.get("callbacks", 0),
            "inputXruns": slot0.get("xruns", 0),
            "inputSource": slot0.get("source", 24),
            "inputQueuedFrames": slot0.get("queuedFrames", 0),
            "inputDroppedFrames": slot0.get("droppedFrames", 0),
            "inputUnderrunFrames": slot0.get("underrunFrames", 0),
            "inputRoute": slot0.get("route", {}),
            "outputs": output_statuses,
            "inputs": input_statuses,
            "sampleRate": audio.get("sampleRate", 192000.0),
            "engineSampleRate": 192000.0,
            "engineSampleFormat": "float32",
            "bufferFrames": audio.get("bufferFrames", 256),
            "limiterCeilingDb": audio.get("limiterCeilingDb", -1.0),
        }


    def compatibility_local_profile(self) -> dict[str, Any]:
        capabilities: set[str] = set()
        for adapter in self.adapters.snapshot():
            for capability in adapter.get("capabilities") or []:
                capabilities.add(str(capability))
        capabilities.update({"profile.customization", "compatibility.handshake"})
        return {
            "id": self.replication.status().get("nodeId", "node-local"),
            "apiVersions": [SHOW_STATE_API_VERSION],
            "schemaVersions": {SHOW_STATE_DOCUMENT_TYPE: [SHOW_STATE_SCHEMA_VERSION], USER_PROFILE_DOCUMENT_TYPE: [USER_PROFILE_SCHEMA_VERSION]},
            "capabilities": sorted(capabilities),
            "requiredCapabilities": ["audio.transport", "authority.fence"],
            "adapters": [],
            "preservesUnknown": True,
            "offlineCapable": True,
            "legacyApiAliases": [dict(item) for item in LEGACY_API_ALIASES],
            "schemaMigrations": [dict(item) for item in SCHEMA_MIGRATIONS],
            "showState": self.state.compatibility_status(),
        }

    def compatibility_with(self, data: dict[str, Any]) -> dict[str, Any]:
        remote = data.get("remote") if isinstance(data.get("remote"), dict) else data
        local = data.get("local") if isinstance(data.get("local"), dict) else self.compatibility_local_profile()
        return compatibility_report(local, remote)

    def user_profile(self) -> dict[str, Any]:
        return self.user_profiles.load()

    def user_profile_resolved(self) -> dict[str, Any]:
        return resolve_user_preferences(self.user_profiles.load())

    def user_profile_inspect(self, data: dict[str, Any]) -> dict[str, Any]:
        profile = data.get("profile") if isinstance(data.get("profile"), dict) else data
        return inspect_user_profile(profile)

    def save_user_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        profile = data.get("profile") if isinstance(data.get("profile"), dict) else data
        saved = self.user_profiles.save(profile)
        if self.native.available:
            try:
                profile_id = self.native._stable_id(f"profile:{saved['profileId']}")
                epoch = max(1, int(self.replication.status().get("epoch", 0)))
                self.native.configure_user_profile(profile_id, epoch)
                type_ids = {"boolean": 0, "integer": 1, "scalar": 2, "token": 3}
                layer_ids = {"base": 0, "user": 1, "role": 2, "venue": 3, "session": 4}
                for item in saved["preferences"]:
                    value = item["value"]
                    if item["type"] == "token": value = self.native._stable_id(f"profile-token:{value}")
                    self.native.set_user_preference(
                        self.native._stable_id(f"profile-namespace:{item['namespace']}"),
                        self.native._stable_id(f"profile-key:{item['key']}"), layer_ids[item["layer"]],
                        int(item["revision"]), type_ids[item["type"]], value,
                    )
            except (RuntimeError, ValueError):
                pass
        return {**saved, "resolved": resolve_user_preferences(saved)["resolved"], "physicalOutputsArmed": False}

    def user_profile_projection(self) -> dict[str, Any]:
        return project_profile(self.user_profiles.load())

    def interoperability_registry(self) -> dict[str, Any]:
        return self.interop_capabilities.snapshot()

    def security_status(self) -> dict[str, Any]:
        return self.security_store.status()

    def daw_session(self) -> dict[str, Any]:
        return self.daw_sessions.load()

    def save_daw_session(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.daw_sessions.save(data)

    def daw_render_plan(self, data: dict[str, Any]) -> dict[str, Any]:
        return render_plan(self.daw_sessions.load(), int(data.get("startFrame", 0)), int(data.get("endFrame", 192000 * 60)))

    def daw_inspect_media(self, data: dict[str, Any]) -> dict[str, Any]:
        uri=str(data.get("path", ""));relative=uri[6:] if uri.startswith("media/") else uri
        return inspect_wav(resolve_media_path(self.daw_media_root, relative), peak_buckets=int(data.get("peakBuckets", 512)))

    def daw_edit(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.daw_sessions.edit(data)

    def daw_marker_edit(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.daw_sessions.marker_edit(data)

    def daw_automation_edit(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.daw_sessions.automation_edit(data)

    def daw_undo(self) -> dict[str, Any]:
        return self.daw_sessions.undo()

    def daw_redo(self) -> dict[str, Any]:
        return self.daw_sessions.redo()

    def daw_ingest_media(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.daw_media.ingest(resolve_media_path(self.daw_import_root, str(data.get("path", ""))))

    def daw_verify_media(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.daw_media.verify(str(data.get("path", "")), str(data.get("contentHash", "")))

    def daw_tempo_status(self) -> dict[str, Any]:
        session=self.daw_sessions.load();points=tempo_map(session.get("tempoMap") or [])
        return {"tempoMap":points,"sampleRate":192000,"physicalOutputsArmed":False}

    def daw_beat_frame(self, data: dict[str, Any]) -> dict[str, Any]:
        points=tempo_map(self.daw_sessions.load().get("tempoMap") or [])
        return {"beat":float(data.get("beat",0)),"frame":beat_to_frame(points,float(data.get("beat",0))),"sampleRate":192000,"physicalOutputsArmed":False}

    def daw_prepare_take(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.daw_takes.prepare(str(data.get("trackId","")),int(data.get("startFrame",0)),pre_roll_frames=int(data.get("preRollFrames",0)),punch_out_frame=data.get("punchOutFrame"))

    def daw_finalize_take(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.daw_takes.finalize(dict(data.get("plan") or {}),str(data.get("path","")),list(data.get("dropouts") or []))

    def daw_render(self, data: dict[str, Any]) -> dict[str, Any]:
        name=Path(str(data.get("fileName","mix.wav"))).name
        if not name.lower().endswith(".wav"):raise ValueError("render output must be WAV")
        session=self.daw_sessions.load();receipt=self.daw_renderer.render(session,self.daw_exports_root/name,int(data.get("startFrame",0)),int(data.get("endFrame",192000*10)),bits=int(data.get("bits",24)),seed=int(data.get("ditherSeed",0)))
        self.daw_autosaves.save(session);return receipt

    def daw_plugin_catalog(self) -> dict[str, Any]:
        return self.daw_plugins.scan()

    def daw_autosave(self) -> dict[str, Any]:
        return self.daw_autosaves.save(self.daw_sessions.load())

    def daw_playback_prefetch(self, data: dict[str, Any]) -> dict[str, Any]:
        return playback_prefetch_plan(self.daw_sessions.load(),int(data.get("playheadFrame",0)),lookahead_frames=int(data.get("lookaheadFrames",384000)))

    def daw_sampler_status(self) -> dict[str, Any]:
        status=self.sampler_preloads.status()
        if self.native.available:
            try:status["engine"]={**self.native.sampler_status(),"physicalOutputsArmed":False}
            except RuntimeError:pass
        return status

    def stage_launcher_status(self) -> dict[str,Any]:
        midi=self.midi_mapping_status().get("nativeExecution") or {}
        feedback={**self._launcher_feedback,"nativeMidiSubmitted":int(midi.get("submitted",0)),"nativeMidiRejected":int(midi.get("rejected",0))}
        return launcher_projection(self.state.snapshot(),self.daw_sampler_status(),self.daw_capture_status(),feedback)

    def stage_launcher_action(self,data:dict[str,Any])->dict[str,Any]:
        action=str(data.get("action","")).strip();source=str(data.get("source","touch"))[:16];action_id=str(data.get("actionId","")).strip()[:128]
        if source not in {"touch","keyboard","midi"}:raise ValueError("unsupported launcher input source")
        with self._dedupe_lock:
            if action_id and action_id in self._launcher_action_ids:
                self._launcher_action_ids.move_to_end(action_id);result=self.stage_launcher_status();result["feedback"]={**result["feedback"],"deduplicated":True};return result
        if action=="transport.toggle":
            running=bool((self.state.snapshot().get("transport") or {}).get("running",False));self.mutate(action_id,lambda:self.state.transport("pause" if running else "play"))
        elif action=="transport.stop":self.mutate(action_id,lambda:self.state.transport("stop"))
        elif action=="sample.trigger":
            if not self.replication.is_primary():raise RuntimeError("standby node cannot trigger stage samples")
            resource=str(data.get("resourceId","")).strip();asset=self.sampler_preloads.resolve(resource,False)
            if not asset:raise ValueError("launcher sample is not preloaded")
            show_ns=int(float((self.state.snapshot().get("transport") or {}).get("seconds",0))*1_000_000_000)
            self.native.sampler_trigger(time_ns(),show_ns,str(asset["nativeResourceId"]),velocity=max(0.0,min(1.0,float(data.get("velocity",1.0)))),note=max(0,min(127,int(data.get("note",60)))))
        else:raise ValueError("unsupported launcher action")
        if action_id:
            with self._dedupe_lock:
                self._launcher_action_ids[action_id]=None
                while len(self._launcher_action_ids)>256:self._launcher_action_ids.popitem(last=False)
        self._launcher_feedback={"sequence":int(self._launcher_feedback.get("sequence",0))+1,"action":action,"source":source,"resourceId":str(data.get("resourceId",""))[:128],"accepted":True,"atMonotonicNs":monotonic_ns()}
        return self.stage_launcher_status()

    def daw_sampler_preload(self, data: dict[str, Any]) -> dict[str, Any]:
        result=self.sampler_preloads.preload(self.daw_sessions.load(),str(data.get("clipId","")),looped=bool(data.get("looped",False)),
            choke_group=int(data.get("chokeGroup",0)),crossfade_frames=int(data.get("crossfadeFrames",256)))
        self._sync_native_midi_mappings()
        return result

    def streaming_bank_status(self)->dict[str,Any]:
        result=self.streaming_banks.status();voice={"available":bool(self.native.available),"activeVoices":0,"activeMask":0,"queuedBlocks":0,"starts":0,"stops":0,"renderedFrames":0,"starvedBlocks":0,"staleBlocks":0,"discontinuities":0,"completedVoices":0,"overflows":0,"diskIoInAudioCallback":False,"physicalOutputsArmed":False}
        if self.native.available:
            raw=self.native.streaming_voice_status()
            for key in ("activeVoices","activeMask","queuedBlocks","starts","stops","renderedFrames","starvedBlocks","staleBlocks","discontinuities","completedVoices","overflows"):voice[key]=int(raw.get(key,0))
        result["voiceEngine"]=voice;return result
    def streaming_bank_replace(self,data:dict[str,Any])->dict[str,Any]:return self.streaming_banks.replace(self.daw_sessions.load(),str(data.get("bankId","")),list(data.get("entries") or []))
    def streaming_bank_trigger(self,data:dict[str,Any])->dict[str,Any]:
        if not self.replication.is_primary():raise RuntimeError("standby node cannot trigger streaming bank")
        return self.streaming_banks.trigger(self.daw_sessions.load(),str(data.get("bankId","")),int(data.get("slot",-1)),str(data.get("actionId","")))
    def streaming_voice_stop(self,data:dict[str,Any])->dict[str,Any]:
        if not self.replication.is_primary():raise RuntimeError("standby node cannot stop streaming voice")
        return self.streaming_voice_producer.stop(int(data.get("voiceSlot",-1)),int(data.get("generation",0)))

    def daw_playback_status(self) -> dict[str, Any]:
        if not self.native.available:return {"available":False,"physicalOutputsArmed":False}
        return {"available":True,**self.native.daw_playback_status(),"producer":self.daw_producer.status(),"physicalOutputsArmed":False}

    def daw_production_status(self) -> dict[str, Any]:
        """One coherent, read-only projection for the DAW production controls."""
        return {
            "canonicalSampleRate": CANONICAL_SAMPLE_RATE,
            "playback": self.daw_playback_status(),
            "capture": self.daw_capture_status(),
            "recovery": self.daw_recovery_status(),
            "temporaryResources": self.daw_temporary_resource_status(),
            "physicalOutputsArmed": False,
        }

    def daw_temporary_resource_status(self)->dict[str,Any]:
        snapshots=MediaSnapshot.status(self.daw_media_root);staging=self._daw_staged_resources().status();plugins=plugin_host_scratch_status()
        return {"documentType":"org.upp.daw-temporary-resource-status","schemaVersion":3,"resourceClass":"aggregate","resourceCount":snapshots["resourceCount"]+staging["resourceCount"]+plugins["resourceCount"],"liveCount":snapshots["liveCount"]+staging["liveCount"]+plugins["liveCount"],"reclaimableCount":snapshots["reclaimableCount"]+staging["reclaimableCount"]+plugins["reclaimableCount"],"unknownOwnerCount":snapshots["unknownOwnerCount"]+staging["unknownOwnerCount"]+plugins["unknownOwnerCount"],"observedBytes":snapshots["observedBytes"]+staging["observedBytes"]+plugins["observedBytes"],"scanTruncated":snapshots["scanTruncated"] or staging["scanTruncated"] or plugins["scanTruncated"],"snapshots":snapshots,"staging":staging,"pluginScratch":plugins,"physicalOutputsArmed":False}

    def _daw_staged_resources(self)->StagedResourceRegistry:
        return StagedResourceRegistry([("media-import",self.daw_media.objects,".media-*"),("render-output",self.daw_exports_root,".render-*.wav")])

    def daw_temporary_resource_cleanup(self,data:dict[str,Any])->dict[str,Any]:
        if data.get("acknowledgeCleanup") is not True:raise ValueError("temporary-resource cleanup requires acknowledgeCleanup=true")
        snapshot_cleanup=MediaSnapshot.reclaim(self.daw_media_root);staging_cleanup=self._daw_staged_resources().reclaim();plugin_cleanup=plugin_host_scratch_cleanup();status=self.daw_temporary_resource_status()
        return {**status,"reclaimedCount":snapshot_cleanup["reclaimedCount"]+staging_cleanup["reclaimedCount"]+plugin_cleanup["reclaimedCount"],"reclaimedResourceIds":snapshot_cleanup["reclaimedResourceIds"]+staging_cleanup["reclaimedResourceIds"]+plugin_cleanup["reclaimedResourceIds"]}

    def plugin_host_lifecycle_status(self)->dict[str,Any]:
        hosts=plugin_host_audit_status()
        return {"documentType":"org.upp.plugin-host-lifecycle","schemaVersion":1,"hosts":hosts[:128],"hostCount":len(hosts),"hostsTruncated":len(hosts)>128,"scratch":plugin_host_scratch_status(),"automaticRestart":False,"physicalOutputsArmed":False}

    def daw_playback_control(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self.native.available:raise RuntimeError("native engine unavailable")
        action=str(data.get("action",""))
        if action=="start":result=self.daw_producer.start(self.daw_sessions.load(),_api_frame(data,"startFrame",0),_api_frame(data,"endFrame",CANONICAL_SAMPLE_RATE*60))
        elif action=="stop":self.daw_producer.stop();result={"running":False}
        elif action=="seek":result=self.native.daw_playback_seek(_api_frame(data,"frame",0))
        elif action=="loop":result=self.daw_producer.start(self.daw_sessions.load(),_api_frame(data,"beginFrame",0),_api_frame(data,"endFrame",0),loop=True)
        else:raise ValueError("unsupported playback action")
        return {**result,"physicalOutputsArmed":False}

    def daw_capture_status(self) -> dict[str, Any]:
        return {"available":self.native.available,**self.daw_capture.status(),"physicalOutputsArmed":False}

    def daw_recovery_status(self) -> dict[str, Any]:
        return self.daw_capture.recovery_candidates()

    def daw_capture_control(self, data: dict[str, Any]) -> dict[str, Any]:
        action=str(data.get("action",""))
        if action=="recover":return self.daw_capture.recover(str(data.get("fileName","")))
        if not self.native.available:raise RuntimeError("native engine unavailable")
        if action=="start":
            if data.get("acknowledgePhysicalInput") is not True:raise PermissionError("capture start requires explicit physical-input acknowledgement")
            result=self.daw_capture.start(int(data.get("track",0)),str(data.get("takeId",f"take-{time_ns()}")),str(data.get("fileName","capture.wav")),
                punchInFrame=int(data.get("punchInFrame",0)),punchOutFrame=int(data["punchOutFrame"]) if data.get("punchOutFrame") is not None else None,
                preRollFrames=int(data.get("preRollFrames",0)),latencyCompensationFrames=int(data.get("latencyCompensationFrames",0)),
                loopStartFrame=int(data["loopStartFrame"]) if data.get("loopStartFrame") is not None else None,
                loopEndFrame=int(data["loopEndFrame"]) if data.get("loopEndFrame") is not None else None,maximumPasses=int(data.get("maximumPasses",1)))
        elif action=="finish":result=self.daw_capture.finish(data.get("fileName"))
        elif action=="abort":self.daw_capture.abort();result=self.daw_capture.status()
        else:raise ValueError("unsupported capture action")
        return {**result,"physicalOutputsArmed":False}

    def daw_plugin_delay_plan(self, data: dict[str, Any]) -> dict[str, Any]:
        return latency_compensation_plan(list(data.get("paths") or []))

    def plugin_delay_graph_status(self)->dict[str,Any]:
        result={"available":bool(self.native.available),"executionMode":"native-output-slot-post-effect","transactionConnected":False,"audioGraphConnected":False,"liveAlignmentVerified":False,"physicalOutputsArmed":False}
        if not self.native.available:return result
        raw=self.native.plugin_delay_graph_status()
        for key in ("activeGeneration","preparedGeneration","activationShowNs","paths","changes","maximumLatencyFrames","swaps","rollbacks","rejected","processedFrames"):
            result[key]=int(raw.get(key,0))
        result["prepared"]=raw.get("prepared")=="1";result["transactionConnected"]=raw.get("transactionConnected")=="1";result["audioGraphConnected"]=raw.get("audioGraphConnected")=="1";result["pathBinding"]=raw.get("pathBinding","unknown");result["liveAlignmentVerified"]=result["transactionConnected"] and result["audioGraphConnected"] and result["activeGeneration"]>0 and result["processedFrames"]>0
        return result
    def plugin_delay_graph_control(self,data:dict[str,Any])->dict[str,Any]:
        # This is a control-thread prototype, not an audio-thread publication API.
        # Serialize prepare/activate and require the same authority as show writes.
        with self._mutation_lock:
            if not self._has_authority():raise RuntimeError("delay graph control requires primary authority and witness lease")
            return self._plugin_delay_graph_control_locked(data)

    def _plugin_delay_graph_control_locked(self,data:dict[str,Any])->dict[str,Any]:
        if not self.native.available:raise RuntimeError("native engine unavailable")
        action=str(data.get("action",""));paths=list(data.get("paths") or [])
        if action in {"prepare","prepareTransaction"}:
            if len(paths)>4:raise ValueError("live delay graph supports at most four output slots")
            plan=latency_compensation_plan(paths);status=self.native.plugin_delay_graph_status();generation=int(status.get("activeGeneration",0))+1
            if int(status.get("preparedGeneration",0)):raise RuntimeError("a delay graph generation is already pending activation")
            boundary=data.get("activationShowNs",0)
            if isinstance(boundary,bool) or not isinstance(boundary,int) or not 0<=boundary<2**64:raise ValueError("invalid activation Show-Time boundary")
            specified=["outputSlot" in path for path in plan["paths"]]
            if any(specified) and not all(specified):raise ValueError("either every live delay path declares outputSlot or none do")
            ordered=plan["paths"]
            if all(specified):
                ordered=sorted(ordered,key=lambda path:path["outputSlot"])
                if [path["outputSlot"] for path in ordered]!=list(range(len(ordered))):raise ValueError("live delay output slots must be contiguous from zero")
            latencies=[int(p["latencyFrames"]) for p in ordered]
            if action=="prepare":self.native.plugin_delay_graph_prepare(generation,boundary,latencies)
            else:
                raw_changes=list(data.get("changes") or [])
                if len(raw_changes)>64:raise ValueError("effect/delay transaction supports at most 64 changes")
                changes=[];seen=set()
                for raw in raw_changes:
                    effect_id=raw.get("effectId");slot=raw.get("outputSlot");bypassed=raw.get("bypassed")
                    if isinstance(effect_id,bool) or not isinstance(effect_id,int) or effect_id<1:raise ValueError("effectId must be a positive integer")
                    if isinstance(slot,bool) or not isinstance(slot,int) or not 0<=slot<4:raise ValueError("outputSlot must be from zero through three")
                    if not isinstance(bypassed,bool):raise ValueError("bypassed must be boolean")
                    if raw.get("safetyClass")!="optional" or raw.get("bypassMode")!="latency-preserving":raise ValueError("transaction changes require optional latency-preserving classification")
                    if (slot,effect_id) in seen:raise ValueError("duplicate effect transaction target")
                    seen.add((slot,effect_id));changes.append({"outputSlot":slot,"effectId":effect_id,"bypassed":bypassed})
                self.native.effect_delay_transaction_prepare(generation,boundary,latencies,changes)
        elif action=="rollback":
            status=self.native.plugin_delay_graph_status();generation=int(status.get("activeGeneration",0))+1
            if int(status.get("preparedGeneration",0)):raise RuntimeError("an effect/delay generation is already pending activation")
            boundary=data.get("activationShowNs",0)
            if isinstance(boundary,bool) or not isinstance(boundary,int) or not 0<=boundary<2**64:raise ValueError("invalid activation Show-Time boundary")
            self.native.effect_delay_transaction_rollback(generation,boundary)
        elif action=="activate":
            # Client-supplied showNs cannot advance the platform's clock.
            show_ns=max(0,int(float(self.state.snapshot()["transport"]["seconds"])*1_000_000_000))
            self.native.plugin_delay_graph_activate(show_ns)
        else:raise ValueError("unsupported delay graph action")
        return self.plugin_delay_graph_status()
    def realtime_audit_status(self)->dict[str,Any]:
        if not self.native.available:return {"available":False,"outputs":[],"ingress":{"pluginHosts":plugin_host_audit_status()},"physicalOutputsArmed":False}
        return {"available":True,"outputs":[self.native.realtime_audit_status(slot) for slot in range(4)],"ingress":{"midi":self.native.ingress_audit_status("MIDI"),"capture":[self.native.capture_ingress_audit_status(slot) for slot in range(4)],"lighting":self.native.lighting_ingress_audit_status(),"pluginHosts":plugin_host_audit_status()},"policy":{"shedOptionalEffectsAfterMisses":3,"criticalAfterMisses":10,"recoverAfterOnTimeCallbacks":128,"automaticEffectSheddingEnabled":False,"overloadAdvisoryOnly":True},"physicalOutputsArmed":False}

    def overload_shedding_plan(self,data:dict[str,Any])->dict[str,Any]:
        outputs=data.get("outputs")
        if outputs is None:
            if not self.native.available:raise RuntimeError("native realtime audit unavailable")
            outputs=[]
            for slot in range(4):
                raw=self.native.realtime_audit_status(slot);outputs.append({"overloadLevel":int(raw.get("overloadLevel",0))})
        if not isinstance(outputs,list) or len(outputs)>4:raise ValueError("outputs must contain at most four audit records")
        return overload_shedding_plan(outputs,list(data.get("effects") or []),list(data.get("policyBypassedEffectIds") or []))

    def overload_transaction_prepare(self,data:dict[str,Any])->dict[str,Any]:
        if data.get("acknowledgeReviewedPlan") is not True:raise ValueError("overload transaction requires acknowledgeReviewedPlan=true")
        with self._mutation_lock:
            if not self._has_authority():raise RuntimeError("overload transaction requires primary authority and witness lease")
            plan=self.overload_shedding_plan(data)
            action=plan["action"];target_ids=plan["recommendedBypassEffectIds"] if action=="shed" else plan["recommendedRestoreEffectIds"]
            reviewed=data.get("reviewedEffectIds")
            if data.get("reviewedAction")!=action or not isinstance(reviewed,list) or reviewed!=target_ids:raise RuntimeError("reviewed overload plan no longer matches current deterministic plan")
            if action=="hold" or not target_ids:raise RuntimeError("current overload plan has no effect transaction to prepare")
            effects=list(data.get("effects") or []);by_id={effect.get("effectId"):effect for effect in effects if isinstance(effect,dict)};changes=[]
            for effect_id in target_ids:
                effect=by_id[effect_id];active=effect.get("latencyFrames");bypass=effect.get("bypassLatencyFrames")
                if isinstance(active,bool) or not isinstance(active,int) or not 0<=active<=65536:raise ValueError("latencyFrames must be an integer from zero through 65536")
                if isinstance(bypass,bool) or not isinstance(bypass,int) or bypass!=active:raise ValueError("latency-preserving bypass must retain the exact active latency")
                changes.append({"effectId":effect_id,"outputSlot":effect["outputSlot"],"bypassed":action=="shed","safetyClass":"optional","bypassMode":"latency-preserving"})
            status=self._plugin_delay_graph_control_locked({"action":"prepareTransaction","activationShowNs":data.get("activationShowNs",0),"paths":list(data.get("paths") or []),"changes":changes})
            return {"documentType":"org.upp.audio.overload-transaction-preparation","schemaVersion":1,"reviewedPlan":plan,"preparedAction":action,"preparedEffectIds":target_ids,"operatorConfirmed":True,"activationRequired":True,"transactionStatus":status,"physicalOutputsArmed":False}

    def hardware_qualification(self) -> dict[str, Any]:
        return probe_platform()

    def hardware_diagnostics(self) -> dict[str, Any]:
        return diagnose_hardware()

    def audio_hardware_preflight(self, data: dict[str, Any]) -> dict[str, Any]:
        return audio_preflight(data)

    def audio_conversion_plan(self, data: dict[str, Any]) -> dict[str, Any]:
        return audio_conversion_plan(dict(data.get("device") or {}), data.get("conversionPolicy"), direction=str(data.get("direction", "playback")))

    def register_interoperability_capability(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.interop_capabilities.register(data.get("capability") if isinstance(data.get("capability"), dict) else data)

    def register_interoperability_adapter(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.interop_capabilities.register_adapter(data.get("adapter") if isinstance(data.get("adapter"), dict) else data)

    def interoperability_offer(self, data: dict[str, Any]) -> dict[str, Any]:
        self._interop_sequence += 1
        epoch = int(self.replication.status().get("epoch", 1))
        return make_authenticated_offer(self.compatibility_local_profile(), str(data.get("targetParticipantId", "")),
                                        authority_epoch=epoch, sequence=self._interop_sequence, ttl_ms=int(data.get("ttlMs", 30_000)), secret=self._interop_secret)

    def interoperability_accept(self, data: dict[str, Any]) -> dict[str, Any]:
        offer = data.get("offer") if isinstance(data.get("offer"), dict) else data
        now_ms = time_ns() // 1_000_000; epoch = int(self.replication.status().get("epoch", 1)); profile = self.user_profiles.load()
        session = self.interop_sessions.authenticate_and_negotiate(offer, self.compatibility_local_profile(), self.interop_capabilities,
                                                                    secret=self._interop_secret, now_unix_ms=now_ms,
                                                                    profile_revision=int(profile["revision"]), authority_epoch=epoch)
        if self.native.available and session["state"] == "negotiated":
            try:
                session_id=int(session["sessionId"][:16],16) or 1; transcript=int(session["transcriptSha256"][:16],16) or 1
                nonce=int(str(offer["nonce"])[:16],16) or 1
                self.native.interop_session_offer(session_id,transcript,nonce,epoch,int(offer["sequence"]),int(offer["expiresAtUnixMs"]))
                self.native.interop_session_authenticate(True,now_ms,epoch,int(offer["sequence"])-1)
                plan=session["plan"]
                self.native.interop_session_negotiate(True,int(plan["selectedApiVersion"]),USER_PROFILE_SCHEMA_VERSION,int(profile["revision"]),int(self.interop_capabilities.snapshot()["revision"]))
            except (RuntimeError,ValueError,KeyError): pass
        return session

    def interoperability_consent(self, data: dict[str, Any]) -> dict[str, Any]:
        projection=self.user_profile_projection();session=self.interop_sessions.consent(str(data.get("sessionId","")),projection,accepted=bool(data.get("accepted")))
        if self.native.available and session["state"]=="consented":
            try:self.native.interop_session_consent(True,int(projection["projectionDigestSha256"][:16],16) or 1)
            except (RuntimeError,ValueError):pass
        return session

    def interoperability_activate(self, data: dict[str, Any]) -> dict[str, Any]:
        now_ms=time_ns()//1_000_000;epoch=int(self.replication.status().get("epoch",1));profile=self.user_profiles.load();registry=self.interop_capabilities.snapshot()
        session=self.interop_sessions.activate(str(data.get("sessionId","")),now_unix_ms=now_ms,profile_revision=int(profile["revision"]),registry_revision=int(registry["revision"]),authority_epoch=epoch)
        if self.native.available and session["state"]=="active":
            try:self.native.interop_session_activate(now_ms,epoch,int(profile["revision"]),int(registry["revision"]))
            except RuntimeError:pass
        return session

    def interoperability_session_status(self, session_id: str) -> dict[str, Any]:
        return self.interop_sessions.status(session_id,now_unix_ms=time_ns()//1_000_000)

    def show_compatibility_requirements(self) -> list[dict[str, Any]]:
        return show_requirements_from_snapshot(self.state.snapshot())

    def show_compatibility(self, data: dict[str, Any]) -> dict[str, Any]:
        remote = data.get("remote") if isinstance(data.get("remote"), dict) else data
        base = self.compatibility_with({"remote": remote})
        execution = resolve_requirements(remote, self.show_compatibility_requirements())
        blockers = list(base.get("blockers") or [])
        blockers.extend(
            f"show requirement blocked: {item['id']}"
            for item in execution.get("requirements", [])
            if item.get("status") == "blocked"
        )
        compatible = bool(base.get("compatible")) and bool(execution.get("compatible"))
        grade = "blocked" if not compatible else execution.get("grade", base.get("grade", "direct"))
        return {
            "compatible": compatible,
            "grade": grade,
            "protocol": base,
            "showExecution": execution,
            "blockers": blockers,
        }

    def venue_profile(self) -> dict[str, Any]:
        return self.venue_profiles.load()

    def save_venue_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        profile = data.get("venue") if isinstance(data.get("venue"), dict) else data
        return self.venue_profiles.save(profile)

    def venue_compatibility(self, data: dict[str, Any]) -> dict[str, Any]:
        venue = data.get("venue") if isinstance(data.get("venue"), dict) else self.venue_profiles.load()
        discovered = data.get("discoveredDevices")
        if discovered is None and bool(data.get("useLocalDiscovery", False)):
            # Local discovery is an explicit show-day evidence mode. Pre-arrival
            # planning otherwise trusts the venue profile's expected-state data.
            discovered = []
            for device in self.audio_devices().get("devices", []):
                if isinstance(device, dict):
                    discovered.append({**device, "kind": "audio", "status": "online", "capabilities": ["audio.output.multi", "audio.input.capture"]})
            for device in self.midi_devices().get("devices", []):
                if isinstance(device, dict):
                    discovered.append({**device, "kind": "midi", "status": "online", "capabilities": ["midi.read", "midi.write"]})
        return venue_compatibility_plan(venue, self.show_compatibility_requirements(), discovered_devices=discovered)

    def venue_profile_inspect(self, data: dict[str, Any]) -> dict[str, Any]:
        venue = data.get("venue") if isinstance(data.get("venue"), dict) else data
        report = inspect_venue_profile(venue)
        profile = normalize_venue_profile(venue) if report.get("readable") else dict(venue)
        return {
            "valid": bool(report.get("readable")),
            "compatibility": report,
            "profile": profile,
            "deviceCount": len(profile.get("devices", [])),
            "humanCount": len(profile.get("humans", [])),
            "capabilityCount": len(profile.get("capabilities", [])),
        }

    def venue_adaptation_status(self) -> dict[str, Any]:
        return self.venue_adaptations.snapshot()

    def venue_adaptation_get(self, transaction_id: str) -> dict[str, Any]:
        return self.venue_adaptations.get(transaction_id)

    def venue_reconciliation_evidence(self) -> dict[str, Any]:
        return self.venue_realization.snapshot()

    def venue_authority_status(self) -> dict[str, Any]:
        return self.venue_authority_leases.snapshot()

    def public_record_status(self) -> dict[str, Any]:
        return self.public_record.verify()

    def public_record_attest(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"attestation": self.public_record.attest(data), "publicRecord": self.public_record.verify()}

    @staticmethod
    def _authority_department_for_resource(resource: str) -> str:
        resource = str(resource).strip()
        if resource.startswith("monitor:") or resource == "audio":
            return "audio"
        if resource.startswith("midi:") or resource == "midi-bindings":
            return "midi"
        if resource.startswith("notation:"):
            return "notation"
        if resource == "lighting-network":
            return "lighting"
        if resource == "technology":
            return "technology"
        if resource in {"transport", "handoff"}:
            return "production"
        if resource == "show":
            return "show"
        if resource == "system":
            return "system"
        return ""

    def resource_authority(self, resource: str, default: str | None = None) -> str | None:
        return self.venue_authority_leases.resolve(
            resource, self._authority_department_for_resource(resource), default=default
        )

    def _normalize_authority_lease_request(self, data: dict[str, Any]) -> dict[str, Any]:
        scope = str(data.get("scope", "")).strip()
        if not scope:
            raise ValueError("authority lease requires scope and grantee")
        active = self.venue_adaptations.snapshot().get("active")
        mappings = (active.get("mappings") or {}) if isinstance(active, dict) else {}
        domains = {str(key).split('.', 1)[0] for key in mappings}
        resources = set((self.state.snapshot().get("resourceRevisions") or {}).keys())
        departments = {self._authority_department_for_resource(item) for item in resources}
        departments.discard("")
        departments.update(domains)

        explicit_kind = str(data.get("scopeKind", "")).strip().lower()
        context = "runtime"
        if explicit_kind:
            kind = explicit_kind
            if kind == "patch":
                if scope not in mappings:
                    raise ValueError("patch authority lease scope is not part of the active Venue Patch Layer")
                context = "venue"
            elif kind == "resource":
                if scope not in resources:
                    raise ValueError("resource authority lease scope is not a known runtime resource")
            elif kind == "department":
                if scope not in departments:
                    raise ValueError("department authority lease scope is not a known runtime department")
            else:
                raise ValueError("authority lease scopeKind must be patch, department, or resource")
        elif scope in mappings:
            kind, context = "patch", "venue"
        elif scope in domains:
            # Preserve the original Venue Patch Layer domain shorthand.
            kind, context = "department", "venue"
        elif scope in resources:
            kind = "resource"
        elif scope in departments:
            kind = "department"
        else:
            raise ValueError("authority lease scope is not a known patch, department, or runtime resource")
        return {**data, "scope": scope, "scopeKind": kind, "context": context}

    def venue_authority_grant(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("authority lease grant requires current node authority")
        normalized = self._normalize_authority_lease_request(data)
        lease = self.venue_authority_leases.grant(normalized)
        try:
            public_record = self.public_record.append("authority-lease-grant", lease)
        except Exception:
            # A grant that cannot enter the durable public record must not remain active.
            self.venue_authority_leases.revoke(str(lease.get("leaseId", "")), "public-record-failure")
            raise RuntimeError("public record unavailable") from None
        lease = {**lease, "publicRecord": public_record}
        self.state.record_external_event(
            "authority",
            f"Authority leased: {lease.get('scopeKind')}:{lease.get('scope')} → {lease.get('grantee')}",
            lease,
        )
        self._persist_new_events()
        self._last_reconciliation_state = None
        return lease

    def venue_authority_revoke(self, lease_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("authority lease revoke requires current node authority")
        data = data or {}
        lease = self.venue_authority_leases.revoke(lease_id, str(data.get("requestedBy", "")))
        try:
            public_record = self.public_record.append("authority-lease-revoke", lease)
        except Exception:
            # Revocation is fail-safe and remains in effect even if public-record persistence fails.
            raise RuntimeError("public record unavailable after authority revocation") from None
        lease = {**lease, "publicRecord": public_record}
        self.state.record_external_event("authority", f"Venue authority lease revoked: {lease.get('scope')}", lease)
        self._persist_new_events()
        self._last_reconciliation_state = None
        return lease

    def venue_reconciliation_report(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = data or {}
        snapshot = self.venue_adaptations.snapshot()
        active = snapshot.get("active")
        if not isinstance(active, dict):
            return evaluate_realization(None, {}, [], self.venue_realization.snapshot())
        use_local = bool(data.get("useLocalDiscovery", active.get("discoveryMode") == "live"))
        plan, requirements = self._venue_plan_for_adaptation(use_local)
        profile = self.venue_profiles.load()
        authority: dict[str, str] = {}
        for key, patch in (profile.get("patch") or {}).items():
            if isinstance(patch, dict) and str(patch.get("authority", "")).strip():
                authority[str(key)] = str(patch.get("authority")).strip()[:160]
        authority.update(self.venue_authority_leases.authority_map())
        return evaluate_realization(active, plan, requirements, self.venue_realization.snapshot(), authority=authority)

    def venue_reconciliation_report_execution(self, data: dict[str, Any]) -> dict[str, Any]:
        active = self.venue_adaptations.snapshot().get("active")
        if not isinstance(active, dict):
            raise ValueError("no active Venue Patch Layer")
        patch_key = str(data.get("patchKey", "")).strip()
        if patch_key not in (active.get("mappings") or {}):
            raise ValueError("patchKey is not part of the active Venue Patch Layer")
        report = self.venue_realization.report(data)
        return {"accepted": True, "report": report, "reconciliation": self.venue_reconciliation_report({})}

    def venue_reconciliation_propose_repair(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("venue repair proposal requires current node authority")
        data = data or {}
        report = self.venue_reconciliation_report({"useLocalDiscovery": bool(data.get("useLocalDiscovery", True))})
        if report.get("status") not in {"drift", "blocked"}:
            raise ValueError("active Venue Patch Layer does not require a repair proposal")
        plan, requirements = self._venue_plan_for_adaptation(bool(data.get("useLocalDiscovery", True)))
        if not plan.get("compatible") or plan.get("readiness") != "ready":
            raise ValueError("current venue state cannot produce a safe repair transaction: " + "; ".join(plan.get("blockers") or []))
        show_venue = str((self.state.snapshot().get("system") or {}).get("venue", ""))
        with self._venue_adaptation_lock:
            return self.venue_adaptations.propose(
                plan, requirements, use_local_discovery=bool(data.get("useLocalDiscovery", True)), show_venue=show_venue,
                expected_revision=data.get("expectedAdaptationRevision"),
            )

    def _venue_plan_for_adaptation(self, use_local_discovery: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        requirements = self.show_compatibility_requirements()
        plan = self.venue_compatibility({"useLocalDiscovery": bool(use_local_discovery)})
        return plan, requirements

    def venue_adaptation_propose(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("venue adaptation proposals require current node authority")
        use_local = bool(data.get("useLocalDiscovery", False))
        plan, requirements = self._venue_plan_for_adaptation(use_local)
        show_venue = str((self.state.snapshot().get("system") or {}).get("venue", ""))
        with self._venue_adaptation_lock:
            return self.venue_adaptations.propose(
                plan, requirements, use_local_discovery=use_local, show_venue=show_venue,
                expected_revision=data.get("expectedAdaptationRevision"),
            )

    def venue_adaptation_validate(self, transaction_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = data or {}
        with self._venue_adaptation_lock:
            tx = self.venue_adaptations.get(transaction_id)
            use_local = tx.get("discoveryMode") == "live"
            plan, requirements = self._venue_plan_for_adaptation(use_local)
            return self.venue_adaptations.validate(transaction_id, plan, requirements, data.get("expectedAdaptationRevision"))

    def venue_adaptation_commit(self, transaction_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("venue adaptation commit requires current node authority")
        with self._venue_adaptation_lock:
            expected = data.get("expectedAdaptationRevision")
            tx = self.venue_adaptations.get(transaction_id)
            use_local = tx.get("discoveryMode") == "live"
            plan, requirements = self._venue_plan_for_adaptation(use_local)
            tx = self.venue_adaptations.validate(transaction_id, plan, requirements, expected)
            if not (tx.get("validation") or {}).get("valid"):
                raise ValueError("venue adaptation no longer validates: " + "; ".join((tx.get("validation") or {}).get("blockers") or []))
            transport = self.state.snapshot().get("transport") or {}
            result = self.venue_adaptations.schedule_commit(
                transaction_id,
                mode=str(data.get("mode", "immediate")),
                show_seconds=float(transport.get("seconds", 0.0)),
                bpm=float(transport.get("bpm", 120.0)),
                cue_id=str(data.get("cueId", "")),
                requested_by=str(data.get("requestedBy", "")),
            )
            if result.get("status") == "committed":
                result = self._after_venue_adaptation_commit(result)
            return result

    def venue_adaptation_rollback(self, transaction_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("venue adaptation rollback requires current node authority")
        seconds = float((self.state.snapshot().get("transport") or {}).get("seconds", 0.0))
        with self._venue_adaptation_lock:
            result = self.venue_adaptations.rollback(
                transaction_id, show_seconds=seconds, requested_by=str(data.get("requestedBy", "")),
                expected_revision=data.get("expectedAdaptationRevision"),
            )
        self.venue_realization.clear()
        self.venue_authority_leases.clear_context("venue")
        self._last_reconciliation_state = None
        active = self.venue_adaptations.snapshot().get("active")
        venue_name = (active or {}).get("venueName") or (result.get("rollback") or {}).get("restoredVenueName") or self.venue_profiles.load().get("name") or "Venue"
        with self._mutation_lock:
            state = self.state.patch_system({"venue": str(venue_name)})
            self._after_mutation(state)
            self.state.record_external_event("adaptation", "Venue Patch Layer rolled back", {
                "transactionId": transaction_id,
                "rollback": result.get("rollback"),
                "active": active,
                "physicalOutputsAutoArmed": False,
            })
            self._persist_new_events()
        return result

    def venue_adaptation_trigger_cue(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("cue-triggered adaptation requires current node authority")
        seconds = float((self.state.snapshot().get("transport") or {}).get("seconds", 0.0))
        with self._venue_adaptation_lock:
            committed = self.venue_adaptations.trigger_cue(str(data.get("cueId", "")), seconds, data.get("expectedAdaptationRevision"))
        committed = [self._after_venue_adaptation_commit(tx) for tx in committed]
        return {"cueId": str(data.get("cueId", "")), "committed": committed, "active": self.venue_adaptations.snapshot().get("active")}

    def _after_venue_adaptation_commit(self, transaction: dict[str, Any]) -> dict[str, Any]:
        receipt = transaction.get("receipt")
        if isinstance(receipt, dict) and not isinstance(receipt.get("publicRecord"), dict):
            evidence = self.public_record.append("venue-adaptation", receipt)
            transaction = self.venue_adaptations.attach_receipt_evidence(str(transaction.get("transactionId", "")), evidence)
        self.venue_realization.clear()
        self.venue_authority_leases.clear_context("venue")
        self._last_reconciliation_state = None
        venue_name = str(transaction.get("venueName") or transaction.get("venueId") or "Venue")
        with self._mutation_lock:
            state = self.state.patch_system({"venue": venue_name})
            self._after_mutation(state)
            self.state.record_external_event(
                "adaptation",
                f"Venue Patch Layer committed for {venue_name}",
                {
                    "transactionId": transaction.get("transactionId"),
                    "venueId": transaction.get("venueId"),
                    "boundary": transaction.get("commitBoundary"),
                    "receipt": transaction.get("receipt"),
                    "physicalOutputsAutoArmed": False,
                },
            )
            self._persist_new_events()
        return transaction

    def _adaptation_loop(self) -> None:
        while not self._stop.wait(0.02):
            if not self._has_authority() or not self.venue_adaptations.has_pending_bar_commit():
                continue
            transport = self.state.snapshot().get("transport") or {}
            try:
                committed = self.venue_adaptations.tick(float(transport.get("seconds", 0.0)))
            except (ValueError, TypeError):
                continue
            for tx in committed:
                self._after_venue_adaptation_commit(tx)

    def _reconciliation_loop(self) -> None:
        while not self._stop.wait(1.0):
            active = self.venue_adaptations.snapshot().get("active")
            if not isinstance(active, dict):
                self._last_reconciliation_state = None
                continue
            try:
                report = self.venue_reconciliation_report({})
            except (ValueError, RuntimeError):
                continue
            state_key = (report.get("transactionId"), report.get("patchRevision"), report.get("status"), tuple(report.get("blockers") or []), tuple(report.get("warnings") or []))
            if state_key == self._last_reconciliation_state:
                continue
            self._last_reconciliation_state = state_key
            self.state.record_external_event("reconciliation", f"Venue realization is {report.get('status')}", {
                "transactionId": report.get("transactionId"),
                "patchRevision": report.get("patchRevision"),
                "status": report.get("status"),
                "safeToContinue": report.get("safeToContinue"),
                "suggestedAction": report.get("suggestedAction"),
                "blockers": report.get("blockers"),
                "warnings": report.get("warnings"),
            })
            self._persist_new_events()

    def compatibility_inspect_show_state(self, data: dict[str, Any]) -> dict[str, Any]:
        snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else data
        result = inspect_show_state(snapshot)
        if result.get("readable"):
            normalized, migration = migrate_show_state(snapshot)
            result = {**result, "migration": migration, "normalizedApiVersion": normalized.get("apiVersion"), "unknownFieldsPreserved": True}
        return result

    def compatibility_migrate_show_state(self, data: dict[str, Any]) -> dict[str, Any]:
        snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else data
        normalized, report = migrate_show_state(snapshot)
        return {"snapshot": normalized, "report": report}

    def negotiate_technology(self, data: dict[str, Any]) -> dict[str, Any]:
        local = data.get("localCapabilities")
        remote = data.get("remoteCapabilities")
        if local is not None and not isinstance(local, list):
            raise ValueError("localCapabilities must be an array")
        if remote is not None and not isinstance(remote, list):
            raise ValueError("remoteCapabilities must be an array")
        return negotiate_technology_capabilities(local or [], remote or [])

    def _technology_receipt_binding(self, extension: dict[str, Any]) -> dict[str, Any]:
        reference = str(extension.get("adoptionRecordRef", "")).strip()
        if not reference:
            return {"verified": False, "reason": "signed-conformance-receipt-required"}
        try:
            record = self.public_record.resolve_reference(reference, record_type="technology-conformance")
        except (KeyError, ValueError, OSError, PermissionError):
            return {"verified": False, "reason": "signed-conformance-receipt-unavailable"}
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("version") != 1:
            return {"verified": False, "reason": "signed-conformance-receipt-invalid"}
        if str(payload.get("extensionId", "")) != str(extension.get("id", "")):
            return {"verified": False, "reason": "signed-conformance-receipt-extension-mismatch"}
        digest = technology_evidence_digest(extension)
        if str(payload.get("evidenceDigestSha256", "")) != digest:
            return {"verified": False, "reason": "signed-conformance-receipt-stale"}
        return {
            "verified": True,
            "reason": "verified",
            "recordId": record.get("recordId"),
            "recordHash": record.get("hash"),
            "receiptScaleTier": payload.get("scaleTier"),
            "receiptCoreEligible": bool(payload.get("coreEligible")),
            "receiptCoreGroupsRequired": int(payload.get("coreIndependentGroupsRequired", 0)),
        }

    def technology_assessment(self) -> dict[str, Any]:
        technology = self.state.technology_snapshot()
        assessment = evaluate_technology_registry(
            technology.get("extensions"),
            policy=technology.get("policy"),
            ecosystem_participants=int(technology.get("ecosystemParticipants", 1)),
        )
        extensions = {item.get("id"): item for item in technology.get("extensions", []) if isinstance(item, dict)}
        invalid: list[str] = []
        unsafe_core: list[str] = []
        scale_revalidation: list[str] = []
        verified_ids: list[str] = []
        stale_ids: list[str] = []
        for item in assessment.get("extensions", []):
            extension = extensions.get(item.get("id"), {})
            binding = self._technology_receipt_binding(extension)
            item["conformanceReceiptVerified"] = bool(binding["verified"])
            item["conformanceReceiptReason"] = binding["reason"]
            item["conformanceReceiptRecordId"] = binding.get("recordId")
            item["conformanceReceiptRecordHash"] = binding.get("recordHash")
            if binding["verified"]:
                verified_ids.append(item["id"])
            elif extension.get("adoptionRecordRef"):
                stale_ids.append(item["id"])

            if item.get("declaredMaturity") == "standard" and not binding["verified"]:
                item["declaredMaturityValid"] = False
                item["grandfatheredStandard"] = False
                item["scaleRevalidationNeeded"] = False
                blockers = list(item.get("maturityBlockers") or [])
                if binding["reason"] not in blockers:
                    blockers.append(binding["reason"])
                item["maturityBlockers"] = blockers

            core_claim = bool(extension.get("requestedCore") or extension.get("mandatoryCore"))
            if core_claim:
                receipt_current_for_core = bool(
                    binding["verified"]
                    and binding.get("receiptCoreEligible")
                    and binding.get("receiptScaleTier") == item.get("scaleTier")
                    and binding.get("receiptCoreGroupsRequired") == item.get("coreIndependentGroupsRequired")
                )
                if not receipt_current_for_core:
                    item["coreEligible"] = False
                    blockers = list(item.get("coreBlockers") or [])
                    blocker = ("current-scale-signed-core-conformance-receipt-required"
                               if binding["verified"] else binding["reason"])
                    if blocker not in blockers:
                        blockers.append(blocker)
                    item["coreBlockers"] = blockers

            if not item.get("declaredMaturityValid"):
                invalid.append(item["id"])
            if core_claim and not item.get("coreEligible"):
                unsafe_core.append(item["id"])
            if item.get("scaleRevalidationNeeded"):
                scale_revalidation.append(item["id"])

        assessment["invalidDeclaredMaturityIds"] = invalid
        assessment["unsafeCoreRequestIds"] = unsafe_core
        assessment["scaleRevalidationIds"] = scale_revalidation
        assessment["verifiedConformanceReceiptIds"] = verified_ids
        assessment["staleOrInvalidConformanceReceiptIds"] = stale_ids
        policy_failures = assessment.get("policyFailures") or []
        if unsafe_core or len(policy_failures) >= 2:
            assessment["openness"] = "at-risk"
        elif invalid or policy_failures:
            assessment["openness"] = "guarded"
        else:
            assessment["openness"] = "open"
        return assessment

    def technology_publish_conformance(self, data: dict[str, Any]) -> dict[str, Any]:
        extension_id = str(data.get("extensionId", "")).strip()[:160]
        if not extension_id:
            raise ValueError("extensionId is required")
        technology = self.state.technology_snapshot()
        extension = next((item for item in technology.get("extensions", []) if item.get("id") == extension_id), None)
        if extension is None:
            raise KeyError(extension_id)
        ecosystem_participants = int(technology.get("ecosystemParticipants", 1))
        evidence = evaluate_technology_extension(
            extension, policy=technology.get("policy"), ecosystem_participants=ecosystem_participants
        )
        if not evidence.get("declaredMaturityValid"):
            raise ValueError("declared technology maturity is not eligible for a conformance receipt")
        if evidence.get("declaredMaturity") == "standard" and not evidence.get("currentScaleStandardReady"):
            raise ValueError("current-scale Standard evidence is required to issue a new conformance receipt")
        if (extension.get("requestedCore") or extension.get("mandatoryCore")) and not evidence.get("coreEligible"):
            raise ValueError("current-scale Core evidence is required to issue a Core conformance receipt")
        requested_by = str(data.get("requestedBy", "")).strip()[:128]
        payload = {
            "version": 1,
            "extensionId": extension_id,
            "evidenceDigestSha256": technology_evidence_digest(extension),
            "declaredMaturity": evidence.get("declaredMaturity"),
            "scaleTier": evidence.get("scaleTier"),
            "ecosystemParticipants": ecosystem_participants,
            "currentScaleStandardReady": bool(evidence.get("currentScaleStandardReady")),
            "coreEligible": bool(evidence.get("coreEligible")),
            "standardIndependentGroupsRequired": int(evidence.get("standardIndependentGroupsRequired", 0)),
            "coreIndependentGroupsRequired": int(evidence.get("coreIndependentGroupsRequired", 0)),
            "independentGroupCount": int(evidence.get("independentGroupCount", 0)),
            "conformingIndependentGroupCount": int(evidence.get("conformingIndependentGroupCount", 0)),
            "interopPairCount": int(evidence.get("interopPairCount", 0)),
        }
        if requested_by:
            payload["requestedBy"] = requested_by
        reference = self.public_record.append("technology-conformance", payload)
        return {
            "adoptionRecordRef": self.public_record.reference_uri(reference),
            "publicRecord": reference,
            "receipt": payload,
        }

    def patch_technology(
        self,
        data: dict[str, Any],
        expected_revision: int | None,
        expected_resource_revision: int | None,
        command_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        if "policy" in data and not self.community.bootstrap_policy_mutation_allowed():
            bootstrap_override = os.environ.get("STAGEFORGE_GOVERNANCE_BOOTSTRAP", "0").strip().lower() in {"1", "true", "yes", "on"}
            if not bootstrap_override:
                raise PermissionError("technology openness policy changes require an adopted community proposal")
        return self.mutate(
            command_id,
            lambda: self.state.patch_technology(data, expected_revision, expected_resource_revision),
        )

    def community_status(self) -> dict[str, Any]:
        return self.community.snapshot(detail=False)

    def community_detail(self) -> dict[str, Any]:
        return self.community.snapshot(detail=True)

    def community_upsert_account(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.community.upsert_account(data)

    def community_patch_policy(self, data: dict[str, Any]) -> dict[str, Any]:
        bootstrap_override = os.environ.get("STAGEFORGE_GOVERNANCE_BOOTSTRAP", "0").strip().lower() in {"1", "true", "yes", "on"}
        if not self.community.bootstrap_policy_mutation_allowed() and not bootstrap_override:
            raise PermissionError("community governance policy is community-controlled; use an adopted community-governance-policy proposal")
        return self.community.patch_policy(data)

    def community_apply_change(self, proposal_id: str) -> dict[str, Any]:
        adopted = self.community.adopted_change(proposal_id)
        change = adopted["change"]
        kind = str(change.get("kind", ""))
        payload = change.get("payload") or {}
        if kind == "community-governance-policy":
            return self.community.apply_ratified_governance_policy(proposal_id)
        if kind == "technology-openness-policy":
            # Community ratification is the authorization. Apply through the
            # authoritative state mutation path without re-entering the normal
            # direct-policy gate.
            state, _ = self.mutate(
                f"community-apply:{proposal_id}:v{adopted['proposalVersion']}",
                lambda: self.state.patch_technology({"policy": payload}, None, None),
            )
            proposal = self.community.mark_change_applied(proposal_id)
            return {
                "applied": True,
                "proposalId": proposal_id,
                "changeHash": proposal.get("appliedChangeHash"),
                "technology": state.get("technology"),
            }
        raise ValueError(f"unsupported adopted community change kind: {kind}")

    def community_create_proposal(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.community.create_proposal(data)

    def community_update_proposal(self, proposal_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self.community.update_proposal(proposal_id, data)

    def community_issue_vote_emails(self, proposal_id: str, data: dict[str, Any]) -> dict[str, Any]:
        user_ids = data.get("userIds")
        if not isinstance(user_ids, list) or not user_ids:
            raise ValueError("userIds must be a non-empty array")
        window_hours = data.get("windowHours")
        if window_hours is not None:
            try:
                window_hours = int(window_hours)
            except (TypeError, ValueError) as exc:
                raise ValueError("windowHours must be an integer") from exc
        base_url = str(data.get("baseUrl") or os.environ.get("STAGEFORGE_PUBLIC_BASE_URL", "http://127.0.0.1:8787")).strip()
        return self.community.issue_vote_emails(proposal_id, [str(x) for x in user_ids], window_hours=window_hours, base_url=base_url)

    def community_vote_context(self, token: str) -> dict[str, Any]:
        return self.community.vote_context(token)

    def community_issue_session(self, authenticated_user_id: str | None) -> dict[str, Any]:
        if not authenticated_user_id:
            raise PermissionError("community account session requires trusted authenticated user identity")
        account = self.community.authenticated_account(authenticated_user_id)
        session = self.community_sessions.issue(account["id"], int(account.get("authGeneration", 1)))
        return {
            **session,
            "account": {
                "id": account["id"],
                "displayName": account.get("displayName", ""),
                "active": bool(account.get("active", False)),
            },
        }

    def community_revoke_sessions(self, authenticated_user_id: str | None) -> dict[str, Any]:
        if not authenticated_user_id:
            raise PermissionError("community session revocation requires trusted authenticated user identity")
        return self.community.revoke_account_sessions(authenticated_user_id)

    def community_cast_vote(self, data: dict[str, Any], authenticated_user_id: str | None) -> dict[str, Any]:
        token = str(data.get("token", "")).strip()
        session_token = str(data.get("sessionToken", "")).strip()
        if token and session_token:
            raise ValueError("provide either vote token or community session, not both")
        if session_token:
            proposal_id = str(data.get("proposalId", "")).strip()
            if not proposal_id:
                raise ValueError("proposalId is required for community session voting")
            session = self.community_sessions.verify(session_token)
            if authenticated_user_id and authenticated_user_id != session.account_id:
                raise PermissionError("trusted authenticated user does not match community session")
            account = self.community.authenticated_account(session.account_id)
            if int(account.get("authGeneration", 1)) != session.auth_generation:
                raise PermissionError("community session has been revoked")
            return self.community.cast_account_vote(
                proposal_id, str(data.get("choice", "")), account_id=session.account_id
            )
        if not token:
            raise ValueError("vote token is required")
        allow_token_only = os.environ.get("STAGEFORGE_GOVERNANCE_TOKEN_ONLY", "0").strip().lower() in {"1", "true", "yes", "on"}
        return self.community.cast_vote(token, str(data.get("choice", "")), authenticated_user_id=authenticated_user_id, allow_token_only=allow_token_only)

    def community_tally(self, proposal_id: str, at: str | None = None) -> dict[str, Any]:
        return self.community.proposal_tally(proposal_id, at)

    def community_monitor(self, at: str | None = None) -> dict[str, Any]:
        return self.community.monitor(at)

    def community_public_record_reconcile(self, proposal_id: str | None = None) -> dict[str, Any]:
        result = self.community.reconcile_public_record(proposal_id)
        return {**result, "publicRecord": self.public_record.verify()}

    def patch_handoff(
        self,
        data: dict[str, Any],
        expected_revision: int | None,
        expected_resource_revision: int | None,
        command_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        return self.mutate(
            command_id,
            lambda: self.state.patch_handoff(data, expected_revision, expected_resource_revision),
        )

    def patch_audio(
        self,
        data: dict[str, Any],
        expected_revision: int | None,
        expected_resource_revision: int | None,
        command_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        state, deduplicated = self.mutate(
            command_id,
            lambda: self.state.patch_audio(data, expected_revision, expected_resource_revision),
        )
        if self.native.available:
            try:
                self._refresh_audio_devices(reselect=True)
                audio = state.get("audio") or {}
                for config in self._audio_output_configs(audio):
                    graph_output = int(config.get("graphOutput", 0))
                    player_id = str(config.get("playerId", "")).strip()
                    if player_id:
                        try:
                            graph_output = int(self.native.bind_audio_output_player(player_id, int(config["slot"])).get("output", graph_output))
                        except (RuntimeError, ValueError):
                            pass
                    self.native.set_audio_output(graph_output, float(config.get("master", 1.0)), float(config.get("limiterCeilingDb", -1.0)))
            except (RuntimeError, ValueError, TypeError):
                pass
        return state, deduplicated

    def _audio_activation_check(self, device: dict[str, Any], direction: str, rate: int,
                                channels: int, period: int, slot: int, sample_format: str = "FLOAT_LE") -> dict[str, Any]:
        backend = str(device.get("backend", "") or "alsa").strip().lower()
        if backend != "alsa":
            raise RuntimeError(f"audio {direction} activation preflight adapter is not implemented for {backend or 'unknown'}")
        try:
            report = audio_preflight({"address": str(device.get("address", "")), "direction": direction,
                                      "format": sample_format, "sampleRate": rate,
                                      "channels": channels, "periodFrames": period})
        except ValueError as exc:
            raise RuntimeError("audio activation requires an explicit numeric ALSA hardware endpoint") from exc
        self._audio_activation_preflight[("output" if direction == "playback" else "input", slot)] = report
        if report.get("supported") is not True:
            raise RuntimeError(f"audio {direction} preflight blocked activation: {report['status']}")
        return report

    @_audio_controlled
    def activate_audio(self, data: dict[str, Any], slot: int = 0) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("node lacks authoritative lease for physical audio output")
        if not self.native.available:
            raise RuntimeError("native audio execution unavailable")
        if data.get("acknowledgePhysicalOutput") is not True:
            raise ValueError("audio activation requires acknowledgePhysicalOutput=true")
        slot = int(slot)
        if not 0 <= slot < 4:
            raise ValueError("audio output slot must be 0..3")
        audio = self.state.snapshot().get("audio") or {}
        config = self._audio_output_configs(audio)[slot]
        show_desired = str(config.get("deviceId", ""))
        mapped_desired = self._mapped_execution_device("audio.foh") if slot == 0 else None
        desired = mapped_desired or show_desired
        if not desired:
            raise RuntimeError(f"no desired audio output device is configured for slot {slot}")
        self._refresh_audio_devices(reselect=True)
        device = self._find_audio_device(desired,"output")
        if desired != "null-audio" and (not device or not device.get("connected") or not device.get("output")):
            raise RuntimeError("desired audio output is not currently connected")
        requested_rate = int(audio.get("sampleRate", 192000))
        requested_period = int(audio.get("bufferFrames", 256))
        requested_format = str(data.get("format", "FLOAT_LE"))
        requested_channels = int(data.get("channels", 2))
        preflight = {"status": "virtual-device", "supported": True, "streamStarted": False}
        if desired != "null-audio":
            preflight = self._audio_activation_check(device, "playback", requested_rate,
                                                       requested_channels, requested_period, slot, requested_format)
        conversion = audio_conversion_plan({"sampleRate": requested_rate, "format": requested_format, "channels": requested_channels}, data.get("conversionPolicy"), direction="playback")
        graph_output = int(config.get("graphOutput", 0))
        player_id = str(config.get("playerId", "")).strip()
        execution_device_id=str(device.get("id",desired)) if device else desired
        self.native.select_audio_device(execution_device_id, slot)
        if player_id:
            binding = self.native.bind_audio_output_player(player_id, slot)
            graph_output = int(binding.get("output", graph_output))
        self.native.set_audio_output(graph_output, float(config.get("master", 1.0)), float(config.get("limiterCeilingDb", -1.0)))
        drift = config.get("driftCompensation") or {}
        self.native.configure_audio_drift(
            slot,
            enabled=bool(drift.get("enabled", True)),
            max_ppm=float(drift.get("maxCorrectionPpm", 2000.0)),
            queue_gain_ppm=float(drift.get("queueGainPpm", 1000.0)),
        )
        raw = self.native.activate_audio(float(requested_rate), requested_period, graph_output, slot, conversion["nativeConversionFlags"], requested_format, requested_channels)
        running = _physical_audio_execution(raw.get("execution")) and raw.get("running") == "1"
        if running:
            self._refresh_audio_devices(reselect=False)
            if not self._find_audio_device(desired,"output"):
                self.native.deactivate_audio(slot)
                raise RuntimeError("audio output disconnected during activation; stream was stopped")
            self._mark_post_promotion_output("audio")
        return {
            "slot": slot,
            "active": running,
            "executionBackend": raw.get("execution", "none"),
            "deviceId": raw.get("device", desired),
            "output": int(raw.get("output", graph_output)),
            "playerId": player_id or None,
            "purpose": config.get("purpose", "aux"),
            "desiredDeviceId": desired,
            "executionDeviceId": execution_device_id,
            "automaticIdentityReconnect": execution_device_id != desired,
            "showDesiredDeviceId": show_desired,
            "venuePatchApplied": bool(mapped_desired),
            "activationPreflight": preflight,
            "conversionPlan": audio_conversion_plan({"sampleRate": round(float(raw.get("actualRate", audio.get("sampleRate", 192000)))), "format": raw.get("actualFormat", "FLOAT_LE"), "channels": int(raw.get("actualChannels", 2))}, data.get("conversionPolicy"), direction="playback"),
        }

    @_audio_controlled
    def deactivate_audio(self, slot: int = 0) -> dict[str, Any]:
        if not self.native.available:
            raise RuntimeError("native audio execution unavailable")
        slot = int(slot)
        if not 0 <= slot < 4:
            raise ValueError("audio output slot must be 0..3")
        self.native.deactivate_audio(slot)
        return self.audio_stream_status(slot)

    def audio_stream_status(self, slot: int = 0) -> dict[str, Any]:
        slot = int(slot)
        if not 0 <= slot < 4:
            raise ValueError("audio output slot must be 0..3")
        config = self._audio_output_configs()[slot]
        show_desired = str(config.get("deviceId", ""))
        mapped_desired = self._mapped_execution_device("audio.foh") if slot == 0 else None
        desired = mapped_desired or show_desired
        connected = desired == "null-audio" or self._find_audio_device(desired,"output") is not None
        if not self.native.available:
            return {"available": False, "slot": slot, "executionBackend": "bridge-only", "active": False, "desiredDeviceId": desired, "desiredConnected": connected}
        try:
            raw = self.native.audio_stream_status(slot)
        except RuntimeError:
            return {"available": False, "slot": slot, "executionBackend": "none", "active": False, "desiredDeviceId": desired, "desiredConnected": connected}
        desired_drift = dict(config.get("driftCompensation") or {})
        native_drift_enabled = raw.get("driftEnabled", "0") == "1"
        native_max_ppm = float(raw.get("maxCorrectionPpm", "2000"))
        native_queue_gain_ppm = float(raw.get("queueGainPpm", "1000"))
        drift_policy_applied = (
            native_drift_enabled == bool(desired_drift.get("enabled", True))
            and abs(native_max_ppm - float(desired_drift.get("maxCorrectionPpm", 2000.0))) < 0.01
            and abs(native_queue_gain_ppm - float(desired_drift.get("queueGainPpm", 1000.0))) < 0.01
        )
        return {
            "available": True,
            "slot": slot,
            "active": _physical_audio_execution(raw.get("execution")) and raw.get("state") == "2",
            "executionBackend": raw.get("execution", "none"),
            "selectedDeviceId": raw.get("selected", "none"),
            "desiredDeviceId": desired,
            "showDesiredDeviceId": show_desired,
            "venuePatchApplied": bool(mapped_desired),
            "desiredConnected": connected,
            "purpose": config.get("purpose", "aux"),
            "playerId": config.get("playerId") or None,
            "state": int(raw.get("state", "0")),
            "callbacks": int(raw.get("callbacks", "0")),
            "xruns": int(raw.get("xruns", "0")),
            "output": int(raw.get("output", str(config.get("graphOutput", 0)))),
            "queuedFrames": int(raw.get("queued", "0")),
            "droppedFrames": int(raw.get("dropped", "0")),
            "underrunFrames": int(raw.get("underruns", "0")),
            "rateMeasured": raw.get("rateMeasured", "0") == "1",
            "ratePpm": float(raw.get("ratePpm", "0")),
            "driftCompensation": desired_drift,
            "driftEnabled": native_drift_enabled,
            "activeMaxCorrectionPpm": native_max_ppm,
            "activeQueueGainPpm": native_queue_gain_ppm,
            "driftPolicyApplied": drift_policy_applied,
            "correctionPpm": float(raw.get("correctionPpm", "0")),
            "sourceFrames": int(raw.get("sourceFrames", "0")),
            "compensatedBlocks": int(raw.get("compensatedBlocks", "0")),
            "firstWriteNs": int(raw.get("firstWriteNs", "0")),
            "lastWriteNs": int(raw.get("lastWriteNs", "0")),
            "maxExcessGapNs": int(raw.get("maxExcessGapNs", "0")),
            "maxExcessGapMs": round(int(raw.get("maxExcessGapNs", "0")) / 1_000_000.0, 3),
            "framesWritten": int(raw.get("framesWritten", "0")),
            "configuredSampleRate": float(raw.get("configuredRate", "0")),
            "configuredPeriodFrames": int(raw.get("periodFrames", "0")),
            "configuredChannels": int(raw.get("channels", "0")),
            "requestedSampleRate": float(raw.get("requestedRate", "0")),
            "requestedPeriodFrames": int(raw.get("requestedPeriodFrames", "0")),
            "requestedChannels": int(raw.get("requestedChannels", "0")),
            "configuredSampleFormat": raw.get("sampleFormat", "unknown"),
            "firstRenderShowNs": int(raw.get("firstRenderShowNs", "0")),
            "lastRenderShowNs": int(raw.get("lastRenderShowNs", "0")),
            "lastBlockEndShowNs": int(raw.get("lastBlockEndShowNs", "0")),
            "master": float(config.get("master", 1.0)),
            "limiterCeilingDb": float(config.get("limiterCeilingDb", -1.0)),
            "error": None if raw.get("error", "none") == "none" else raw.get("error", "").replace("_", " "),
            "activationPreflight": self._audio_activation_preflight.get(("output", slot)),
        }

    @_audio_controlled
    def recover_audio(self, data: dict[str, Any], slot: int = 0) -> dict[str, Any]:
        if data.get("acknowledgeRecovery") is not True:
            raise ValueError("audio recovery requires acknowledgeRecovery=true")
        if self.audio_stream_status(slot).get("active"):
            raise ValueError("audio output is already active")
        return {**self.activate_audio(data, slot), "recoveryAttempted": True}

    def audio_outputs_status(self) -> dict[str, Any]:
        return {"available": self.native.available, "outputs": [self.audio_stream_status(slot) for slot in range(4)]}

    @_audio_controlled
    def activate_audio_input(self, data: dict[str, Any], slot: int = 0) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("node lacks authoritative lease for physical audio input")
        if not self.native.available:
            raise RuntimeError("native audio input unavailable")
        if data.get("acknowledgePhysicalInput") is not True:
            raise ValueError("audio input activation requires acknowledgePhysicalInput=true")
        slot = int(slot)
        if not 0 <= slot < 4:
            raise ValueError("audio input slot must be 0..3")
        audio = self.state.snapshot().get("audio") or {}
        config = self._audio_input_configs(audio)[slot]
        show_desired = str(config.get("deviceId", ""))
        mapped_desired = self._mapped_execution_device("audio.live-input") if slot == 0 else None
        desired = mapped_desired or show_desired
        if not desired:
            raise RuntimeError(f"no desired audio input device is configured for slot {slot}")
        self._refresh_audio_devices(reselect=True)
        device = self._find_audio_device(desired,"input")
        if not device or not device.get("connected") or not device.get("input"):
            raise RuntimeError("desired audio input is not currently connected")
        requested_rate = int(config.get("sampleRate", audio.get("sampleRate", 192000)))
        requested_period = int(audio.get("bufferFrames", 256))
        route = config.get("route") or {}
        gain = float(route.get("gain", 0.0))
        if gain > 0.0 and data.get("acknowledgeSignalRoute") is not True:
            raise ValueError("nonzero persisted input routing requires acknowledgeSignalRoute=true")
        channels = int(data.get("channels", 2))
        requested_format = str(data.get("format", "FLOAT_LE"))
        preflight = self._audio_activation_check(device, "capture", requested_rate, channels, requested_period, slot, requested_format)
        conversion = audio_conversion_plan({"sampleRate": requested_rate, "format": requested_format, "channels": channels}, data.get("conversionPolicy"), direction="capture")
        source = 24 + slot
        player_id = str(config.get("playerId", "")).strip()
        execution_device_id=str(device.get("id",desired))
        self.native.select_audio_input(execution_device_id, slot)
        if player_id:
            binding = self.native.bind_audio_input_player(player_id, slot)
            source = int(binding.get("source", source))
        raw = self.native.activate_audio_input(float(requested_rate), requested_period, channels, source, slot, conversion["nativeConversionFlags"], requested_format)
        self.native.route_audio_input(int(route.get("output", 0)), gain, slot)
        running = _physical_audio_execution(raw.get("execution")) and raw.get("running") == "1"
        if running:
            self._refresh_audio_devices(reselect=False)
            if not self._find_audio_device(desired,"input"):
                self.native.deactivate_audio_input(slot)
                raise RuntimeError("audio input disconnected during activation; stream was stopped")
        return {"slot": slot, "active": running, "executionBackend": raw.get("execution", "none"), "deviceId": raw.get("device", execution_device_id), "desiredDeviceId":desired,"executionDeviceId":execution_device_id,"automaticIdentityReconnect":execution_device_id!=desired,"source": int(raw.get("source", source)), "playerId": player_id or None, "route": route, "showDesiredDeviceId": show_desired, "venuePatchApplied": bool(mapped_desired), "activationPreflight": preflight, "conversionPlan": audio_conversion_plan({"sampleRate": round(float(raw.get("actualRate", requested_rate))), "format": raw.get("actualFormat", "FLOAT_LE"), "channels": int(raw.get("actualChannels", channels))}, data.get("conversionPolicy"), direction="capture")}

    @_audio_controlled
    def deactivate_audio_input(self, slot: int = 0) -> dict[str, Any]:
        if not self.native.available:
            raise RuntimeError("native audio input unavailable")
        self.native.deactivate_audio_input(slot)
        return self.audio_input_status(slot)

    def audio_input_status(self, slot: int = 0) -> dict[str, Any]:
        slot = int(slot)
        if not 0 <= slot < 4:
            raise ValueError("audio input slot must be 0..3")
        if not self.native.available:
            return {"available": False, "slot": slot, "active": False, "executionBackend": "none"}
        try:
            raw = self.native.audio_input_status(slot)
        except RuntimeError:
            return {"available": False, "slot": slot, "active": False, "executionBackend": "none"}
        config = self._audio_input_configs()[slot]
        show_desired = str(config.get("deviceId", ""))
        mapped_desired = self._mapped_execution_device("audio.live-input") if slot == 0 else None
        desired = mapped_desired or show_desired
        connected = self._find_audio_device(desired,"input") is not None if desired else False
        return {
            "available": True, "slot": slot, "active": _physical_audio_execution(raw.get("execution")) and int(raw.get("state", "0")) == 2, "executionBackend": raw.get("execution", "none"),
            "deviceId": raw.get("selected", "none"), "desiredDeviceId": desired, "showDesiredDeviceId": show_desired, "venuePatchApplied": bool(mapped_desired), "desiredConnected": connected, "playerId": config.get("playerId") or None, "sampleRate": float(raw.get("sampleRate", config.get("sampleRate", 192000.0))), "route": config.get("route") or {},
            "source": int(raw.get("source", str(24 + slot))), "callbacks": int(raw.get("callbacks", "0")), "xruns": int(raw.get("xruns", "0")),
            "configuredSampleRate": float(raw.get("configuredRate", "0")), "configuredPeriodFrames": int(raw.get("periodFrames", "0")), "configuredChannels": int(raw.get("channels", "0")),
            "requestedSampleRate": float(raw.get("requestedRate", "0")), "requestedPeriodFrames": int(raw.get("requestedPeriodFrames", "0")), "requestedChannels": int(raw.get("requestedChannels", "0")), "configuredSampleFormat": raw.get("sampleFormat", "unknown"),
            "queuedFrames": int(raw.get("queued", "0")), "droppedFrames": int(raw.get("dropped", "0")), "underrunFrames": int(raw.get("underruns", "0")),
            "error": None if raw.get("error", "none") == "none" else raw.get("error"),
        }

    @_audio_controlled
    def recover_audio_input(self, data: dict[str, Any], slot: int = 0) -> dict[str, Any]:
        if data.get("acknowledgeRecovery") is not True:
            raise ValueError("audio input recovery requires acknowledgeRecovery=true")
        if self.audio_input_status(slot).get("active"):
            raise ValueError("audio input is already active")
        return {**self.activate_audio_input(data, slot), "recoveryAttempted": True}

    def audio_inputs_status(self) -> dict[str, Any]:
        return {"available": self.native.available, "inputs": [self.audio_input_status(slot) for slot in range(4)]}

    def configure_le_uwb_hub(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("node lacks authoritative lease for LE-UWB hub coordination")
        if not self.native.available:
            raise RuntimeError("native LE-UWB hub unavailable")
        epoch = int(self.replication.status().get("epoch", 0))
        if epoch <= 0:
            raise RuntimeError("LE-UWB hub requires a nonzero authority epoch")
        raw = self.native.configure_le_uwb_hub(
            epoch,
            target_lead_ns=int(data.get("targetPresentationLeadNs", 10_000_000)),
            max_end_to_end_ns=int(data.get("maxEndToEndNs", 30_000_000)),
            fresh_ns=int(data.get("freshObservationNs", 100_000_000)),
            holdover_ns=int(data.get("holdoverNs", 500_000_000)),
            max_clock_uncertainty_ns=int(data.get("maxClockUncertaintyNs", 250_000)),
            max_jitter_ns=int(data.get("maxJitterNs", 500_000)),
            max_range_uncertainty_mm=float(data.get("maxRangeUncertaintyMm", 300.0)),
            max_drift_ppm=float(data.get("maxDriftPpm", 250.0)),
            require_authenticated=bool(data.get("requireAuthenticatedObservations", True)),
        )
        return {"configured": True, "authorityEpoch": int(raw["epoch"]), "physicalOutputsArmed": False}

    def register_le_uwb_node(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("node lacks authoritative lease for LE-UWB hub coordination")
        roles = {"performer-input": 0, "monitor-output": 1, "stage-output": 2, "lighting": 3, "control": 4}
        role = str(data.get("role", "")).strip().lower()
        if role not in roles:
            raise ValueError("LE-UWB node role must be performer-input, monitor-output, stage-output, lighting, or control")
        raw = self.native.register_le_uwb_node(
            int(data.get("nodeId", 0)), int(data.get("leStreamId", 0)), roles[role],
            int(data.get("presentationDelayNs", 0)), required=bool(data.get("required", True)),
        )
        return {"nodeId": int(raw["nodeId"]), "registered": True, "physicalOutputsArmed": False}

    def report_uwb_observation(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("standby cannot ingest authoritative UWB timing evidence")
        epoch = int(self.replication.status().get("epoch", 0))
        raw = self.native.observe_uwb_node(
            int(data.get("nodeId", 0)), int(data.get("sequence", 0)), epoch,
            int(data.get("hubTimeNs", 0)), int(data.get("nodeTimeNs", 0)),
            float(data.get("distanceMm", 0.0)), float(data.get("rangeUncertaintyMm", 0.0)),
            int(data.get("clockUncertaintyNs", 0)), authenticated=True,
        )
        return {"nodeId": int(raw["nodeId"]), "uwbSequence": int(raw["uwbSequence"]), "accepted": True}

    def report_le_isochronous_observation(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("standby cannot ingest authoritative LE transport evidence")
        epoch = int(self.replication.status().get("epoch", 0))
        raw = self.native.observe_le_isochronous(
            int(data.get("nodeId", 0)), int(data.get("sequence", 0)), epoch,
            int(data.get("eventCounter", 0)), int(data.get("hubTimeNs", 0)),
            int(data.get("transportLatencyNs", 0)), int(data.get("jitterNs", 0)), authenticated=True,
        )
        return {"nodeId": int(raw["nodeId"]), "leSequence": int(raw["leSequence"]), "eventCounter": int(raw["eventCounter"]), "accepted": True}

    def plan_le_uwb_sync(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._has_authority():
            raise RuntimeError("node lacks authoritative lease for LE-UWB group planning")
        data = data or {}
        hub_now_ns = int(data.get("hubNowNs", monotonic_ns()))
        show_now_ns = int(data.get("showNowNs", max(0.0, float((self.state.snapshot().get("transport") or {}).get("seconds", 0.0))) * 1_000_000_000))
        epoch = int(self.replication.status().get("epoch", 0))
        raw = self.native.plan_le_uwb_sync(hub_now_ns, show_now_ns, epoch)
        return {
            "generation": int(raw["generation"]), "authorityEpoch": int(raw["epoch"]),
            "targetHubNs": int(raw["targetHubNs"]), "targetShowNs": int(raw["targetShowNs"]),
            "presentationLeadNs": int(raw["leadNs"]), "configuredNodes": int(raw["configured"]),
            "requiredNodes": int(raw["required"]), "readyNodes": int(raw["readyNodes"]),
            "holdoverNodes": int(raw["holdover"]), "blockedNodes": int(raw["blocked"]),
            "ready": raw["ready"] == "1", "physicalOutputsArmed": False,
        }

    def le_uwb_node_status(self, node_id: int) -> dict[str, Any]:
        raw = self.native.le_uwb_node_status(int(node_id))
        roles = ["performer-input", "monitor-output", "stage-output", "lighting", "control"]
        states = ["unconfigured", "awaiting-uwb", "awaiting-le", "locked", "holdover", "blocked"]
        return {
            "nodeId": int(raw["nodeId"]), "leStreamId": int(raw["streamId"]),
            "role": roles[int(raw["role"])], "state": states[int(raw["state"])],
            "required": raw["required"] == "1", "authorityEpoch": int(raw["epoch"]),
            "uwbSequence": int(raw["uwbSequence"]), "leSequence": int(raw["leSequence"]),
            "leEventCounter": int(raw["eventCounter"]), "distanceMm": float(raw["distanceMm"]),
            "rangeUncertaintyMm": float(raw["rangeUncertaintyMm"]), "clockUncertaintyNs": int(raw["clockUncertaintyNs"]),
            "clockOffsetNs": int(raw["clockOffsetNs"]), "driftPpm": float(raw["driftPpm"]),
            "transportLatencyNs": int(raw["transportLatencyNs"]), "jitterNs": int(raw["jitterNs"]),
            "authenticated": raw["authenticated"] == "1", "rejectedObservations": int(raw["rejected"]),
            "physicalOutputsArmed": False,
        }

    def _configure_lighting_from_state(self) -> None:
        if not self.native.available:
            return
        network = ((self.state.snapshot().get("lighting") or {}).get("network") or {})
        target = str(network.get("target", "")).strip()
        protocol = str(network.get("protocol", "artnet")).lower()
        if target and protocol in {"artnet", "sacn"}:
            self.native.configure_lighting_network(
                target,
                int(network.get("port", 5568 if protocol == "sacn" else 6454)),
                protocol=protocol,
                universe_base=int(network.get("universeBase", 1)),
            )
        self.native.arm_lighting_network(False)
        self._lighting_armed = False

    def lighting_network_status(self) -> dict[str, Any]:
        desired = ((self.state.snapshot().get("lighting") or {}).get("network") or {})
        mapped = self._mapped_lighting_execution()
        execution_desired = mapped or desired
        if not self.native.available:
            return {"available": False, "armed": False, "desired": desired, "executionDesired": execution_desired, "venuePatchApplied": bool(mapped), "physicalOutput": False}
        try:
            raw = self.native.lighting_network_status()
        except RuntimeError:
            raw = {}
        return {
            "available": True,
            "configured": raw.get("configured") == "1",
            "armed": raw.get("armed") == "1",
            "target": raw.get("target", ""),
            "port": int(raw.get("port", desired.get("port", 6454))),
            "protocol": raw.get("protocol", execution_desired.get("protocol", desired.get("protocol", "artnet"))),
            "universeBase": int(raw.get("universeBase", execution_desired.get("universeBase", desired.get("universeBase", 1)))),
            "packetsSent": int(raw.get("packets", "0")),
            "sendErrors": int(raw.get("errors", "0")),
            "desired": desired,
            "executionDesired": execution_desired,
            "venuePatchApplied": bool(mapped),
            "physicalOutput": raw.get("armed") == "1",
        }

    def patch_lighting_network(
        self, data: dict[str, Any], expected_revision: int | None, expected_resource_revision: int | None, command_id: str | None = None
    ) -> tuple[dict[str, Any], bool]:
        # Reconfiguration always disarms physical output first. The desired
        # target persists; authority to transmit does not.
        if self.native.available:
            try:
                self.native.arm_lighting_network(False)
            except RuntimeError:
                pass
        self._lighting_armed = False
        state, deduplicated = self.mutate(
            command_id,
            lambda: self.state.patch_lighting_network(data, expected_revision, expected_resource_revision),
        )
        if self.native.available:
            network = ((state.get("lighting") or {}).get("network") or {})
            protocol = str(network.get("protocol", "artnet")).lower()
            if protocol in {"artnet", "sacn"} and str(network.get("target", "")).strip():
                self.native.configure_lighting_network(
                    str(network["target"]),
                    int(network.get("port", 5568 if protocol == "sacn" else 6454)),
                    protocol=protocol,
                    universe_base=int(network.get("universeBase", 1)),
                )
        return state, deduplicated

    def arm_lighting_network(self, data: dict[str, Any]) -> dict[str, Any]:
        if bool(data.get("armed", False)) and not self._has_authority():
            raise RuntimeError("node lacks authoritative lease for physical lighting output")
        if not self.native.available:
            raise RuntimeError("native lighting output unavailable")
        armed = bool(data.get("armed", False))
        if armed and data.get("acknowledgePhysicalOutput") is not True:
            raise ValueError("arming lighting output requires acknowledgePhysicalOutput=true")
        network = ((self.state.snapshot().get("lighting") or {}).get("network") or {})
        mapped_network = self._mapped_lighting_execution()
        execution_network = mapped_network or network
        if armed:
            protocol = str(execution_network.get("protocol", "artnet")).lower()
            if protocol not in {"artnet", "sacn"}:
                raise RuntimeError("unsupported lighting network protocol")
            target = str(execution_network.get("target", "")).strip()
            if not target:
                raise ValueError(f"configure a unicast {protocol} target before arming")
            self.native.configure_lighting_network(
                target,
                int(execution_network.get("port", 5568 if protocol == "sacn" else 6454)),
                protocol=protocol,
                universe_base=int(execution_network.get("universeBase", 1)),
            )
        self.native.arm_lighting_network(armed)
        self._lighting_armed = armed
        if armed:
            self._mark_post_promotion_output("lighting")
        return self.lighting_network_status()

    def _refresh_midi_devices(self, *, rebind: bool = False) -> list[dict[str, Any]]:
        if not hasattr(self, "_midi_scan_lock"):
            self._midi_scan_lock = RLock()
        if not hasattr(self, "_midi_hotplug_generation"):
            self._midi_hotplug_generation = 0
        if not hasattr(self, "_midi_hotplug_changes"):
            self._midi_hotplug_changes = []
        with self._midi_scan_lock:
            if not self.native.available:
                self._midi_devices = []
                return []
            devices = self.native.scan_midi_devices()
            bindings = (self.state.snapshot().get("midi") or {}).get("bindings") or {}
            previous_by_id = {str(item.get("id", "")): item for item in self._midi_devices}
            previous_ids = set(previous_by_id)
            for device in devices:
                device_id = str(device.get("id", ""))
                device.update(describe_midi_device(device))
                device["attached"] = bool(device.get("attached"))
                device["identityRecorded"] = self.midi_identities.expected(device_id) is not None
            current_by_id = {str(device.get("id", "")): device for device in devices}
            current_ids = set(current_by_id)
            disconnected = previous_ids - current_ids
            prior_identity = {
                device_id: (previous_by_id.get(device_id) or self.midi_identities.expected(device_id) or {}).get("persistentId")
                for device_id in current_ids
            }
            identity_changed = {
                device_id for device_id in current_ids
                if prior_identity.get(device_id)
                and current_by_id[device_id].get("persistentId")
                and prior_identity[device_id] != current_by_id[device_id].get("persistentId")
                and (device_id not in previous_by_id
                     or previous_by_id[device_id].get("persistentId") != current_by_id[device_id].get("persistentId"))
            }
            unsafe_ids = disconnected | identity_changed
            detached: list[str] = []
            for device_id in sorted(unsafe_ids):
                try:
                    self.native.detach_midi_input(device_id)
                    detached.append(device_id)
                except (RuntimeError, ValueError):
                    pass

            claims: dict[str, list[tuple[str, str]]] = {}
            for desired_id, player_id in bindings.items():
                candidate = self.midi_identities.resolve(str(desired_id), devices)
                if candidate is None:
                    continue
                current_id = str(candidate.get("id", ""))
                claims.setdefault(current_id, []).append((str(desired_id), str(player_id)))

            if rebind and self.replication.is_primary():
                for current_id, desired in claims.items():
                    players = {player_id for _, player_id in desired}
                    if len(desired) != 1 or len(players) != 1:
                        continue
                    desired_id, player_id = desired[0]
                    try:
                        self.native.attach_midi_input(current_id, player_id)
                        current_by_id[current_id]["attached"] = True
                    except (RuntimeError, ValueError):
                        pass

            for device in devices:
                device_id = str(device.get("id", ""))
                desired = claims.get(device_id, [])
                desired_ids = [wanted for wanted, _ in desired]
                players = {player for _, player in desired}
                device["desired"] = bool(desired)
                device["desiredDeviceIds"] = desired_ids
                device["reconnectsDeviceIds"] = [wanted for wanted in desired_ids if wanted != device_id]
                device["playerId"] = next(iter(players)) if len(desired) == 1 and len(players) == 1 else None
                if len(desired) > 1 or len(players) > 1:
                    device["reconnectStatus"] = "ambiguous"
                elif device["reconnectsDeviceIds"]:
                    device["reconnectStatus"] = "persistent-match"
                elif desired:
                    device["reconnectStatus"] = "eligible" if self.midi_identities.permits_rebind(device_id, device) else "explicit-rebind-required"
                else:
                    device["reconnectStatus"] = "unbound"

            changes = ([{"kind": "connected", "deviceId": value} for value in sorted(current_ids - previous_ids)]
                       + [{"kind": "disconnected", "deviceId": value, "detached": value in detached} for value in sorted(disconnected)]
                       + [{"kind": "identity-changed", "deviceId": value,
                           "previousPersistentId": prior_identity[value],
                           "currentPersistentId": current_by_id[value].get("persistentId"),
                           "detached": value in detached} for value in sorted(identity_changed)])
            if changes:
                self._midi_hotplug_generation += 1
                for change in changes:
                    change.update({"generation": self._midi_hotplug_generation, "observedMonotonicNs": monotonic_ns()})
                self._midi_hotplug_changes = (self._midi_hotplug_changes + changes)[-128:]
            self._midi_devices = devices
            self._last_midi_scan = monotonic()
            for device in devices:
                self.midi_identities.record(str(device.get("id", "")), device)
            return [dict(device) for device in devices]

    def midi_hotplug_status(self, after: int = 0) -> dict[str, Any]:
        if not hasattr(self, "_midi_scan_lock"):
            self._midi_scan_lock = RLock()
        if not hasattr(self, "_midi_hotplug_generation"):
            self._midi_hotplug_generation = 0
        if not hasattr(self, "_midi_hotplug_changes"):
            self._midi_hotplug_changes = []
        with self._midi_scan_lock:
            return {"generation": self._midi_hotplug_generation,
                    "changes": [dict(item) for item in self._midi_hotplug_changes if int(item["generation"]) > int(after)],
                    "scanIntervalMs": 2000,
                    "automaticActivation": False,
                    "physicalOutputsArmed": False}

    def midi_devices(self, *, rescan: bool = False) -> dict[str, Any]:
        if rescan or monotonic() - self._last_midi_scan > 2.0:
            try:
                self._refresh_midi_devices(rebind=True)
            except RuntimeError:
                self._midi_devices = []
        bindings = (self.state.snapshot().get("midi") or {}).get("bindings") or {}
        devices = []
        for raw in self._midi_devices:
            device = dict(raw)
            device["attached"] = bool(device.get("attached"))
            devices.append(device)
        return {
            "available": self.native.available,
            "devices": devices,
            "bindings": dict(bindings),
            "hotplug": self.midi_hotplug_status(),
            "backend": "linux-raw" if any(str(d.get("id", "")).startswith("linux-raw-") for d in devices) else "native-abstraction",
        }

    def midi_mapping_status(self) -> dict[str, Any]:
        status=self.midi_mapping.status();native={"available":False,"authority":"bridge","bindings":0,"submitted":0,"rejected":0}
        if getattr(self.native,"supports_native_midi_performance",False):
            try:
                raw=self.native.native_midi_mapping_status();native={"available":True,"authority":"native-core","bindings":int(raw.get("bindings","0")),"submitted":int(raw.get("submitted","0")),"rejected":int(raw.get("rejected","0"))}
            except RuntimeError:pass
        status["nativeExecution"]=native;return status

    def midi_mapping_targets(self) -> dict[str, Any]:
        return self.midi_mapping.targets()

    def midi_mapping_learn(self, data: dict[str, Any]) -> dict[str, Any]:
        target=str(data.get("targetId",""));resource=str(data.get("resourceId",""))
        if target in {"sample.trigger","loop.toggle","loop.clear"} and resource:
            try:self.sampler_preloads.preload(self.daw_sessions.load(),resource,looped=target!="sample.trigger",
                choke_group=int(data.get("chokeGroup",0)),crossfade_frames=int(data.get("crossfadeFrames",256)))
            except (RuntimeError,ValueError,OSError):pass
        return self.midi_mapping.begin(data)

    def midi_mapping_cancel(self) -> dict[str, Any]:
        return self.midi_mapping.cancel()

    def midi_mapping_delete(self, mapping_id: str) -> dict[str, Any]:
        result=self.midi_mapping.delete(mapping_id)
        if mapping_id in self._native_midi_mapping_ids:
            try:self.native.remove_native_midi_mapping(mapping_id)
            except RuntimeError:pass
            self._native_midi_mapping_ids.discard(mapping_id)
        return result

    def _native_midi_mapping(self, mapping: dict[str, Any], *, preload: bool = False) -> dict[str, Any] | None:
        target=dict(mapping.get("target") or {});target_id=str(target.get("targetId",""))
        if target_id in {"filter.cutoff","filter.resonance","track.volume","track.pan","transport.play","transport.stop","master.tempo"}:
            return mapping
        if target_id not in {"sample.trigger","loop.toggle","loop.clear"} or not getattr(self.native,"supports_sampler_voice_engine",False):return None
        resource=str(target.get("resourceId",""));looped=target_id!="sample.trigger"
        if not resource:return None
        asset=self.sampler_preloads.resolve(resource,looped)
        if preload:
            try:asset=self.sampler_preloads.preload(self.daw_sessions.load(),resource,looped=looped,choke_group=int(target.get("chokeGroup",0)),crossfade_frames=int(target.get("crossfadeFrames",256)))
            except (RuntimeError,ValueError,OSError):return None
        if asset is None:return None
        compiled=deepcopy(mapping);compiled_target=dict(compiled.get("target") or {});compiled_target["resourceId"]=asset["nativeResourceId"];compiled["target"]=compiled_target
        return compiled

    def _sync_native_midi_mappings(self) -> None:
        self._native_midi_mapping_ids.clear()
        if not getattr(self.native,"supports_native_midi_performance",False):return
        self.native.clear_native_midi_mappings();transport=self.state.snapshot().get("transport") or {}
        self.native.configure_native_midi_master(float(transport.get("bpm",120.0)))
        for mapping in self.midi_mapping.status().get("mappings",[]):
            compiled=self._native_midi_mapping(mapping,preload=True)
            if not mapping.get("enabled",True) or compiled is None:continue
            try:self.native.upsert_native_midi_mapping(compiled);self._native_midi_mapping_ids.add(str(mapping.get("mappingId","")))
            except (RuntimeError,ValueError):continue

    def _execute_midi_mapping_actions(self, actions: list[dict[str, Any]],native_executed_ids: set[str] | None = None) -> None:
        for action in actions:
            target=str(action.get("targetId",""));value=float(action.get("value",0));show_ns=max(0,int(float(action.get("showTimeSeconds",0))*1_000_000_000))
            if native_executed_ids is not None and str(action.get("mappingId","")) in native_executed_ids:
                # Native Core already executed the action. Mirror only the small
                # document-facing transport projection; never resubmit it.
                if target=="transport.play" and value>0:self.state.transport("play")
                elif target=="transport.stop" and value>0:self.state.transport("stop")
                elif target=="master.tempo":self.state.patch_show({"bpm":value})
                continue
            if target=="transport.play" and value>0:self.state.transport("play")
            elif target=="transport.stop" and value>0:self.state.transport("stop")
            elif target=="master.tempo":self.state.patch_show({"bpm":value})
            elif target=="sample.trigger" and value>0:
                try:self.daw_producer.start_clip(self.daw_sessions.load(),str(action.get("resourceId","")),loop=False)
                except (RuntimeError,ValueError):pass
            elif target=="loop.toggle":
                try:self.daw_producer.start_clip(self.daw_sessions.load(),str(action.get("resourceId","")),loop=True) if value>0 else self.daw_producer.stop()
                except (RuntimeError,ValueError):pass
            elif target=="loop.clear" and value>0:self.daw_producer.stop()
            elif "parameterId" in action and self.native.available:
                try:self.native.submit_mapped_automation(target,int(action["parameterId"]),show_ns,value)
                except RuntimeError:pass

    def ingest_midi(self, player_id: str, data: dict[str, Any], expected_revision: int | None = None, expected_resource_revision: int | None = None) -> dict[str, Any]:
        result=self.state.ingest_midi(player_id,data,expected_revision,expected_resource_revision);transport=result.get("transport") or {};self.midi_mapping.observe(data,transport);self._execute_midi_mapping_actions(self.midi_mapping.drain_due(float(transport.get("seconds",0))));return self.state.snapshot()

    def bind_midi_device(
        self,
        device_id: str,
        player_id: str,
        expected_revision: int | None,
        expected_resource_revision: int | None,
        command_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        # Persist desired ownership even when the endpoint is currently absent.
        # Hot-plug discovery will satisfy the binding when the device appears.
        state, deduplicated = self.mutate(
            command_id,
            lambda: self.state.bind_midi_device(device_id, player_id, expected_revision, expected_resource_revision),
        )
        if self.native.available:
            try:
                self._refresh_midi_devices(rebind=False)
                if any(device.get("id") == device_id and device.get("connected") for device in self._midi_devices):
                    selected = next(device for device in self._midi_devices if device.get("id") == device_id and device.get("connected"))
                    self.midi_identities.record(device_id, selected)
                    self.native.attach_midi_input(device_id, player_id)
                self._refresh_midi_devices(rebind=True)
            except (RuntimeError, ValueError):
                pass
        return state, deduplicated

    def unbind_midi_device(
        self,
        device_id: str,
        expected_revision: int | None,
        expected_resource_revision: int | None,
        command_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        state, deduplicated = self.mutate(
            command_id,
            lambda: self.state.unbind_midi_device(device_id, expected_revision, expected_resource_revision),
        )
        if self.native.available:
            try:
                self.native.detach_midi_input(device_id)
                self._refresh_midi_devices(rebind=True)
            except RuntimeError:
                pass
        return state, deduplicated

    def pump_midi_once(self, max_events: int = 64) -> int:
        if not self.native.available:
            return 0
        events = self.native.poll_midi_inputs(max_events=max_events)
        if not events:
            return 0
        with self._mutation_lock:
            before_revision = self.state.revision
            native_executed_ids=set(self._native_midi_mapping_ids)
            for event in events:
                player_id = str(event.get("playerId", "")).strip()
                if not player_id:
                    continue
                midi_data={
                        "deviceId": event.get("deviceId", "native"),
                        "status": event.get("status", 0),
                        "data1": event.get("data1", 0),
                        "data2": event.get("data2", 0),
                        "showTimeSeconds": max(0, int(event.get("showTimeNs", 0))) / 1_000_000_000.0,
                    }
                self.state.ingest_midi(
                    player_id,
                    midi_data,
                )
                observed=self.midi_mapping.observe(midi_data,self.state.snapshot().get("transport") or {})
                learned=observed.get("learnedMapping")
                compiled=self._native_midi_mapping(learned) if learned and getattr(self.native,"supports_native_midi_performance",False) else None
                if compiled is not None:
                    try:self.native.upsert_native_midi_mapping(compiled);self._native_midi_mapping_ids.add(str(learned.get("mappingId","")))
                    except (RuntimeError,ValueError):pass
            transport=self.state.snapshot().get("transport") or {};self._execute_midi_mapping_actions(self.midi_mapping.drain_due(float(transport.get("seconds",0))),native_executed_ids)
            if self.state.revision != before_revision:
                self._after_mutation(self.state.snapshot(), sync_native=False)
        return len(events)

    def _midi_loop(self) -> None:
        while not self._stop.wait(0.01):
            if not self.native.available:
                self._stop.wait(0.25)
                continue
            if not self.replication.is_primary():
                self._stop.wait(0.05)
                continue
            try:
                if monotonic() - self._last_midi_scan > 2.0:
                    self._refresh_midi_devices(rebind=True)
                captured = self.pump_midi_once(128)
                transport=self.state.snapshot().get("transport") or {};due=self.midi_mapping.drain_due(float(transport.get("seconds",0)))
                if due:
                    with self._mutation_lock:
                        before_revision=self.state.revision;self._execute_midi_mapping_actions(due,set(self._native_midi_mapping_ids))
                        if self.state.revision!=before_revision:self._after_mutation(self.state.snapshot())
                if captured == 0 and not any(d.get("attached") for d in self._midi_devices):
                    self._stop.wait(0.04)
            except (RuntimeError, ValueError, KeyError):
                self._stop.wait(0.1)

    def schedule_lighting(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self.replication.is_primary():
            raise RuntimeError("standby node cannot schedule authoritative lighting events")
        if not self.native.available:
            raise RuntimeError("native lighting scheduler unavailable")
        semantic: dict[str, Any] | None = None
        if "fixtureId" in data or "parameter" in data or "normalizedValue" in data:
            mapping = self._active_venue_mapping("lighting.primary")
            if not mapping:
                raise ValueError("semantic lighting intent requires an active lighting.primary venue mapping")
            semantic = resolve_lighting_fixture_intent(
                mapping,
                str(data.get("fixtureId", "")),
                str(data.get("parameter", "")),
                data.get("normalizedValue"),
            )
            universe = int(semantic["universe"])
            channel = int(semantic["channel"])
            value = int(semantic["value"])
        else:
            try:
                universe = int(data.get("universe", 0))
                channel = int(data["channel"])
                value = int(data["value"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("lighting schedule requires universe, channel and value") from exc
        if not (0 <= universe < 16 and 1 <= channel <= 512 and 0 <= value <= 255):
            raise ValueError("lighting event outside supported universe/channel/value range")

        try:
            now_show_ns = int(float(self.native.time_state().get("seconds", "0")) * 1_000_000_000)
        except (RuntimeError, ValueError):
            now_show_ns = int(float(self.state.snapshot()["transport"]["seconds"]) * 1_000_000_000)
        target_ns = int(data.get("targetShowTimeNs", now_show_ns + 100_000_000))
        timing = {
            "nowNs": now_show_ns,
            "targetNs": target_ns,
            "fixedLatencyNs": int(data.get("fixedLatencyNs", 20_000_000)),
            "jitterNs": int(data.get("jitterNs", 5_000_000)),
            "minimumLookaheadNs": int(data.get("minimumLookaheadNs", 20_000_000)),
            "timestamped": False,
        }
        plan = self.timing_plan(timing)
        with self._mutation_lock:
            event_id = self._next_lighting_event_id
            self._next_lighting_event_id += 1
            queued = self.native.schedule_lighting(event_id, int(plan["dispatchNs"]), universe, channel, value)
        result = {
            "eventId": event_id,
            "universe": universe,
            "channel": channel,
            "value": value,
            "targetShowTimeNs": target_ns,
            "dispatchShowTimeNs": int(plan["dispatchNs"]),
            "reserveNs": int(plan["reserveNs"]),
            "late": bool(plan["late"]),
            "queued": int(queued.get("queued", "0")),
            "physicalOutput": self._lighting_armed,
            "transportAuthority": "stageforge",
        }
        if semantic:
            result["semantic"] = semantic
            result["venuePatchApplied"] = True
        return result

    def lighting_universe_info(self, universe: int) -> dict[str, Any]:
        if not self.native.available:
            raise RuntimeError("native lighting scheduler unavailable")
        if not 0 <= int(universe) < 16:
            raise ValueError("universe must be 0..15 in the starter")
        network = self._mapped_lighting_execution() or ((self.state.snapshot().get("lighting") or {}).get("network") or {})
        protocol = str(network.get("protocol", "artnet")).lower()
        raw = self.native.sacn_frame_info(int(universe)) if protocol == "sacn" else self.native.artnet_frame_info(int(universe))
        result = {
            "universe": int(raw.get("universe", universe)),
            "channel1": int(raw.get("channel1", "0")),
            "protocol": protocol,
            "physicalOutput": self._lighting_armed,
        }
        if protocol == "sacn":
            result["sacnBytes"] = int(raw.get("bytes", "0"))
            result["networkUniverse"] = int(raw.get("networkUniverse", universe + int(network.get("universeBase", 1))))
        else:
            result["artnetBytes"] = int(raw.get("bytes", "0"))
        return result

    def _lighting_loop(self) -> None:
        while not self._stop.wait(0.01):
            if not self.native.available:
                self._stop.wait(0.25)
                continue
            try:
                show_ns = int(float(self.native.time_state().get("seconds", "0")) * 1_000_000_000)
                self.native.drain_lighting(show_ns)
            except (RuntimeError, ValueError):
                self._stop.wait(0.05)

    def _execution_replication_telemetry(self) -> dict[str, Any]:
        """Small signed execution summary carried beside replicated show state.

        The control snapshot remains the source of truth. These fields describe
        what the current authority actually executed so a standby can measure
        continuity without comparing machine-local monotonic clock epochs.
        """
        outputs: list[dict[str, Any]] = []
        inputs: list[int] = []
        if self.native.available:
            try:
                for item in self.audio_outputs_status().get("outputs", []):
                    if not item.get("active"):
                        continue
                    outputs.append({
                        "slot": int(item.get("slot", 0)),
                        "purpose": str(item.get("purpose", "aux")),
                        "lastBlockEndShowNs": int(item.get("lastBlockEndShowNs", 0)),
                        "lastRenderShowNs": int(item.get("lastRenderShowNs", 0)),
                        "lastWriteNsLocal": int(item.get("lastWriteNs", 0)),
                        "framesWritten": int(item.get("framesWritten", 0)),
                    })
            except (RuntimeError, TypeError, ValueError):
                outputs = []
            try:
                for item in self.audio_inputs_status().get("inputs", []):
                    if item.get("active"):
                        inputs.append(int(item.get("slot", 0)))
            except (RuntimeError, TypeError, ValueError):
                inputs = []
        transport = self.state.snapshot().get("transport") or {}
        return {
            "capturedAtMonotonicNsLocal": monotonic_ns(),
            "showTimeNs": int(float(transport.get("seconds", 0.0)) * 1_000_000_000),
            "transportRunning": bool(transport.get("running", False)),
            "audioOutputs": outputs,
            "activeAudioInputSlots": inputs,
        }

    def _replication_auth_configured(self) -> bool:
        return self._replication_keyring.configured or bool(self._replication_secret)

    def _replication_auth_snapshot(self):
        if self._replication_keyring.configured:
            return self._replication_keyring.snapshot()
        return RotatingHmacKeyring(None, self._replication_secret).snapshot()

    def _replication_loop(self) -> None:
        last_revision = -1
        last_sent_at = 0.0
        while not self._stop.wait(self._replication_interval):
            if not self._has_authority() or not self._peer.configured:
                continue
            if not self._replication_auth_configured():
                # Automatic venue-LAN replication is never sent unsigned.
                continue
            now = monotonic()
            snapshot = self.state.replication_snapshot()
            revision = int(snapshot.get("revision", 0))
            if revision == last_revision and now - last_sent_at < self._replication_heartbeat:
                continue
            try:
                auth = self._replication_auth_snapshot()
                envelope = self.replication.export(
                    snapshot, auth.active_secret, self._execution_replication_telemetry(),
                    key_id=auth.active_key_id if auth.keyring_mode else None,
                )
            except (RuntimeError, PermissionError):
                continue
            result = self._peer.push(envelope)
            if result.ok:
                last_revision = revision
                last_sent_at = now

    def _witness_loop(self) -> None:
        interval = max(0.1, self._witness.ttl_ms / 3000.0)
        while not self._stop.is_set():
            self._witness_tick()
            self._stop.wait(interval)

    def _witness_tick(self) -> None:
        # Keep renewal and role changes ordered with irreversible handoff release.
        with self._mutation_lock:
            status = self._witness.acquire()
            valid = bool(status.get("leaseValid"))
            if self.replication.is_primary():
                if valid:
                    self.replication.adopt_epoch(int(status.get("leaseEpoch", 1)))
                else:
                    # In witness mode an unfenced primary is not allowed to keep
                    # executing. Demote and silence physical authorities first.
                    self._fence_physical_outputs()
                    self.replication.set_role("standby")
            elif self._auto_failover:
                failover = self.failover_status()
                if failover.get("heartbeatEligible") and valid:
                    decision_at_promotion = self.handoff_decision_status()
                    self.replication.promote_with_epoch(int(status.get("leaseEpoch", 1)))
                    self._record_failover_continuity(failover.get("replicaAgeMs"))
                    self._last_failover_continuity["handoffDecisionAtPromotion"] = decision_at_promotion
                    # Promotion never restores physical outputs automatically.
                    if self.native.available:
                        try:
                            self._refresh_midi_devices(rebind=True)
                        except RuntimeError:
                            pass

    def witness_status(self) -> dict[str, Any]:
        return {**self._witness.status(), "autoFailover": self._auto_failover, "authoritative": self._has_authority()}

    def planned_handoff_status(self) -> dict[str, Any]:
        native = None
        if self.native.available:
            try: native = self.native.planned_handoff_status()
            except RuntimeError: pass
        return {"active": self._planned_handoff is not None, "transaction": dict(self._planned_handoff or {}),
                "native": native, "physicalOutputsAutoArmed": False}

    def planned_handoff_offer(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self.replication.is_primary():
            raise PermissionError("only the primary may create a planned handoff offer")
        if not self._replication_auth_configured():
            raise RuntimeError("planned handoff requires authenticated replication")
        status = self.replication.status()
        target_node = str(data.get("targetNodeId", "")).strip()
        pre_roll_ms = max(100, min(int(data.get("preRollMs", 2000)), 60000))
        now_show_ns = int(float((self.state.snapshot().get("transport") or {}).get("seconds", 0.0)) * 1_000_000_000)
        target_show_ns = max(int(data.get("targetShowNs", 0)), now_show_ns + pre_roll_ms * 1_000_000)
        transaction_id = int(data.get("transactionId", 0))
        auth = self._replication_auth_snapshot()
        offer = make_offer(transaction_id=transaction_id, source_node_id=str(status["nodeId"]), target_node_id=target_node,
                           source_epoch=int(status["epoch"]), target_epoch=int(status["epoch"])+1,
                           target_show_ns=target_show_ns, allow_degraded_program=bool(data.get("allowDegradedProgram", False)),
                           secret=auth.active_secret, key_id=auth.active_key_id if auth.keyring_mode else None)
        self._planned_handoff = {"state": "offered", **{k: offer[k] for k in offer if not k.startswith("hmac")}}
        return offer

    def planned_handoff_accept(self, offer: dict[str, Any]) -> dict[str, Any]:
        status = self.replication.status()
        if status["role"] != "standby":
            raise PermissionError("planned handoff offers are accepted by standby nodes only")
        if not self._replication_auth_configured():
            raise RuntimeError("planned handoff requires authenticated replication")
        auth = self._replication_auth_snapshot()
        ok, reason = verify_offer(offer, keyset=auth, expected_target_node_id=str(status["nodeId"]))
        if not ok: raise PermissionError(reason)
        source = status.get("sourceNodeId")
        if source and source != offer["sourceNodeId"]:
            raise RuntimeError("planned handoff source does not match replicated authority")
        if not self.native.available:
            raise RuntimeError("native planned handoff execution is unavailable")
        self.native.planned_handoff_prepare(int(offer["transactionId"]), int(offer["sourceEpoch"]), int(offer["targetEpoch"]),
                                            int(offer["targetShowNs"]), allow_degraded_program=bool(offer["allowDegradedProgram"]))
        self._planned_handoff = {"state": "preparing", **{k: offer[k] for k in offer if k not in {"hmacSha256"}}}
        return self.planned_handoff_status()

    def planned_handoff_acknowledge(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._planned_handoff or self._planned_handoff.get("state") != "preparing":
            raise RuntimeError("no planned handoff is awaiting pre-roll acknowledgement")
        if data.get("acknowledgePreRoll") is not True:
            raise ValueError("planned handoff requires acknowledgePreRoll=true")
        decision = self.handoff_decision_status()
        ready = bool(decision.get("readyForProgramTakeover"))
        if not ready and not bool(self._planned_handoff.get("allowDegradedProgram")):
            raise RuntimeError("program pre-roll is not execution-ready")
        self.native.planned_handoff_acknowledge(int(self._planned_handoff["transactionId"]), program_ready=ready)
        self._planned_handoff["state"] = "target-ready"
        self._planned_handoff["programReady"] = ready
        auth = self._replication_auth_snapshot()
        receipt_key_id = self._planned_handoff.get("keyId")
        receipt_secret = auth.resolve(receipt_key_id)
        receipt = make_ready_receipt(offer=self._planned_handoff, program_ready=ready,
                                     secret=receipt_secret, key_id=receipt_key_id if auth.keyring_mode else None)
        delivery = self._peer.deliver_planned_handoff_ready(receipt)
        self._planned_handoff["readinessDelivery"] = {
            "delivered": delivery.ok,
            "httpStatus": delivery.status or None,
            "error": delivery.error,
        }
        return self.planned_handoff_status()

    def planned_handoff_peer_ready(
        self, receipt: dict[str, Any],
        authorization_hook: Callable[[bool, str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if (not self.replication.is_primary() or not self._planned_handoff or
                self._planned_handoff.get("state") not in {"offered", "target-ready"}):
            raise RuntimeError("primary has no matching planned handoff offer")
        if not self._replication_auth_configured():
            raise RuntimeError("planned handoff requires authenticated replication")
        auth = self._replication_auth_snapshot()
        ok, reason = verify_ready_receipt(
            receipt,
            keyset=auth,
            expected_source_node_id=str(self.replication.status()["nodeId"]),
            offer=self._planned_handoff,
        )
        if not ok:
            if authorization_hook is not None:
                authorization_hook(False, "planned-handoff-authentication-failed", {})
            raise PermissionError(reason)
        if authorization_hook is not None:
            authorization_hook(True, "planned-handoff-hmac-verified", {
                "actor": str(receipt.get("targetNodeId", ""))[:64] or None,
                "keyId": str(receipt.get("keyId", ""))[:64] or None,
            })
        if self._planned_handoff.get("state") == "target-ready":
            if bool(self._planned_handoff.get("programReady")) != receipt["programReady"]:
                raise RuntimeError("conflicting planned handoff readiness receipt")
            return self.planned_handoff_status()
        self._planned_handoff["state"] = "target-ready"
        self._planned_handoff["programReady"] = receipt["programReady"]
        self._planned_handoff["readyReceiptDigest"] = str(receipt["digestSha256"])
        return self.planned_handoff_status()

    def planned_handoff_commit(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._planned_handoff or self._planned_handoff.get("state") != "target-ready":
            raise RuntimeError("planned handoff target is not ready")
        if data.get("acknowledgeAuthorityChange") is not True:
            raise ValueError("planned handoff commit requires acknowledgeAuthorityChange=true")
        if not self._witness.configured:
            raise RuntimeError("planned handoff commit requires witness quorum fencing")
        lease = self._witness.acquire()
        if not lease.get("leaseValid") or int(lease.get("leaseEpoch", 0)) != int(self._planned_handoff["targetEpoch"]):
            raise RuntimeError("standby did not acquire the exact planned witness epoch")
        now_show_ns = int(float((self.state.snapshot().get("transport") or {}).get("seconds", 0.0)) * 1_000_000_000)
        self.native.planned_handoff_commit(int(self._planned_handoff["transactionId"]), int(self._planned_handoff["sourceEpoch"]),
                                           int(lease["leaseEpoch"]), now_show_ns)
        self.replication.promote_with_epoch(int(lease["leaseEpoch"]))
        self._planned_handoff["state"] = "committed"
        self._planned_handoff["physicalOutputsArmed"] = False
        return self.planned_handoff_status()

    def planned_handoff_release_authority(self, data: dict[str, Any]) -> dict[str, Any]:
        """Self-fence the old primary and atomically transfer its witness lease."""
        with self._mutation_lock:
            return self._planned_handoff_release_authority_locked(data)

    def _planned_handoff_release_authority_locked(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self.replication.is_primary():
            raise PermissionError("only the old primary may release planned-handoff authority")
        if not self._planned_handoff or self._planned_handoff.get("state") != "target-ready":
            raise RuntimeError("planned handoff target is not ready")
        if data.get("acknowledgeAuthorityRelease") is not True:
            raise ValueError("planned handoff release requires acknowledgeAuthorityRelease=true")
        if not self._witness.configured:
            raise RuntimeError("planned handoff release requires witness quorum fencing")
        now_show_ns = int(float((self.state.snapshot().get("transport") or {}).get("seconds", 0.0)) * 1_000_000_000)
        if now_show_ns < int(self._planned_handoff["targetShowNs"]):
            raise RuntimeError("planned handoff Show-Time boundary has not arrived")

        # Demote before making an irreversible quorum request. A partial
        # transfer cannot safely be rolled back, so every attempted release
        # leaves the old primary fenced even when quorum is not reached.
        self._fence_physical_outputs()
        self.replication.set_role("standby")
        self._planned_handoff["state"] = "authority-release-pending"
        transfer = self._witness.transfer(
            target_node_id=str(self._planned_handoff["targetNodeId"]),
            source_epoch=int(self._planned_handoff["sourceEpoch"]),
            target_epoch=int(self._planned_handoff["targetEpoch"]),
            transaction_id=int(self._planned_handoff["transactionId"]),
        )
        self._planned_handoff["authorityTransfer"] = transfer
        self._planned_handoff["state"] = (
            "authority-released" if transfer.get("transferred") else "release-indeterminate"
        )
        self._planned_handoff["physicalOutputsArmed"] = False
        return self.planned_handoff_status()

    def planned_handoff_abort(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self._planned_handoff: raise RuntimeError("no planned handoff is active")
        if data.get("acknowledgeAbort") is not True: raise ValueError("planned handoff abort requires acknowledgeAbort=true")
        if self.native.available: self.native.planned_handoff_abort(int(self._planned_handoff["transactionId"]))
        self._planned_handoff["state"] = "aborted"
        return self.planned_handoff_status()

    def replication_status(self) -> dict[str, Any]:
        replica = self.replication.status()
        return {
            "node": replica,
            "transport": self._peer.status(),
            "authenticated": self._replication_auth_configured(),
            "keyringMode": self._replication_keyring.keyring_mode,
            "automaticPushEnabled": bool(self._peer.configured and self._replication_auth_configured()),
            "heartbeatSeconds": self._replication_heartbeat,
            "witness": self.witness_status(),
        }

    def _record_failover_continuity(self, replica_age_ms: int | None) -> None:
        snapshot = self.state.snapshot()
        transport = snapshot.get("transport") or {}
        bridge_seconds = float(transport.get("seconds", 0.0))
        native_seconds: float | None = None
        timeline_error_ms: float | None = None
        if self.native.available:
            try:
                native_seconds = float(self.native.time_state().get("seconds", bridge_seconds))
                timeline_error_ms = abs(native_seconds - bridge_seconds) * 1000.0
            except (RuntimeError, TypeError, ValueError):
                pass
        if timeline_error_ms is None:
            grade = "unmeasured"
        elif timeline_error_ms <= 5.0:
            grade = "sample-window"
        elif timeline_error_ms <= 20.0:
            grade = "tight"
        elif timeline_error_ms <= 100.0:
            grade = "degraded"
        else:
            grade = "discontinuous"

        source_outputs = self._replicated_execution_telemetry.get("audioOutputs") or []
        source_last_program_ns = max(
            [int(item.get("lastBlockEndShowNs", 0)) for item in source_outputs if isinstance(item, dict)] or [0]
        )
        source_inputs = self._replicated_execution_telemetry.get("activeAudioInputSlots") or []
        if source_inputs:
            handoff_mode = "live-input-state-warm"
            deterministic_prebuffer_eligible = False
        elif source_outputs and bool(transport.get("running", False)):
            handoff_mode = "deterministic-prebuffer-eligible"
            deterministic_prebuffer_eligible = True
        else:
            handoff_mode = "state-warm"
            deterministic_prebuffer_eligible = False

        handoff_target_show_ns = max(int(bridge_seconds * 1_000_000_000), source_last_program_ns)
        handoff_adjustment_ms = 0.0
        if source_last_program_ns > 0 and native_seconds is not None:
            native_show_ns = int(native_seconds * 1_000_000_000)
            handoff_adjustment_ms = max(0.0, (handoff_target_show_ns - native_show_ns) / 1_000_000.0)
        # The target is diagnostic/prebuffer intent only. The authoritative
        # transport is never advanced merely because an output buffer rendered
        # ahead of it. Deterministic sources may later pre-render toward this
        # target; live inputs require a duplicated feed.

        self._promotion_at = monotonic()
        self._promotion_at_ns = monotonic_ns()
        self._last_failover_continuity = {
            "measured": timeline_error_ms is not None,
            "replicaAgeMs": replica_age_ms,
            "transportRunning": bool(transport.get("running", False)),
            "bridgeShowSeconds": round(bridge_seconds, 6),
            "nativeShowSeconds": round(native_seconds, 6) if native_seconds is not None else None,
            "timelineErrorMs": round(timeline_error_ms, 3) if timeline_error_ms is not None else None,
            "grade": grade,
            "firstAudioArmAfterMs": None,
            "firstAudioWriteAfterMs": None,
            "maxObservedOutputGapMs": None,
            "audioResumptionGrade": "not-rearmed",
            "activeAudioOutputSlots": [],
            "firstLightingArmAfterMs": None,
            "sourceLastProgramShowNs": source_last_program_ns or None,
            "newFirstProgramShowNs": None,
            "crossNodeProgramGapMs": None,
            "crossNodeProgramOverlapMs": None,
            "crossNodeProgramGrade": "unmeasured",
            "handoffMode": handoff_mode,
            "deterministicPrebufferEligible": deterministic_prebuffer_eligible,
            "prebufferReady": False,
            "handoffTargetShowNs": handoff_target_show_ns or None,
            "handoffAdjustmentMs": round(handoff_adjustment_ms, 3),
            "physicalOutputsAutoArmed": False,
        }

    def _refresh_failover_audio_telemetry(self) -> None:
        if self._promotion_at_ns is None:
            return
        try:
            outputs = self.audio_outputs_status().get("outputs", [])
        except (RuntimeError, ValueError, TypeError):
            return
        active = [item for item in outputs if item.get("active")]
        self._last_failover_continuity["activeAudioOutputSlots"] = [int(item.get("slot", 0)) for item in active]
        first_writes = [int(item.get("firstWriteNs", 0)) for item in active if int(item.get("firstWriteNs", 0)) >= self._promotion_at_ns]
        if first_writes:
            elapsed_ms = max(0.0, (min(first_writes) - self._promotion_at_ns) / 1_000_000.0)
            self._last_failover_continuity["firstAudioWriteAfterMs"] = round(elapsed_ms, 3)
            if elapsed_ms <= 20.0:
                grade = "tight"
            elif elapsed_ms <= 100.0:
                grade = "short-gap"
            elif elapsed_ms <= 500.0:
                grade = "degraded"
            else:
                grade = "long-gap"
            self._last_failover_continuity["audioResumptionGrade"] = grade

        first_program_positions = [int(item.get("firstRenderShowNs", 0)) for item in active if int(item.get("firstRenderShowNs", 0)) > 0]
        source_last = int(self._last_failover_continuity.get("sourceLastProgramShowNs") or 0)
        if source_last > 0 and first_program_positions:
            new_first = min(first_program_positions)
            delta_ms = (new_first - source_last) / 1_000_000.0
            gap_ms = max(0.0, delta_ms)
            overlap_ms = max(0.0, -delta_ms)
            self._last_failover_continuity["newFirstProgramShowNs"] = new_first
            self._last_failover_continuity["crossNodeProgramGapMs"] = round(gap_ms, 3)
            self._last_failover_continuity["crossNodeProgramOverlapMs"] = round(overlap_ms, 3)
            magnitude = max(gap_ms, overlap_ms)
            if magnitude <= 5.0:
                program_grade = "sample-window"
            elif magnitude <= 20.0:
                program_grade = "tight"
            elif magnitude <= 100.0:
                program_grade = "degraded"
            else:
                program_grade = "discontinuous"
            self._last_failover_continuity["crossNodeProgramGrade"] = program_grade
        gaps = [float(item.get("maxExcessGapMs", 0.0)) for item in active]
        if gaps:
            self._last_failover_continuity["maxObservedOutputGapMs"] = round(max(gaps), 3)

    def failover_continuity_status(self) -> dict[str, Any]:
        self._refresh_failover_audio_telemetry()
        return dict(self._last_failover_continuity)

    def _mark_post_promotion_output(self, kind: str) -> None:
        if self._promotion_at is None:
            return
        elapsed_ms = int(max(0.0, monotonic() - self._promotion_at) * 1000)
        key = "firstAudioArmAfterMs" if kind == "audio" else "firstLightingArmAfterMs"
        if self._last_failover_continuity.get(key) is None:
            self._last_failover_continuity[key] = elapsed_ms

    def handoff_execution_status(self) -> dict[str, Any]:
        return self.handoff_execution.snapshot()

    def report_shadow_prebuffer(self, data: dict[str, Any]) -> dict[str, Any]:
        if self.replication.is_primary():
            raise RuntimeError("shadow prebuffer execution reports are accepted on standby nodes only")
        source_id = str(data.get("sourceId", "")).strip()
        if not source_id:
            raise ValueError("sourceId is required")
        if "bufferedUntilShowNs" not in data:
            raise ValueError("bufferedUntilShowNs is required")
        start_show_ns = data.get("startShowNs")
        rendered_frames = int(data.get("renderedFrames", 0))
        self.handoff_execution.report_shadow(
            source_id,
            buffered_until_show_ns=int(data["bufferedUntilShowNs"]),
            content_hash=str(data.get("contentHash", "")),
            healthy=bool(data.get("healthy", True)),
            start_show_ns=None if start_show_ns is None else int(start_show_ns),
            rendered_frames=rendered_frames,
        )
        if self.native.available:
            try:
                runtime_status = self.native.runtime_show_status()
                if start_show_ns is not None and rendered_frames > 0:
                    self.native.shadow_block(
                        source_id,
                        int(runtime_status.get("generation", "0")),
                        int(self.state.revision),
                        str(data.get("contentHash", "")),
                        int(start_show_ns),
                        int(data["bufferedUntilShowNs"]),
                        rendered_frames,
                        bool(data.get("healthy", True)),
                    )
                else:
                    self.native.shadow_report(
                        source_id,
                        int(runtime_status.get("generation", "0")),
                        int(self.state.revision),
                        str(data.get("contentHash", "")),
                        int(data["bufferedUntilShowNs"]),
                        False,
                    )
            except RuntimeError:
                pass
        return self.handoff_decision_status()

    def report_live_feed_ready(self, data: dict[str, Any]) -> dict[str, Any]:
        if self.replication.is_primary():
            raise RuntimeError("duplicated live-feed reports are accepted on standby nodes only")
        if "slot" not in data:
            raise ValueError("slot is required")
        source_id = str(data.get("sourceId", "")).strip()
        if not source_id:
            raise ValueError("sourceId is required")
        self.handoff_execution.report_live(
            int(data["slot"]),
            source_id=source_id,
            healthy=bool(data.get("healthy", True)),
            latency_ms=float(data.get("latencyMs", 0.0)),
            first_show_ns=data.get("firstShowNs"),
            last_show_ns=data.get("lastShowNs"),
            frames=int(data.get("frames", 0)),
            sequence=data.get("sequence"),
        )
        return self.handoff_decision_status()

    def handoff_decision_status(self) -> dict[str, Any]:
        replica = self.replication.status()
        telemetry = self._replicated_execution_telemetry if isinstance(self._replicated_execution_telemetry, dict) else {}
        source_outputs = telemetry.get("audioOutputs") or []
        source_inputs = tuple(
            int(v) for v in (telemetry.get("activeAudioInputSlots") or [])
            if isinstance(v, int) or str(v).isdigit()
        )
        source_last = max(
            [int(item.get("lastBlockEndShowNs", 0)) for item in source_outputs if isinstance(item, dict)] or [0]
        )
        target_ns = max(int(telemetry.get("showTimeNs", 0) or 0), source_last)
        local_show_ns = None
        if self.native.available:
            try:
                local_show_ns = int(float(self.native.time_state().get("seconds", "0")) * 1_000_000_000)
            except (RuntimeError, TypeError, ValueError):
                pass
        snapshot = self.state.snapshot()
        handoff = snapshot.get("handoff") or {}
        decision = evaluate_handoff(
            HandoffFacts(
                role=str(replica.get("role", "standby")),
                replica_age_ms=replica.get("replicaAgeMs"),
                source_node_id=replica.get("sourceNodeId"),
                source_program_cursor_ns=source_last,
                handoff_target_show_ns=target_ns,
                local_show_ns=local_show_ns,
                active_live_input_slots=source_inputs,
                source_outputs_active=bool(source_outputs),
                transport_running=bool(telemetry.get("transportRunning", False)),
            ),
            policy=handoff.get("policy"),
            live_inputs=handoff.get("liveInputs"),
            deterministic_sources=handoff.get("deterministicSources"),
            execution=self.handoff_execution.snapshot(),
        )
        native_shadow_plan = None
        if self.native.available and target_ns:
            try:
                required_ms = float((handoff.get("policy") or {}).get("requiredPrebufferMs", 250.0))
                native_shadow_plan = self.native.shadow_plan(target_ns, max(0, int(required_ms * 1_000_000)))
            except (RuntimeError, TypeError, ValueError):
                native_shadow_plan = None
        return {
            **decision,
            "replicaAgeMs": replica.get("replicaAgeMs"),
            "sourceNodeId": replica.get("sourceNodeId"),
            "sourceProgramCursorNs": source_last or None,
            "handoffTargetShowNs": target_ns or None,
            "localShowNs": local_show_ns,
            "activeLiveInputSlots": list(source_inputs),
            "nativeShadowPlan": native_shadow_plan,
            "physicalOutputsAutoArm": False,
        }

    def handoff_readiness_status(self) -> dict[str, Any]:
        # Compatibility surface retained for readiness-v1 clients. New clients
        # should use /api/v1/handoff/decision for the richer deterministic
        # policy result.
        decision = self.handoff_decision_status()
        return {
            "mode": decision["mode"],
            "replicaAgeMs": decision.get("replicaAgeMs"),
            "sourceNodeId": decision.get("sourceNodeId"),
            "sourceProgramCursorNs": decision.get("sourceProgramCursorNs"),
            "handoffTargetShowNs": decision.get("handoffTargetShowNs"),
            "localShowNs": decision.get("localShowNs"),
            "localLagMs": decision.get("localLagMs"),
            "activeLiveInputSlots": decision.get("activeLiveInputSlots", []),
            "deterministicPrebufferEligible": decision.get("deterministicPrebufferEligible", False),
            "prebufferReady": decision.get("prebufferReady", False),
            "physicalOutputsAutoArm": False,
            "readyForAuthorityTransfer": decision.get("readyForAuthorityTransfer", False),
            "reasons": list(decision.get("reasons", [])),
        }

    def failover_status(self) -> dict[str, Any]:
        replica = self.replication.status()
        age = replica.get("replicaAgeMs")
        heartbeat_eligible = bool(age is not None and age >= self._failover_promote_ms)
        witness = self._witness.status()
        if replica["role"] == "primary":
            state = "primary" if self._has_authority() else "lease-lost"
            safe = False
        elif age is None:
            state, safe = "waiting", False
        elif age >= self._failover_promote_ms:
            state = "eligible"
            safe = (not self._witness.configured) or bool(witness.get("leaseValid"))
        elif age >= self._failover_suspect_ms:
            state, safe = "suspect", False
        else:
            state, safe = "healthy", False
        handoff_decision = self.handoff_decision_status() if replica["role"] == "standby" else None
        return {
            "state": state,
            "safeToPromote": safe,
            "safeToPromoteAuthority": safe,
            "programLogicReady": bool(handoff_decision and handoff_decision.get("programLogicReady")),
            "programExecutionReady": bool(handoff_decision and handoff_decision.get("executionReady")),
            "programContinuityReady": bool(handoff_decision and handoff_decision.get("readyForProgramTakeover")),
            "handoffDecision": handoff_decision,
            "heartbeatEligible": heartbeat_eligible,
            "electionMode": "witness-quorum-auto" if self._witness.configured and self._auto_failover else ("witness-quorum-manual" if self._witness.configured else "manual-after-failure-detection"),
            "suspectAfterMs": self._failover_suspect_ms,
            "promotionEligibleAfterMs": self._failover_promote_ms,
            "replicaAgeMs": age,
            "sourceNodeId": replica.get("sourceNodeId"),
            "lastAppliedRevision": replica.get("lastAppliedRevision", 0),
            "witness": witness,
            "splitBrainProtection": "witness lease fences authority; physical outputs remain disarmed after promotion",
            "continuity": self.failover_continuity_status(),
        }

    def promote_after_failure(self, data: dict[str, Any]) -> dict[str, Any]:
        if self._witness.status().get("acquisitionSuspended"):
            raise RuntimeError("handoff acquisition fence requires recovery before promotion")
        if self.replication.is_primary():
            return {"promoted": False, "reason": "already primary", "node": self.node_status(), "failover": self.failover_status()}
        if data.get("acknowledgeAuthorityChange") is not True:
            raise ValueError("failover promotion requires acknowledgeAuthorityChange=true")
        status = self.failover_status()
        decision_at_promotion = status.get("handoffDecision") or self.handoff_decision_status()
        replica_age_ms = status.get("replicaAgeMs")
        if not status.get("heartbeatEligible"):
            raise RuntimeError("standby is not yet promotion-eligible; primary heartbeat has not exceeded the failover threshold")
        if self._witness.configured:
            lease = self._witness.acquire()
            if not lease.get("leaseValid"):
                raise RuntimeError("standby could not acquire witness quorum lease")
            self.replication.promote_with_epoch(int(lease.get("leaseEpoch", 1)))
            self._record_failover_continuity(replica_age_ms)
            self._last_failover_continuity["handoffDecisionAtPromotion"] = decision_at_promotion
            if self.native.available:
                try:
                    self._refresh_midi_devices(rebind=True)
                except RuntimeError:
                    pass
            node = self.node_status()
        else:
            # set_node_role() records continuity for the standby→primary edge.
            node = self.set_node_role({"role": "primary", "acknowledgeAuthorityChange": True, "forceAuthorityOverride": True})
        return {"promoted": True, "node": node, "failover": self.failover_status()}

    def recover_fenced_node(self,data:dict[str,Any])->dict[str,Any]:
        if data.get("acknowledgeStandbyRecovery") is not True:raise ValueError("fenced-node recovery requires acknowledgeStandbyRecovery=true")
        recovery_id=str(data.get("recoveryId","")).strip()
        if not recovery_id:raise ValueError("fenced-node recovery requires recoveryId")
        with self._mutation_lock:
            self._fence_physical_outputs();self.replication.set_role("standby")
            if hasattr(self, "venue_authority_leases"):
                self.venue_authority_leases.clear()
            result=self._witness.recover(recovery_id)
            return {**result,"nodeRole":self.replication.role,"physicalAuthority":False,"physicalOutputsArmed":False}

    def node_status(self) -> dict[str, Any]:
        status = self.replication.status()
        status.update({
            "replicationAuthenticated": self._replication_auth_configured(),
            "replicationKeyringMode": self._replication_keyring.keyring_mode,
            "physicalAuthority": self._has_authority(),
            "witness": self.witness_status(),
            "audio": self.audio_stream_status(),
            "audioOutputs": self.audio_outputs_status(),
            "audioInput": self.audio_input_status(),
            "lightingArmed": self._lighting_armed,
            "replicationTransport": self._peer.status(),
        })
        return status

    def set_node_role(self, data: dict[str, Any]) -> dict[str, Any]:
        role = str(data.get("role", "")).strip().lower()
        if role == "primary" and self._witness.status().get("acquisitionSuspended"):
            raise RuntimeError("handoff acquisition fence requires recovery before promotion")
        if data.get("acknowledgeAuthorityChange") is not True:
            raise ValueError("role change requires acknowledgeAuthorityChange=true")
        previous = self.replication.role
        decision_at_promotion = self.handoff_decision_status() if previous == "standby" and role == "primary" else None
        if role == previous and (role != "primary" or self._has_authority()):
            return self.node_status()
        if role == "standby":
            self._fence_physical_outputs()
            self.replication.set_role("standby")
            if hasattr(self, "venue_authority_leases"):
                self.venue_authority_leases.clear()
            self._last_reconciliation_state = None
            return self.node_status()
        if role != "primary":
            raise ValueError("node role must be primary or standby")
        if previous == "standby" and data.get("forceAuthorityOverride") is not True and not self.failover_status().get("heartbeatEligible"):
            raise RuntimeError("standby is not promotion-eligible; wait for heartbeat failure or use an explicit administrative override")
        if self._witness.configured and data.get("forceAuthorityOverride") is not True:
            lease = self._witness.acquire()
            if not lease.get("leaseValid"):
                raise RuntimeError("cannot promote without a witness quorum lease")
            self.replication.promote_with_epoch(int(lease.get("leaseEpoch", 1)))
        else:
            self.replication.set_role("primary")
        if previous == "standby":
            self._record_failover_continuity(self.failover_status().get("replicaAgeMs"))
            if decision_at_promotion is not None:
                self._last_failover_continuity["handoffDecisionAtPromotion"] = decision_at_promotion
        if self.native.available:
            try:
                self._refresh_midi_devices(rebind=True)
            except RuntimeError:
                pass
        # Physical audio and lighting never auto-arm on promotion.
        return self.node_status()

    def export_replica(self) -> dict[str, Any]:
        auth = self._replication_auth_snapshot()
        return self.replication.export(
            self.state.replication_snapshot(),
            auth.active_secret,
            self._execution_replication_telemetry(),
            key_id=auth.active_key_id if auth.keyring_mode else None,
        )

    def apply_replica(
        self, envelope: dict[str, Any],
        authorization_hook: Callable[[bool, str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        auth = self._replication_auth_snapshot()
        ok, reason = verify_envelope(envelope, keyset=auth)
        if not ok:
            if authorization_hook is not None:
                authorization_hook(False, "replication-authentication-failed", {})
            raise ValueError(reason)
        if authorization_hook is not None:
            authorization_hook(True, "replication-hmac-verified", {
                "actor": str(envelope.get("sourceNodeId", ""))[:64] or None,
                "keyId": str(envelope.get("keyId", ""))[:64] or None,
            })
        prior_replica = self.replication.status()
        decision = self.replication.can_apply(envelope)
        if not decision.accepted:
            raise ValueError(decision.reason)
        authority_changed = (
            str(prior_replica.get("sourceNodeId") or "") != str(envelope.get("sourceNodeId") or "")
            or int(prior_replica.get("lastAppliedEpoch", 0) or 0) != int(envelope.get("epoch", 0) or 0)
        )
        if authority_changed:
            self.handoff_execution.clear()
        execution_telemetry = envelope.get("executionTelemetry") or {}
        if not isinstance(execution_telemetry, dict):
            execution_telemetry = {}
        with self._mutation_lock:
            state = self.state.apply_replica_snapshot(envelope["snapshot"])
            self.repository.save_snapshot(self.state.persistence_snapshot())
            self._last_persisted_event_id = max(
                [int(event.get("eventId", 0)) for event in state.get("events", [])] or [0]
            )
            if self.native.available:
                try:
                    self.native.arm_lighting_network(False)
                    self.native.deactivate_all_audio_inputs()
                    self.native.deactivate_all_audio_outputs()
                    self.native.sync_state(state)
                    self._configure_lighting_from_state()
                    self._refresh_audio_devices(reselect=True)
                    self._refresh_midi_devices(rebind=False)
                except RuntimeError:
                    pass
            self._lighting_armed = False
            self._replicated_execution_telemetry = dict(execution_telemetry)
            self.replication.mark_applied(envelope)
        return {
            "accepted": True,
            "revision": state["revision"],
            "node": self.node_status(),
        }

    def health(self) -> dict[str, Any]:
        snapshot = self.state.snapshot()
        ledger = self.repository.verify_ledger()
        return {
            "ok": bool(ledger.get("ok")),
            "service": "stageforge-dev",
            "revision": snapshot["revision"],
            "ledger": ledger,
            "adapters": {
                "healthy": sum(1 for a in self.adapters.snapshot() if a["healthy"]),
                "total": len(self.adapters.snapshot()),
            },
            "audio": {
                "desiredDeviceId": (snapshot.get("audio") or {}).get("deviceId", "null-audio"),
                "devices": len(self._audio_devices),
                "stream": self.audio_stream_status(),
                "outputs": self.audio_outputs_status(),
                "input": self.audio_input_status(),
            },
            "lighting": self.lighting_network_status(),
            "midi": {
                "received": (snapshot.get("midi") or {}).get("received", 0),
                "bindings": len((snapshot.get("midi") or {}).get("bindings") or {}),
                "devices": len(self._midi_devices),
            },
            "native": self.native.status(),
            "node": self.node_status(),
        }

    def clock_status(self) -> dict[str, Any]:
        if self.native.available:
            try:
                status = self.native.clock_status()
                return {
                    "available": True,
                    "source": status.get("source", "local"),
                    "state": status.get("state", "free"),
                    "offsetNs": int(status.get("offsetNs", "0")),
                    "driftPpm": float(status.get("driftPpm", "0")),
                    "sourceAgeNs": int(status.get("ageNs", "0")),
                    "projectedNs": int(status.get("projectedNs", "0")),
                    "observations": int(status.get("observations", "0")),
                    "transportAuthority": "stageforge",
                }
            except (RuntimeError, ValueError):
                pass
        now = monotonic_ns()
        return {
            "available": False,
            "source": "local",
            "state": "free",
            "offsetNs": 0,
            "driftPpm": 0.0,
            "sourceAgeNs": 0,
            "projectedNs": now,
            "observations": 0,
            "transportAuthority": "stageforge",
        }

    def set_clock_source(self, source: str) -> dict[str, Any]:
        if not self.native.available:
            raise RuntimeError("native clock discipline unavailable")
        self.native.set_clock_source(source)
        return self.clock_status()

    def observe_clock(self, data: dict[str, Any]) -> dict[str, Any]:
        if not self.native.available:
            raise RuntimeError("native clock discipline unavailable")
        try:
            local_ns = int(data["localNs"])
            source_ns = int(data["sourceNs"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("clock observation requires integer localNs and sourceNs") from exc
        self.native.observe_clock(local_ns, source_ns)
        status = self.native.clock_status(local_ns)
        return {
            "available": True,
            "source": status.get("source", "external"),
            "state": status.get("state", "locked"),
            "offsetNs": int(status.get("offsetNs", "0")),
            "driftPpm": float(status.get("driftPpm", "0")),
            "sourceAgeNs": int(status.get("ageNs", "0")),
            "projectedNs": int(status.get("projectedNs", "0")),
            "observations": int(status.get("observations", "0")),
            "transportAuthority": "stageforge",
        }

    def transport_discipline_status(self) -> dict[str, Any]:
        if not getattr(self.native,"supports_transport_discipline",False):return {"available":False,"physicalOutputsArmed":False}
        raw=self.native.transport_discipline_status();return {"available":True,"configured":raw.get("configured")=="1","state":raw.get("state","free"),
            "sourceId":int(raw.get("sourceId","0")),"authorityEpoch":int(raw.get("authorityEpoch","0")),"lastSequence":int(raw.get("lastSequence","0")),
            "phaseErrorNs":int(raw.get("phaseErrorNs","0")),"driftPpm":float(raw.get("driftPpm","0")),"correctionPpm":float(raw.get("correctionPpm","0")),
            "appliedRate":float(raw.get("appliedRate","1")),"sourceAgeNs":int(raw.get("sourceAgeNs","0")),"observations":int(raw.get("observations","0")),
            "rejected":int(raw.get("rejected","0")),"holdoverEntries":int(raw.get("holdoverEntries","0")),"physicalOutputsArmed":False}

    def configure_transport_discipline(self,data:dict[str,Any])->dict[str,Any]:
        if not self.replication.is_primary():raise RuntimeError("standby node cannot own transport discipline")
        epoch=max(1,int(self.replication.status().get("epoch",0)));source=str(data.get("sourceId","")).strip()
        if not source:raise ValueError("transport discipline sourceId is required")
        self.native.configure_transport_discipline(self.native._stable_id("clock-source:"+source),epoch,holdover_ns=int(data.get("holdoverNs",1_000_000_000)),max_slew_ppm=float(data.get("maxSlewPpm",500)),recovery_window_ns=int(data.get("recoveryWindowNs",5_000_000_000)))
        return self.transport_discipline_status()

    def observe_transport_discipline(self,data:dict[str,Any])->dict[str,Any]:
        if not self.replication.is_primary():raise RuntimeError("standby node cannot submit transport discipline evidence")
        epoch=max(1,int(self.replication.status().get("epoch",0)))
        self.native.observe_transport_discipline(int(data.get("sequence",0)),epoch,int(data.get("localNs",0)),int(data.get("sourceNs",0)),int(data.get("localShowNs",0)),int(data.get("sourceShowNs",0)))
        return self.transport_discipline_status()

    def midi_clock_status(self)->dict[str,Any]:
        if not getattr(self.native,"supports_midi_clock",False):return {"available":False,"physicalOutputsArmed":False}
        raw=self.native.midi_clock_status();return {"available":True,"configured":raw.get("configured")=="1","running":raw.get("running")=="1","ppqn":24,
            "authorityEpoch":int(raw.get("authorityEpoch","0")),"bpm":float(raw.get("bpm","120")),"emitted":int(raw.get("emitted","0")),"received":int(raw.get("received","0")),
            "rejected":int(raw.get("rejected","0")),"lastSequence":int(raw.get("lastSequence","0")),"lastPulseShowNs":int(raw.get("lastPulseShowNs","0")),
            "maximumJitterNs":int(raw.get("maximumJitterNs","0")),"physicalOutputsArmed":False}

    def midi_clock_control(self,data:dict[str,Any])->dict[str,Any]:
        if not self.replication.is_primary():raise RuntimeError("standby node cannot own MIDI Clock")
        epoch=max(1,int(self.replication.status().get("epoch",0)));action=str(data.get("action",""));show_ns=int(data.get("showTimeNs",0))
        if action=="configure":self.native.configure_midi_clock(epoch,float(data.get("bpm",120)),show_ns)
        elif action=="start":self.native.start_midi_clock(epoch,show_ns)
        elif action=="stop":self.native.stop_midi_clock(epoch,show_ns)
        elif action=="tempo":self.native.set_midi_clock_tempo(epoch,float(data.get("bpm",120)),show_ns)
        elif action=="observe":self.native.observe_midi_clock(epoch,int(data.get("sequence",0)),show_ns)
        elif action=="emit":self.native.emit_midi_clock(show_ns,int(data.get("maximum",4096)))
        else:raise ValueError("unsupported MIDI Clock action")
        return self.midi_clock_status()

    def timing_plan(self, data: dict[str, Any]) -> dict[str, Any]:
        plan = local_timing_plan(data)
        if self.native.available:
            try:
                native = self.native.timing_plan(
                    plan["nowNs"], plan["targetNs"],
                    plan["profile"]["fixedLatencyNs"], plan["profile"]["jitterNs"],
                    plan["profile"]["minimumLookaheadNs"], plan["timestamped"],
                )
                plan["dispatchNs"] = int(native["dispatchNs"])
                plan["reserveNs"] = int(native["reserveNs"])
                plan["late"] = native["late"] == "1"
                plan["source"] = "native"
                return plan
            except (RuntimeError, KeyError, ValueError):
                pass
        plan["source"] = "bridge"
        return plan

    def stage_template_list(self): return {"templates": self.stage_templates.list(), "physicalOutputsArmed": False}
    def stage_template_get(self, template_id): return self.stage_templates.get(template_id)
    def stage_template_create(self, body): return self.stage_templates.create(body)
    def stage_template_validate(self, template_id): return self.stage_templates.validate_saved(template_id)
    def stage_template_publish(self, template_id): return self.stage_templates.publish(template_id)

    def close(self) -> None:
        self._stop.set()
        playback_error = None
        try:
            self.daw_producer.stop()
        except RuntimeError as exc:
            playback_error = exc
        try:
            self.streaming_voice_producer.close()
        except RuntimeError as exc:
            if playback_error is None:playback_error=exc
        try:
            self.daw_capture.abort()
        except RuntimeError as exc:
            if playback_error is None:
                playback_error = exc
        if self._midi_thread and self._midi_thread.is_alive():
            self._midi_thread.join(timeout=1.0)
        if self._audio_thread and self._audio_thread.is_alive():
            self._audio_thread.join(timeout=1.0)
        if self._lighting_thread and self._lighting_thread.is_alive():
            self._lighting_thread.join(timeout=1.0)
        if self._replication_thread and self._replication_thread.is_alive():
            self._replication_thread.join(timeout=1.0)
        if self._witness_thread and self._witness_thread.is_alive():
            self._witness_thread.join(timeout=1.0)
        if self._adaptation_thread and self._adaptation_thread.is_alive():
            self._adaptation_thread.join(timeout=1.0)
        if self._reconciliation_thread and self._reconciliation_thread.is_alive():
            self._reconciliation_thread.join(timeout=1.0)
        if self.native.available:
            try:
                self.native.arm_lighting_network(False)
                self.native.deactivate_all_audio_inputs()
                self.native.deactivate_all_audio_outputs()
            except RuntimeError:
                pass
        self.native.close()
        if playback_error is not None:
            raise playback_error
