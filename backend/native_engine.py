from __future__ import annotations

import os
import subprocess
import secrets
import hashlib
import json
import struct
from pathlib import Path
from threading import RLock
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MONITOR_FIELDS = ("master", "self", "vocals", "band", "click", "talkback", "ambient", "muted")


def _candidate_paths() -> list[Path]:
    executable = "stagemesh_engine.exe" if os.name == "nt" else "stagemesh_engine"
    paths: list[Path] = []
    configured = os.environ.get("STAGEMESH_NATIVE_ENGINE", "").strip()
    if configured.lower() in {"off", "disabled", "none", "0"}:
        return []
    if configured:
        paths.append(Path(configured).expanduser())
    paths.extend([
        ROOT / "build" / "native" / executable,
        ROOT / "build" / executable,
        ROOT / "out" / "build" / "native" / executable,
    ])
    return paths


def parse_response(line: str) -> tuple[bool, dict[str, str]]:
    parts = line.strip().split()
    if not parts:
        raise RuntimeError("native engine returned an empty response")
    ok = parts[0] == "OK"
    if not ok and parts[0] != "ERR":
        raise RuntimeError(f"invalid native engine response: {line!r}")
    values: dict[str, str] = {}
    for token in parts[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        values[key] = value.replace("_", " ") if key == "message" else value
    return ok, values


class NativeEngineClient:
    """Small stdio IPC bridge to the dependency-free native engine.

    This transport is intentionally temporary and local. It proves the semantic
    boundary without committing UPP to Python, sockets, protobuf, or any other
    heavyweight runtime. A future binary IPC transport can keep the methods and
    API contract while replacing only this class.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._process: subprocess.Popen[str] | None = None
        self._path: Path | None = None
        self._last_error: str | None = None
        self._hello: dict[str, str] = {}
        self._parameter_bindings: set[tuple[int, int]] = set()
        self._ipc_token = secrets.token_hex(32)
        self._start()

    def _start(self) -> None:
        if os.environ.get("STAGEMESH_NATIVE_ENGINE", "").strip().lower() in {"off", "disabled", "none", "0"}:
            self._last_error = "native engine disabled by STAGEMESH_NATIVE_ENGINE"
            return
        path = next((candidate.resolve() for candidate in _candidate_paths() if candidate.is_file()), None)
        if path is None:
            self._last_error = "native engine binary not found; build with CMake or set STAGEMESH_NATIVE_ENGINE"
            return
        try:
            env = os.environ.copy()
            env["STAGEFORGE_IPC_TOKEN"] = self._ipc_token
            process = subprocess.Popen(
                [str(path), "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )
            self._process = process
            self._path = path
            self.request(f"AUTH {self._ipc_token}")
            self._hello = self.request("HELLO")
        except (OSError, RuntimeError) as exc:
            self._last_error = str(exc)
            self.close()

    @property
    def available(self) -> bool:
        return bool(self._process and self._process.poll() is None)

    @property
    def supports_native_midi_performance(self) -> bool:
        return self.available and self._hello.get("nativeMidiPerformance") == "1"

    @property
    def supports_sampler_voice_engine(self) -> bool:
        return self.available and self._hello.get("samplerVoiceEngine") == "1"

    @property
    def supports_transport_discipline(self) -> bool:
        return self.available and self._hello.get("transportDiscipline") == "1"

    @property
    def supports_midi_clock(self) -> bool:
        return self.available and self._hello.get("midiClock24Ppqn") == "1"

    def request(self, command: str) -> dict[str, str]:
        if "\n" in command or "\r" in command:
            raise ValueError("native engine commands must be one line")
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None or process.stdout is None:
                raise RuntimeError(self._last_error or "native engine unavailable")
            try:
                process.stdin.write(command + "\n")
                process.stdin.flush()
                line = process.stdout.readline()
            except (BrokenPipeError, OSError) as exc:
                self._last_error = f"native IPC failed: {exc}"
                raise RuntimeError(self._last_error) from exc
            ok, values = parse_response(line)
            if not ok:
                message = values.get("message", "native engine error")
                code = values.get("code", "error")
                raise RuntimeError(f"{code}: {message}")
            return values

    @staticmethod
    def _stable_id(value: str) -> int:
        # FNV-1a 64-bit, stable across processes/platforms and easy to reproduce
        # in non-Python UPP implementations. Zero is reserved by Core.
        h = 14695981039346656037
        for byte in value.encode("utf-8"):
            h ^= byte
            h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
        return h or 1

    def daw_playback_status(self) -> dict[str, str]:
        return self.request("DAW_PLAYBACK_STATUS")

    def daw_playback_start(self) -> dict[str, str]:
        return self.request("DAW_PLAYBACK_START")

    def daw_playback_stop(self) -> dict[str, str]:
        return self.request("DAW_PLAYBACK_STOP")

    def daw_playback_seek(self, frame: int) -> dict[str, str]:
        return self.request(f"DAW_PLAYBACK_SEEK {max(0,int(frame))}")

    def daw_playback_loop(self, begin: int, end: int) -> dict[str, str]:
        return self.request(f"DAW_PLAYBACK_LOOP {max(0,int(begin))} {max(0,int(end))}")

    def daw_playback_loop_clear(self) -> dict[str, str]:
        return self.request("DAW_PLAYBACK_LOOP_CLEAR")

    def daw_playback_pcm(self, generation: int, start: int, left: list[float], right: list[float]) -> dict[str, str]:
        if len(left)!=len(right) or not left or len(left)>256:raise ValueError("PCM block must contain 1..256 stereo frames")
        interleaved=[sample for pair in zip(left,right) for sample in pair]
        payload=struct.pack("<"+"f"*len(interleaved),*interleaved).hex()
        return self.request(f"DAW_PLAYBACK_PCM {int(generation)} {int(start)} {len(left)} {payload}")

    def daw_record_status(self, track: int) -> dict[str, str]:
        return self.request(f"DAW_RECORD_STATUS {int(track)}")

    def daw_record_arm(self, track: int, acknowledged: bool) -> dict[str, str]:
        return self.request(f"DAW_RECORD_ARM {int(track)} {1 if acknowledged else 0}")

    def daw_record_disarm(self, track: int) -> dict[str, str]:
        return self.request(f"DAW_RECORD_DISARM {int(track)}")

    def daw_record_pop(self, track: int) -> dict[str, Any]:
        response=self.request(f"DAW_RECORD_POP {int(track)}");frames=int(response["frames"]);raw=bytes.fromhex(response["pcm"])
        values=struct.unpack("<"+"f"*(frames*2),raw)
        return {**response,"frames":frames,"generation":int(response.get("generation","0")),"sequence":int(response["sequence"]),"showFrame":int(response["showFrame"]),"left":list(values[0::2]),"right":list(values[1::2])}

    def plugin_delay_graph_prepare(self,generation:int,activation_show_ns:int,latencies:list[int])->dict[str,str]:
        if not latencies or len(latencies)>16:raise ValueError("delay graph requires 1..16 paths")
        return self.request("PDC_PREPARE "+" ".join(map(str,[generation,activation_show_ns,len(latencies),*latencies])))
    def plugin_delay_graph_activate(self,show_ns:int)->dict[str,str]:return self.request(f"PDC_ACTIVATE {int(show_ns)}")
    def plugin_delay_graph_status(self)->dict[str,str]:return self.request("PDC_STATUS")
    def effect_delay_transaction_prepare(self,generation:int,activation_show_ns:int,latencies:list[int],changes:list[dict])->dict[str,str]:
        values=[generation,activation_show_ns,len(latencies),*latencies,len(changes)]
        for change in changes:values.extend((change["outputSlot"],change["effectId"],1 if change["bypassed"] else 0))
        return self.request("FXPDC_PREPARE "+" ".join(map(str,values)))
    def effect_delay_transaction_rollback(self,generation:int,activation_show_ns:int)->dict[str,str]:return self.request(f"FXPDC_ROLLBACK {int(generation)} {int(activation_show_ns)}")
    def realtime_audit_status(self,slot:int=0)->dict[str,str]:return self.request(f"RT_AUDIT_STATUS {int(slot)}")
    def ingress_audit_status(self,domain:str="MIDI")->dict[str,str]:
        normalized=str(domain).upper()
        if normalized=="MIDI":return self.request("INGRESS_AUDIT_STATUS MIDI")
        if normalized=="CAPTURE":raise ValueError("capture ingress audit requires a slot")
        raise ValueError("unsupported ingress audit domain")
    def capture_ingress_audit_status(self,slot:int=0)->dict[str,str]:
        return self.request(f"INGRESS_AUDIT_STATUS CAPTURE {self._audio_input_slot(slot)}")
    def lighting_ingress_audit_status(self)->dict[str,str]:return self.request("INGRESS_AUDIT_STATUS LIGHTING")

    def _bind_parameter_once(self, target_id: int, parameter_id: int, command: str) -> None:
        key = (int(target_id), int(parameter_id))
        if key in self._parameter_bindings:
            return
        self.request(command)
        self._parameter_bindings.add(key)

    def compile_runtime_state(self, snapshot: dict[str, Any]) -> None:
        if not self.available:
            return
        revision = max(0, int(snapshot.get("revision", 0)))
        structural = {
            "players": snapshot.get("players") or [],
            "audio": snapshot.get("audio") or {},
            "lighting": snapshot.get("lighting") or {},
        }
        digest = hashlib.blake2b(
            json.dumps(structural, sort_keys=True, separators=(",", ":")).encode("utf-8"), digest_size=8
        ).digest()
        content_hash = int.from_bytes(digest, "big")
        self.request(f"SHOW_COMPILE_BEGIN {revision} {content_hash}")

        for player in (snapshot.get("players") or [])[:64]:
            player_id = str(player.get("id", "")).strip()
            if not player_id:
                continue
            role_id = self._stable_id(f"player:{player_id}")
            self.request(f"SHOW_COMPILE_ROLE {role_id} 0")
            monitor = player.get("monitor") or {}
            target = self._stable_id(f"monitor:{player_id}")
            master = float(monitor.get("master", 72.0))
            self.request(f"SHOW_COMPILE_PARAM {target} 1 0 100 {master:.6f} 2 2")
            token = player_id if not any(ch.isspace() for ch in player_id) else ""
            if token:
                self._bind_parameter_once(target, 1, f"PARAM_BIND_MONITOR_MASTER {target} 1 {token} 0 100 {master:.6f}")
                channel_ids = {"self": 2, "vocals": 3, "band": 4, "click": 5, "talkback": 6, "ambient": 7}
                for channel, parameter_id in channel_ids.items():
                    value = float(monitor.get(channel, 0.0))
                    self.request(f"SHOW_COMPILE_PARAM {target} {parameter_id} 0 100 {value:.6f} 2 2")
                    self._bind_parameter_once(
                        target, parameter_id,
                        f"PARAM_BIND_MONITOR_CHANNEL {target} {parameter_id} {token} {channel} 0 100 {value:.6f}",
                    )

        audio = snapshot.get("audio") or {}
        outputs = audio.get("outputs") or []
        for raw in outputs[:16]:
            try:
                graph_output = max(0, min(15, int(raw.get("graphOutput", 0))))
                master = float(raw.get("master", 1.0))
            except (TypeError, ValueError):
                continue
            target = 1000 + graph_output
            self.request(f"SHOW_COMPILE_PARAM {target} 1 0 4 {master:.6f} 1 1")
            self._bind_parameter_once(target, 1, f"PARAM_BIND_AUDIO_MASTER {target} 1 {graph_output} 0 4 {master:.6f}")

        for raw in (audio.get("inputs") or [])[:16]:
            try:
                slot = int(raw.get("slot", 0))
                route = raw.get("route") or {}
                output = int(route.get("output", 0))
            except (TypeError, ValueError):
                continue
            from_id = self._stable_id(f"audio-input:{slot}")
            to_id = self._stable_id(f"audio-output:{output}")
            self.request(f"SHOW_COMPILE_ROUTE {from_id} {to_id} 2 0")

        show_ns = max(0, int(float((snapshot.get("transport") or {}).get("seconds", 0.0)) * 1_000_000_000))
        self.request(f"SHOW_COMPILE_COMMIT {show_ns}")
        # Compatibility request is executed by the Core timeline owner and also
        # runs the owner tick, making the generation swap deterministic before
        # sync_state returns without creating a second timeline consumer.
        self.request(f"EVENT_DRAIN {show_ns}")
        generation = int(self.runtime_show_status().get("generation", "0"))
        handoff = snapshot.get("handoff") or {}
        for source in (handoff.get("deterministicSources") or [])[:64]:
            source_id = str(source.get("id", "")).strip()
            if not source_id:
                continue
            numeric_id = self._stable_id(f"shadow:{source_id}")
            content = str(source.get("contentHash", ""))
            hash_id = self._stable_id(f"content:{content}") if content else self._stable_id(f"source:{source_id}")
            self.request(
                f"SHADOW_DECLARE {numeric_id} {revision} {hash_id} {generation} "
                f"{1 if source.get('required', True) else 0} "
                f"{1 if source.get('shadowCapable') else 0} "
                f"{1 if source.get('localAssetReady') else 0}"
            )

    def sync_state(self, snapshot: dict[str, Any]) -> None:
        if not self.available:
            return
        # Apply native Core control state as one revisioned transaction. The
        # bridge remains authoritative during migration, but transport + monitor
        # state no longer arrive as a partially visible sequence of commands.
        revision = max(0, int(snapshot.get("revision", 0)))
        transport = snapshot.get("transport") or {}
        self.request(f"CORE_SYNC_BEGIN {revision}")
        try:
            self.request(
                "CORE_SYNC_TRANSPORT "
                f"{float(transport.get('bpm', 120.0)):.6f} "
                f"{float(transport.get('seconds', 0.0)):.6f} "
                f"{1 if transport.get('running') else 0}"
            )
            for player in snapshot.get("players") or []:
                player_id = str(player.get("id", "")).strip()
                if not player_id or any(ch.isspace() for ch in player_id):
                    continue
                monitor = player.get("monitor") or {}
                values = [
                    float(monitor.get("master", 72.0)),
                    float(monitor.get("self", 76.0)),
                    float(monitor.get("vocals", 58.0)),
                    float(monitor.get("band", 62.0)),
                    float(monitor.get("click", 38.0)),
                    float(monitor.get("talkback", 45.0)),
                    float(monitor.get("ambient", 28.0)),
                    1 if monitor.get("muted") else 0,
                ]
                self.request(
                    f"CORE_SYNC_MONITOR {player_id} "
                    + " ".join(str(value) for value in values)
                )
            self.request("CORE_SYNC_COMMIT")
        except Exception:
            try:
                self.request("CORE_SYNC_ABORT")
            except Exception:
                pass
            raise

        audio = snapshot.get("audio") or {}
        outputs = audio.get("outputs")
        if not isinstance(outputs, list):
            outputs = [{"slot": 0, "deviceId": audio.get("deviceId", "null-audio"), "graphOutput": 0, "playerId": "", "master": 1.0, "limiterCeilingDb": audio.get("limiterCeilingDb", -1.0)}]
        for raw_output in outputs[:4]:
            if not isinstance(raw_output, dict):
                continue
            try:
                slot = max(0, min(3, int(raw_output.get("slot", 0))))
            except (TypeError, ValueError):
                continue
            device_id = str(raw_output.get("deviceId", "")).strip()
            if device_id and not any(ch.isspace() for ch in device_id):
                try:
                    self.select_audio_device(device_id, slot)
                except (RuntimeError, ValueError):
                    pass
            graph_output = int(raw_output.get("graphOutput", 0))
            player_id = str(raw_output.get("playerId", "")).strip()
            if player_id and not any(ch.isspace() for ch in player_id):
                try:
                    graph_output = int(self.bind_audio_output_player(player_id, slot).get("output", graph_output))
                except (RuntimeError, ValueError):
                    pass
            try:
                self.set_audio_output(graph_output, float(raw_output.get("master", 1.0)), float(raw_output.get("limiterCeilingDb", -1.0)))
            except (RuntimeError, TypeError, ValueError):
                pass
        inputs = audio.get("inputs")
        if not isinstance(inputs, list):
            inputs = [{"slot": 0, "deviceId": audio.get("inputDeviceId", ""), "playerId": audio.get("inputPlayerId", ""), "route": audio.get("inputRoute") or {}}]
        for raw_input in inputs[:4]:
            if not isinstance(raw_input, dict):
                continue
            try:
                slot = max(0, min(3, int(raw_input.get("slot", 0))))
            except (TypeError, ValueError):
                continue
            input_device = str(raw_input.get("deviceId", "")).strip()
            if input_device and not any(ch.isspace() for ch in input_device):
                try:
                    self.select_audio_input(input_device, slot)
                except (RuntimeError, ValueError):
                    pass
            player_id = str(raw_input.get("playerId", "")).strip()
            if player_id and not any(ch.isspace() for ch in player_id):
                try:
                    self.bind_audio_input_player(player_id, slot)
                except (RuntimeError, ValueError):
                    pass
            route = raw_input.get("route") or {}
            try:
                self.route_audio_input(int(route.get("output", 0)), float(route.get("gain", 0.0)), slot)
            except (RuntimeError, TypeError, ValueError):
                pass

        try:
            self.compile_runtime_state(snapshot)
        except (RuntimeError, TypeError, ValueError):
            # The bridge can continue operating while a native runtime compiler
            # problem is surfaced through native health; do not partially mutate
            # the validated Python show state on compiler failure.
            pass

    def parameter_status(self) -> dict[str, str]:
        return self.request("PARAM_STATUS")

    def runtime_show_status(self) -> dict[str, str]:
        return self.request("SHOW_RUNTIME_STATUS")

    def routing_status(self) -> dict[str, str]:
        return self.request("ROUTE_STATUS")

    def journal_status(self) -> dict[str, str]:
        return self.request("JOURNAL_STATUS")

    def next_journal_record(self) -> dict[str, str]:
        return self.request("JOURNAL_NEXT")

    def shadow_declare(self, source_id: str, show_revision: int, content_hash: str, generation: int, *, required: bool, capable: bool, asset_ready: bool) -> dict[str, str]:
        numeric_id = self._stable_id(f"shadow:{source_id}")
        hash_id = self._stable_id(f"content:{content_hash}") if content_hash else self._stable_id(f"source:{source_id}")
        return self.request(f"SHADOW_DECLARE {numeric_id} {int(show_revision)} {hash_id} {int(generation)} {1 if required else 0} {1 if capable else 0} {1 if asset_ready else 0}")

    def shadow_report(self, source_id: str, generation: int, show_revision: int, content_hash: str, buffered_until_show_ns: int, healthy: bool) -> dict[str, str]:
        numeric_id = self._stable_id(f"shadow:{source_id}")
        hash_id = self._stable_id(f"content:{content_hash}") if content_hash else self._stable_id(f"source:{source_id}")
        return self.request(f"SHADOW_REPORT {numeric_id} {int(generation)} {int(show_revision)} {hash_id} {int(buffered_until_show_ns)} {1 if healthy else 0}")

    def shadow_block(self, source_id: str, generation: int, show_revision: int, content_hash: str, start_show_ns: int, end_show_ns: int, frames: int, healthy: bool = True) -> dict[str, str]:
        numeric_id = self._stable_id(f"shadow:{source_id}")
        hash_id = self._stable_id(f"content:{content_hash}") if content_hash else self._stable_id(f"source:{source_id}")
        return self.request(
            f"SHADOW_BLOCK {numeric_id} {int(generation)} {int(show_revision)} {hash_id} "
            f"{int(start_show_ns)} {int(end_show_ns)} {int(frames)} {1 if healthy else 0}"
        )

    def shadow_plan(self, target_show_ns: int, prebuffer_ns: int) -> dict[str, str]:
        return self.request(f"SHADOW_PLAN {int(target_show_ns)} {int(prebuffer_ns)}")

    def effect_status(self, output_slot: int = 0) -> dict[str, str]:
        return self.request(f"EFFECT_STATUS {int(output_slot)}")

    def bypass_effect(self, output_slot: int, effect_id: int, bypassed: bool) -> dict[str, str]:
        return self.request(f"EFFECT_BYPASS {int(output_slot)} {int(effect_id)} {1 if bypassed else 0}")

    def streaming_voice_start(self,slot:int,generation:int,gain:float=1.0,loop:bool=False)->dict[str,str]:return self.request(f"STREAM_VOICE_START {int(slot)} {int(generation)} {float(gain)} {1 if loop else 0}")
    def streaming_voice_block(self,slot:int,generation:int,sequence:int,left:list[float],right:list[float],terminal:bool=False)->dict[str,str]:
        if len(left)!=len(right) or not 0<len(left)<=256:raise ValueError("streaming voice block must contain 1..256 stereo frames")
        interleaved=[sample for pair in zip(left,right) for sample in pair];payload=struct.pack("<"+"f"*len(interleaved),*interleaved).hex()
        return self.request(f"STREAM_VOICE_BLOCK {int(slot)} {int(generation)} {int(sequence)} {len(left)} {1 if terminal else 0} {payload}")
    def streaming_voice_stop(self,slot:int,generation:int)->dict[str,str]:return self.request(f"STREAM_VOICE_STOP {int(slot)} {int(generation)}")
    def streaming_voice_stop_all(self)->dict[str,str]:return self.request("STREAM_VOICE_STOP_ALL")
    def streaming_voice_slot_status(self,slot:int)->dict[str,str]:return self.request(f"STREAM_VOICE_SLOT {int(slot)}")
    def streaming_voice_status(self)->dict[str,str]:return self.request("STREAM_VOICE_STATUS")

    def configure_le_uwb_hub(self, authority_epoch: int, *, target_lead_ns: int = 10_000_000,
                             max_end_to_end_ns: int = 30_000_000, fresh_ns: int = 100_000_000,
                             holdover_ns: int = 500_000_000, max_clock_uncertainty_ns: int = 250_000,
                             max_jitter_ns: int = 500_000, max_range_uncertainty_mm: float = 300.0,
                             max_drift_ppm: float = 250.0, require_authenticated: bool = True) -> dict[str, str]:
        return self.request(
            f"HUB_CONFIG {int(authority_epoch)} {int(target_lead_ns)} {int(max_end_to_end_ns)} "
            f"{int(fresh_ns)} {int(holdover_ns)} {int(max_clock_uncertainty_ns)} {int(max_jitter_ns)} "
            f"{float(max_range_uncertainty_mm):.6f} {float(max_drift_ppm):.6f} {1 if require_authenticated else 0}"
        )

    def register_le_uwb_node(self, node_id: int, stream_id: int, role: int, presentation_delay_ns: int,
                             *, required: bool = True) -> dict[str, str]:
        return self.request(
            f"HUB_NODE {int(node_id)} {int(stream_id)} {int(role)} {int(presentation_delay_ns)} {1 if required else 0}"
        )

    def observe_uwb_node(self, node_id: int, sequence: int, authority_epoch: int, hub_time_ns: int,
                         node_time_ns: int, distance_mm: float, range_uncertainty_mm: float,
                         clock_uncertainty_ns: int, *, authenticated: bool = True) -> dict[str, str]:
        return self.request(
            f"HUB_UWB {int(node_id)} {int(sequence)} {int(authority_epoch)} {int(hub_time_ns)} {int(node_time_ns)} "
            f"{float(distance_mm):.6f} {float(range_uncertainty_mm):.6f} {int(clock_uncertainty_ns)} {1 if authenticated else 0}"
        )

    def observe_le_isochronous(self, node_id: int, sequence: int, authority_epoch: int, event_counter: int,
                               hub_time_ns: int, transport_latency_ns: int, jitter_ns: int,
                               *, authenticated: bool = True) -> dict[str, str]:
        return self.request(
            f"HUB_LE {int(node_id)} {int(sequence)} {int(authority_epoch)} {int(event_counter)} {int(hub_time_ns)} "
            f"{int(transport_latency_ns)} {int(jitter_ns)} {1 if authenticated else 0}"
        )

    def plan_le_uwb_sync(self, hub_now_ns: int, show_now_ns: int, authority_epoch: int) -> dict[str, str]:
        return self.request(f"HUB_PLAN {int(hub_now_ns)} {int(show_now_ns)} {int(authority_epoch)}")

    def le_uwb_target(self, node_id: int, generation: int) -> dict[str, str]:
        return self.request(f"HUB_TARGET {int(node_id)} {int(generation)}")

    def le_uwb_node_status(self, node_id: int) -> dict[str, str]:
        return self.request(f"HUB_STATUS {int(node_id)}")

    def le_uwb_hardware_status(self, node_id: int | None = None) -> dict[str, str]:
        suffix = "" if node_id is None else f" {int(node_id)}"
        return self.request(f"HUB_HW_STATUS{suffix}")

    def open_uwb_hardware(self, path: str, baud: int = 921_600) -> dict[str, str]:
        device = str(path).strip()
        if not device or any(ch.isspace() for ch in device):
            raise ValueError("UWB device path must be a non-empty token")
        return self.request(f"HUB_HW_UWB_OPEN {device} {int(baud)}")

    def close_uwb_hardware(self) -> dict[str, str]:
        return self.request("HUB_HW_UWB_CLOSE")

    def open_le_iso_hardware(self, node_id: int, local_address: str, remote_address: str,
                             *, random_address: bool = False) -> dict[str, str]:
        for address in (local_address, remote_address):
            if len(address) != 17 or any(ch.isspace() for ch in address):
                raise ValueError("LE address must use XX:XX:XX:XX:XX:XX form")
        return self.request(
            f"HUB_HW_LE_OPEN {int(node_id)} {local_address} {remote_address} {1 if random_address else 0}"
        )

    def close_le_iso_hardware(self, node_id: int) -> dict[str, str]:
        return self.request(f"HUB_HW_LE_CLOSE {int(node_id)}")

    def poll_le_uwb_hardware(self, budget: int = 64) -> dict[str, str]:
        if budget < 1 or budget > 1024:
            raise ValueError("hardware poll budget must be between 1 and 1024")
        return self.request(f"HUB_HW_POLL {int(budget)}")

    def configure_user_profile(self, profile_id: int, authority_epoch: int) -> dict[str, str]:
        return self.request(f"PROFILE_CONFIG {int(profile_id)} {int(authority_epoch)}")

    def set_user_preference(self, namespace_id: int, key_id: int, layer: int, revision: int,
                            value_type: int, value: bool | int | float) -> dict[str, str]:
        if layer < 0 or layer > 4:
            raise ValueError("profile layer must be between 0 and 4")
        if value_type < 0 or value_type > 3:
            raise ValueError("profile value type must be between 0 and 3")
        encoded = int(value) if value_type in {0, 1, 3} else float(value)
        return self.request(
            f"PROFILE_SET {int(namespace_id)} {int(key_id)} {int(layer)} {int(revision)} {int(value_type)} {encoded}"
        )

    def user_preference(self, namespace_id: int, key_id: int) -> dict[str, str]:
        return self.request(f"PROFILE_GET {int(namespace_id)} {int(key_id)}")

    def clear_user_profile_layer(self, layer: int) -> dict[str, str]:
        if layer < 0 or layer > 4:
            raise ValueError("profile layer must be between 0 and 4")
        return self.request(f"PROFILE_CLEAR_LAYER {int(layer)}")

    def user_profile_status(self) -> dict[str, str]:
        return self.request("PROFILE_STATUS")

    def configure_interoperability_handshake(self, local: dict[str, Any], remote: dict[str, Any],
                                             adapters: list[dict[str, Any]] | None = None) -> dict[str, str]:
        def stage(side: str, offer: dict[str, Any]) -> None:
            versions = offer.get("protocolVersions") or [1, 1]
            schemas = offer.get("profileSchemaVersions") or [1, 1]
            protocol_min, protocol_max = min(map(int, versions)), max(map(int, versions))
            schema_min, schema_max = min(map(int, schemas)), max(map(int, schemas))
            self.request(
                f"INTEROP_{side}_BEGIN {int(offer['participantId'])} {protocol_min} {protocol_max} "
                f"{schema_min} {schema_max} {1 if offer.get('preservesUnknown', True) else 0} "
                f"{1 if offer.get('offlineCapable', True) else 0}"
            )
            for capability in (offer.get("capabilities") or [])[:64]:
                if isinstance(capability, dict):
                    capability_id = int(capability["id"])
                    required = bool(capability.get("required"))
                else:
                    capability_id, required = int(capability), False
                self.request(f"INTEROP_{side}_CAP {capability_id} {1 if required else 0}")

        stage("LOCAL", local)
        self.request("INTEROP_LOCAL_COMMIT")
        for adapter in (adapters or [])[:32]:
            self.request(f"INTEROP_ADAPTER {int(adapter['from'])} {int(adapter['to'])} {int(adapter.get('quality', 80))}")
        stage("REMOTE", remote)
        return self.request("INTEROP_PLAN")

    def interop_session_offer(self, session_id: int, transcript_hash: int, nonce: int, authority_epoch: int,
                              sequence: int, expires_unix_ms: int) -> dict[str, str]:
        return self.request(f"SESSION_OFFER {int(session_id)} {int(transcript_hash)} {int(nonce)} {int(authority_epoch)} {int(sequence)} {int(expires_unix_ms)}")

    def interop_session_authenticate(self, verified: bool, now_unix_ms: int, authority_epoch: int,
                                     minimum_sequence: int) -> dict[str, str]:
        return self.request(f"SESSION_AUTH {1 if verified else 0} {int(now_unix_ms)} {int(authority_epoch)} {int(minimum_sequence)}")

    def interop_session_negotiate(self, compatible: bool, protocol: int, profile_schema: int,
                                  profile_revision: int, registry_revision: int) -> dict[str, str]:
        return self.request(f"SESSION_NEGOTIATE {1 if compatible else 0} {int(protocol)} {int(profile_schema)} {int(profile_revision)} {int(registry_revision)}")

    def interop_session_consent(self, accepted: bool, projection_digest: int) -> dict[str, str]:
        return self.request(f"SESSION_CONSENT {1 if accepted else 0} {int(projection_digest)}")

    def interop_session_activate(self, now_unix_ms: int, authority_epoch: int, profile_revision: int,
                                 registry_revision: int) -> dict[str, str]:
        return self.request(f"SESSION_ACTIVATE {int(now_unix_ms)} {int(authority_epoch)} {int(profile_revision)} {int(registry_revision)}")

    def interop_session_status(self) -> dict[str, str]:
        return self.request("SESSION_STATUS")

    def configure_session_channel(self, session_high: int, session_low: int, key_epoch: int,
                                  capabilities: list[int]) -> dict[str, str]:
        self.request(f"CHANNEL_BEGIN {int(session_high)} {int(session_low)} {int(key_epoch)}")
        for capability in capabilities[:64]:
            self.request(f"CHANNEL_CAP {int(capability)}")
        return self.request("CHANNEL_COMMIT")

    def session_channel_outbound(self, capability_id: int, payload_size: int) -> dict[str, str]:
        return self.request(f"CHANNEL_OUT {int(capability_id)} {int(payload_size)}")

    def session_channel_inbound(self, session_high: int, session_low: int, key_epoch: int, sequence: int,
                                capability_id: int, payload_size: int, *, authenticated: bool) -> dict[str, str]:
        return self.request(
            f"CHANNEL_IN {int(session_high)} {int(session_low)} {int(key_epoch)} {int(sequence)} "
            f"{int(capability_id)} {int(payload_size)} {1 if authenticated else 0}"
        )

    def rotate_session_channel(self, key_epoch: int, grace_frames: int = 32) -> dict[str, str]:
        return self.request(f"CHANNEL_ROTATE {int(key_epoch)} {int(grace_frames)}")

    def session_channel_status(self) -> dict[str, str]:
        return self.request("CHANNEL_STATUS")

    def planned_handoff_prepare(self, transaction_id: int, source_epoch: int, target_epoch: int,
                                target_show_ns: int, *, allow_degraded_program: bool = False) -> dict[str, str]:
        return self.request(
            f"HANDOFF_TX_PREPARE {int(transaction_id)} {int(source_epoch)} {int(target_epoch)} "
            f"{int(target_show_ns)} {1 if allow_degraded_program else 0}"
        )

    def planned_handoff_acknowledge(self, transaction_id: int, *, program_ready: bool) -> dict[str, str]:
        return self.request(f"HANDOFF_TX_ACK {int(transaction_id)} {1 if program_ready else 0}")

    def planned_handoff_commit(self, transaction_id: int, observed_source_epoch: int,
                               witness_epoch: int, current_show_ns: int) -> dict[str, str]:
        return self.request(
            f"HANDOFF_TX_COMMIT {int(transaction_id)} {int(observed_source_epoch)} "
            f"{int(witness_epoch)} {int(current_show_ns)}"
        )

    def planned_handoff_abort(self, transaction_id: int) -> dict[str, str]:
        return self.request(f"HANDOFF_TX_ABORT {int(transaction_id)}")

    def planned_handoff_status(self) -> dict[str, str]:
        return self.request("HANDOFF_TX_STATUS")

    def show_event_status(self) -> dict[str, str]:
        return self.request("EVENT_STATUS")

    def show_event_loop_status(self) -> dict[str, str]:
        return self.request("EVENT_LOOP_STATUS")

    def cue_status(self) -> dict[str, str]:
        return self.request("CUE_STATUS")

    def automation_status(self) -> dict[str, str]:
        return self.request("AUTOMATION_STATUS")

    def automation_parameter(self, target_id: int, parameter_id: int, show_time_ns: int | None = None) -> dict[str, str]:
        suffix = "" if show_time_ns is None else f" {int(show_time_ns)}"
        return self.request(f"AUTOMATION_GET {int(target_id)} {int(parameter_id)}{suffix}")

    def automation_block(self, target_id: int, parameter_id: int, start_show_ns: int, step_ns: int, frames: int) -> dict[str, str]:
        return self.request(f"AUTOMATION_BLOCK {int(target_id)} {int(parameter_id)} {int(start_show_ns)} {int(step_ns)} {int(frames)}")

    def drain_show_events(self, show_time_ns: int) -> dict[str, str]:
        return self.request(f"EVENT_DRAIN {int(show_time_ns)}")

    def submit_cue_event(self, event_id: int, show_time_ns: int, cue_id: int, priority: int = 2) -> dict[str, str]:
        return self.request(f"EVENT_SUBMIT CUE {int(event_id)} {int(show_time_ns)} {int(priority)} {int(cue_id)}")

    def submit_transport_event(self, event_id: int, show_time_ns: int, action: str, value: float = 0.0, priority: int = 0) -> dict[str, str]:
        if action not in {"play", "pause", "stop", "rewind", "bpm", "seek"}:
            raise ValueError("invalid transport show-event action")
        return self.request(f"EVENT_SUBMIT TRANSPORT {int(event_id)} {int(show_time_ns)} {int(priority)} {action} {float(value):.6f}")

    def submit_automation_event(self, event_id: int, show_time_ns: int, target_id: int, parameter_id: int, value: float, *, duration_ms: int = 0, owner_id: int = 0, priority: int = 1) -> dict[str, str]:
        return self.request(
            f"EVENT_SUBMIT AUTOMATION {int(event_id)} {int(show_time_ns)} {int(priority)} {int(target_id)} {int(parameter_id)} {float(value):.9f} {int(duration_ms)} {int(owner_id)}"
        )

    def submit_mapped_automation(self, target: str, parameter_id: int, show_time_ns: int, value: float) -> dict[str, str]:
        target_id=self._stable_id(f"midi-map:{target}");event_id=self._stable_id(f"midi-event:{target}:{show_time_ns}:{value}")
        return self.submit_automation_event(event_id,show_time_ns,target_id,parameter_id,value,owner_id=self._stable_id("midi-learn"))

    def clear_native_midi_mappings(self) -> dict[str, str]:
        return self.request("MIDI_MAP_CLEAR")

    def configure_native_midi_master(self, bpm: float, key_root: int = 0, scale_mask: int = 0x0AB5) -> dict[str, str]:
        return self.request(f"MIDI_MAP_MASTER {float(bpm):.9f} {int(key_root)} {int(scale_mask)}")

    def upsert_native_midi_mapping(self, mapping: dict[str, Any]) -> dict[str, str]:
        source=dict(mapping.get("source") or {});target=dict(mapping.get("target") or {})
        messages={"note":0,"cc":1,"pitch-bend":2,"program":3};behaviors={"absolute":0,"relative":1,"trigger":2,"toggle":3,"gate":4}
        actions={"transport.play":1,"transport.stop":2,"master.tempo":3,"sample.trigger":4,"loop.toggle":5,"loop.clear":6}
        divisions={"off":0,"1/4":1,"1/8":2,"1/16":4,"1/32":8}
        target_id=str(target.get("targetId",""));device_id=str(source.get("deviceId",""));mapping_id=str(mapping.get("mappingId",""));resource_id=str(target.get("resourceId", ""))
        if not target_id or not device_id or not mapping_id:raise ValueError("native MIDI mapping requires mapping, device and target IDs")
        message=messages.get(str(source.get("message","")));behavior=behaviors.get(str(mapping.get("behavior","")))
        if message is None or behavior is None:raise ValueError("native MIDI mapping message or behavior is unsupported")
        return self.request(
            "MIDI_MAP_UPSERT "
            f"{self._stable_id('midi-mapping:'+mapping_id)} {self._stable_id(device_id)} {self._stable_id('midi-map:'+target_id)} "
            f"{self._stable_id('sampler:'+resource_id) if resource_id else 0} {int(target.get('parameterId',0))} {int(source.get('channel',0))} {int(source.get('number',0))} {message} {behavior} "
            f"{actions.get(target_id,0)} {divisions.get(str(mapping.get('quantize','off')),0)} {1 if mapping.get('keySync') else 0} "
            f"{float(target.get('minimum',0.0)):.9f} {float(target.get('maximum',1.0)):.9f}"
        )

    def sampler_load_pcm(self, resource_id: str, left: list[float], right: list[float], *, choke_group: int = 0,
                         looped: bool = False, loop_begin: int = 0, loop_end: int | None = None,
                         crossfade_frames: int = 0) -> dict[str, str]:
        if not resource_id or not left or len(left) != len(right):
            raise ValueError("sampler PCM requires a resource ID and equal non-empty stereo channels")
        total=len(left);end=total if loop_end is None else int(loop_end);sample_id=self._stable_id("sampler:"+resource_id)
        self.request(f"SAMPLER_LOAD_BEGIN {sample_id} {total} {int(choke_group)} {1 if looped else 0} {int(loop_begin)} {end} {int(crossfade_frames)}")
        for offset in range(0,total,256):
            block_left=left[offset:offset+256];block_right=right[offset:offset+256]
            pcm=b"".join(struct.pack("<ff",float(l),float(r)) for l,r in zip(block_left,block_right)).hex()
            self.request(f"SAMPLER_LOAD_PCM {offset} {len(block_left)} {pcm}")
        return self.request("SAMPLER_LOAD_COMMIT")

    def sampler_trigger(self, event_id: int, show_time_ns: int, resource_id: str, velocity: float = 1.0, note: int = 60) -> dict[str, str]:
        return self.request(f"SAMPLER_TRIGGER {int(event_id)} {int(show_time_ns)} {self._stable_id('sampler:'+resource_id)} {float(velocity):.9f} {int(note)}")

    def sampler_stop(self, event_id: int, show_time_ns: int, resource_id: str | None = None) -> dict[str, str]:
        suffix=f" {self._stable_id('sampler:'+resource_id)}" if resource_id else ""
        return self.request(f"SAMPLER_STOP {int(event_id)} {int(show_time_ns)}{suffix}")

    def sampler_status(self) -> dict[str, str]:
        return self.request("SAMPLER_STATUS")

    def remove_native_midi_mapping(self, mapping_id: str) -> dict[str, str]:
        return self.request(f"MIDI_MAP_REMOVE {self._stable_id('midi-mapping:'+str(mapping_id))}")

    def native_midi_mapping_status(self) -> dict[str, str]:
        return self.request("MIDI_MAP_STATUS")

    def release_automation_owner(self, event_id: int, show_time_ns: int, target_id: int, parameter_id: int, owner_id: int, *, priority: int = 1) -> dict[str, str]:
        return self.request(
            f"EVENT_SUBMIT AUTOMATION_RELEASE {int(event_id)} {int(show_time_ns)} {int(priority)} {int(target_id)} {int(parameter_id)} {int(owner_id)}"
        )

    def next_cue_event(self) -> dict[str, str]:
        return self.request("EVENT_NEXT CUE")

    def schedule_midi(self, event_id: int, show_time_ns: int, status: int, data1: int, data2: int) -> dict[str, str]:
        return self.request(f"MIDI_SCHEDULE {event_id} {show_time_ns} {status} {data1} {data2}")

    def scan_audio_devices(self) -> list[dict[str, Any]]:
        result = self.request("AUDIO_SCAN")
        count = int(result.get("count", "0"))
        devices: list[dict[str, Any]] = []
        for index in range(max(0, min(count, 64))):
            raw = self.request(f"AUDIO_DEVICE {index}")
            devices.append({
                "index": index,
                "id": raw.get("id", ""),
                "name": raw.get("name", "").replace("_", " "),
                "backend": raw.get("backend", ""),
                "address": raw.get("address", "").replace("_", " "),
                "input": raw.get("input") == "1",
                "output": raw.get("output") == "1",
                "connected": raw.get("connected") == "1",
                "attached": raw.get("attached") == "1",
                "selected": raw.get("selected") == "1",
                "inputSelected": raw.get("inputSelected") == "1",
            })
        return devices

    def _audio_output_slot(self, slot: int) -> int:
        slot = int(slot)
        if not 0 <= slot < 4:
            raise ValueError("audio output slot must be 0..3")
        return slot

    def select_audio_device(self, device_id: str, slot: int = 0) -> dict[str, str]:
        if not device_id or any(ch.isspace() for ch in device_id):
            raise ValueError("audio device id must be a non-empty token")
        slot = self._audio_output_slot(slot)
        return self.request(f"AUDIO_SELECT {slot} {device_id}")

    def bind_audio_output_player(self, player_id: str, slot: int = 0) -> dict[str, str]:
        if not player_id or any(ch.isspace() for ch in player_id):
            raise ValueError("player id must be a non-empty token")
        return self.request(f"AUDIO_OUTPUT_BIND_PLAYER {self._audio_output_slot(slot)} {player_id}")

    def set_audio_route(self, source: int, output: int, gain: float) -> dict[str, str]:
        return self.request(f"AUDIO_ROUTE {int(source)} {int(output)} {float(gain):.6f}")

    def set_audio_output(self, output: int, master: float, ceiling_db: float) -> dict[str, str]:
        return self.request(f"AUDIO_OUTPUT {int(output)} {float(master):.6f} {float(ceiling_db):.3f}")

    def _audio_input_slot(self, slot: int) -> int:
        slot = int(slot)
        if not 0 <= slot < 4:
            raise ValueError("audio input slot must be 0..3")
        return slot

    def select_audio_input(self, device_id: str, slot: int = 0) -> dict[str, str]:
        if not device_id or any(ch.isspace() for ch in device_id):
            raise ValueError("audio input device id must be a non-empty token")
        return self.request(f"AUDIO_INPUT_SELECT {self._audio_input_slot(slot)} {device_id}")

    def bind_audio_input_player(self, player_id: str, slot: int = 0) -> dict[str, str]:
        if not player_id or any(ch.isspace() for ch in player_id):
            raise ValueError("player id must be a non-empty token")
        return self.request(f"AUDIO_INPUT_BIND_PLAYER {self._audio_input_slot(slot)} {player_id}")

    def activate_audio_input(self, sample_rate: float, buffer_frames: int, channels: int = 2, source: int = 24, slot: int = 0, conversion_flags: int = 0, sample_format: str = "FLOAT_LE") -> dict[str, str]:
        sample_format = str(sample_format)
        if sample_format not in {"FLOAT_LE", "S32_LE", "S24_3LE", "S16_LE"}:
            raise ValueError("unsupported audio input sample format")
        command = f"AUDIO_INPUT_ACTIVATE {self._audio_input_slot(slot)} {float(sample_rate):.3f} {int(buffer_frames)} {int(channels)} {int(source)} {int(conversion_flags)}"
        if sample_format != "FLOAT_LE":
            command += f" {sample_format}"
        return self.request(command)

    def deactivate_audio_input(self, slot: int = 0) -> dict[str, str]:
        return self.request(f"AUDIO_INPUT_DEACTIVATE {self._audio_input_slot(slot)}")

    def deactivate_all_audio_inputs(self) -> None:
        for slot in range(4):
            try:
                self.deactivate_audio_input(slot)
            except RuntimeError:
                pass

    def audio_input_status(self, slot: int = 0) -> dict[str, str]:
        return self.request(f"AUDIO_INPUT_STATUS {self._audio_input_slot(slot)}")

    def all_audio_input_status(self) -> list[dict[str, str]]:
        return [self.audio_input_status(slot) for slot in range(4)]

    def route_audio_input(self, output: int, gain: float, slot: int = 0) -> dict[str, str]:
        return self.request(f"AUDIO_INPUT_ROUTE {self._audio_input_slot(slot)} {int(output)} {float(gain):.6f}")

    def configure_audio_drift(self, slot: int = 0, *, enabled: bool = True, max_ppm: float = 2000.0, queue_gain_ppm: float = 1000.0) -> dict[str, str]:
        return self.request(
            f"AUDIO_DRIFT_CONFIG {self._audio_output_slot(slot)} {1 if enabled else 0} {float(max_ppm):.3f} {float(queue_gain_ppm):.3f}"
        )

    def activate_audio(self, sample_rate: float, buffer_frames: int, output: int = 0, slot: int = 0, conversion_flags: int = 0, sample_format: str = "FLOAT_LE", channels: int = 2) -> dict[str, str]:
        sample_format = str(sample_format)
        channels = int(channels)
        if sample_format not in {"FLOAT_LE", "S32_LE", "S24_3LE", "S16_LE"}:
            raise ValueError("unsupported audio output sample format")
        if not 1 <= channels <= 32:
            raise ValueError("audio output channels must be 1..32")
        command = f"AUDIO_ACTIVATE {self._audio_output_slot(slot)} {float(sample_rate):.3f} {int(buffer_frames)} {int(output)} {int(conversion_flags)}"
        if sample_format != "FLOAT_LE" or channels != 2:
            command += f" {sample_format} {channels}"
        return self.request(command)

    def deactivate_audio(self, slot: int = 0) -> dict[str, str]:
        return self.request(f"AUDIO_DEACTIVATE {self._audio_output_slot(slot)}")

    def deactivate_all_audio_outputs(self) -> None:
        for slot in range(4):
            try:
                self.deactivate_audio(slot)
            except RuntimeError:
                pass

    def audio_stream_status(self, slot: int = 0) -> dict[str, str]:
        return self.request(f"AUDIO_STREAM_STATUS {self._audio_output_slot(slot)}")

    def all_audio_stream_status(self) -> list[dict[str, str]]:
        return [self.audio_stream_status(slot) for slot in range(4)]

    def scan_midi_devices(self) -> list[dict[str, Any]]:
        result = self.request("MIDI_SCAN")
        count = int(result.get("count", "0"))
        devices: list[dict[str, Any]] = []
        for index in range(max(0, min(count, 32))):
            raw = self.request(f"MIDI_DEVICE {index}")
            devices.append({
                "index": index,
                "id": raw.get("id", ""),
                "name": raw.get("name", "").replace("_", " "),
                "path": raw.get("path", ""),
                "input": raw.get("input") == "1",
                "connected": raw.get("connected") == "1",
            })
        return devices

    def attach_midi_input(self, device_id: str, player_id: str) -> dict[str, str]:
        if not device_id or any(ch.isspace() for ch in device_id):
            raise ValueError("device id must be a non-empty token")
        if not player_id or any(ch.isspace() for ch in player_id):
            raise ValueError("player id must be a non-empty token")
        return self.request(f"MIDI_ATTACH {device_id} {player_id}")

    def detach_midi_input(self, device_id: str) -> dict[str, str]:
        if not device_id or any(ch.isspace() for ch in device_id):
            raise ValueError("device id must be a non-empty token")
        return self.request(f"MIDI_DETACH {device_id}")

    def poll_midi_inputs(self, max_events: int = 64) -> list[dict[str, Any]]:
        self.request("MIDI_INPUT_POLL")
        events: list[dict[str, Any]] = []
        for _ in range(max(0, min(int(max_events), 256))):
            raw = self.request("MIDI_INPUT_NEXT")
            if raw.get("available") != "1":
                break
            events.append({
                "deviceId": raw.get("device", ""),
                "playerId": raw.get("player", ""),
                "showTimeNs": int(raw.get("showNs", "0")),
                "status": int(raw.get("status", "0")),
                "data1": int(raw.get("data1", "0")),
                "data2": int(raw.get("data2", "0")),
            })
        return events

    def inject_midi_input(self, device_id: str, player_id: str, show_time_ns: int, status: int, data1: int, data2: int) -> dict[str, str]:
        return self.request(f"MIDI_INPUT_INJECT {device_id} {player_id} {show_time_ns} {status} {data1} {data2}")

    def core_status(self) -> dict[str, str]:
        return self.request("CORE_STATUS")

    def set_clock_source(self, source: str) -> dict[str, str]:
        source = str(source).strip()[:63]
        if not source or any(ch.isspace() for ch in source):
            raise ValueError("clock source must be a non-empty token")
        return self.request(f"CLOCK_SOURCE {source}")

    def observe_clock(self, local_ns: int, source_ns: int) -> dict[str, str]:
        return self.request(f"CLOCK_OBSERVE {int(local_ns)} {int(source_ns)}")

    def clock_status(self, local_ns: int | None = None) -> dict[str, str]:
        return self.request("CLOCK_STATUS" if local_ns is None else f"CLOCK_STATUS {int(local_ns)}")

    def configure_transport_discipline(self, source_id: int, authority_epoch: int, *, holdover_ns: int = 1_000_000_000,
                                       max_slew_ppm: float = 500.0, recovery_window_ns: int = 5_000_000_000) -> dict[str, str]:
        return self.request(f"TRANSPORT_DISCIPLINE_CONFIG {int(source_id)} {int(authority_epoch)} {int(holdover_ns)} {float(max_slew_ppm):.6f} {int(recovery_window_ns)}")

    def observe_transport_discipline(self, sequence: int, authority_epoch: int, local_ns: int, source_ns: int,
                                     local_show_ns: int, source_show_ns: int) -> dict[str, str]:
        return self.request(f"TRANSPORT_DISCIPLINE_OBSERVE {int(sequence)} {int(authority_epoch)} {int(local_ns)} {int(source_ns)} {int(local_show_ns)} {int(source_show_ns)}")

    def transport_discipline_status(self, local_ns: int | None = None) -> dict[str, str]:
        return self.request("TRANSPORT_DISCIPLINE_STATUS" if local_ns is None else f"TRANSPORT_DISCIPLINE_STATUS {int(local_ns)}")

    def configure_midi_clock(self, authority_epoch: int, bpm: float, boundary_show_ns: int = 0) -> dict[str, str]:
        return self.request(f"MIDI_CLOCK_CONFIG {int(authority_epoch)} {float(bpm):.9f} {int(boundary_show_ns)}")

    def start_midi_clock(self, authority_epoch: int, boundary_show_ns: int = 0) -> dict[str, str]:
        return self.request(f"MIDI_CLOCK_START {int(authority_epoch)} {int(boundary_show_ns)}")

    def stop_midi_clock(self, authority_epoch: int, show_time_ns: int) -> dict[str, str]:
        return self.request(f"MIDI_CLOCK_STOP {int(authority_epoch)} {int(show_time_ns)}")

    def set_midi_clock_tempo(self, authority_epoch: int, bpm: float, boundary_show_ns: int) -> dict[str, str]:
        return self.request(f"MIDI_CLOCK_TEMPO {int(authority_epoch)} {float(bpm):.9f} {int(boundary_show_ns)}")

    def observe_midi_clock(self, authority_epoch: int, sequence: int, show_time_ns: int) -> dict[str, str]:
        return self.request(f"MIDI_CLOCK_OBSERVE {int(authority_epoch)} {int(sequence)} {int(show_time_ns)}")

    def emit_midi_clock(self, until_show_ns: int, maximum: int = 4096) -> dict[str, str]:
        return self.request(f"MIDI_CLOCK_EMIT {int(until_show_ns)} {int(maximum)}")

    def midi_clock_status(self) -> dict[str, str]:
        return self.request("MIDI_CLOCK_STATUS")

    def timing_plan(self, now_ns: int, target_ns: int, fixed_ns: int, jitter_ns: int, lookahead_ns: int, timestamped: bool) -> dict[str, str]:
        return self.request(
            f"TIMING_PLAN {now_ns} {target_ns} {fixed_ns} {jitter_ns} {lookahead_ns} {1 if timestamped else 0}"
        )

    def time_state(self) -> dict[str, str]:
        return self.request("TIME")

    def schedule_lighting(self, event_id: int, show_time_ns: int, universe: int, channel: int, value: int) -> dict[str, str]:
        return self.request(f"LIGHT_SCHEDULE {int(event_id)} {int(show_time_ns)} {int(universe)} {int(channel)} {int(value)}")

    def drain_lighting(self, show_time_ns: int) -> dict[str, str]:
        return self.request(f"LIGHT_DRAIN {int(show_time_ns)}")

    def artnet_frame_info(self, universe: int) -> dict[str, str]:
        return self.request(f"LIGHT_ARTNET {int(universe)}")

    def sacn_frame_info(self, universe: int) -> dict[str, str]:
        return self.request(f"LIGHT_SACN {int(universe)}")

    def configure_lighting_network(
        self,
        target: str,
        port: int = 6454,
        *,
        protocol: str = "artnet",
        universe_base: int = 1,
    ) -> dict[str, str]:
        target = str(target).strip()
        if not target or any(ch.isspace() for ch in target):
            raise ValueError("lighting target must be a non-empty IPv4 token")
        protocol = str(protocol).strip().lower()
        if protocol not in {"artnet", "sacn"}:
            raise ValueError("lighting protocol must be artnet or sacn")
        universe_base = int(universe_base)
        if not 1 <= universe_base <= 63984:
            raise ValueError("sACN universe base must be 1..63984")
        return self.request(
            f"LIGHT_NET_CONFIG {target} {int(port)} {protocol.upper()} {universe_base}"
        )

    def arm_lighting_network(self, armed: bool) -> dict[str, str]:
        return self.request(f"LIGHT_NET_ARM {1 if armed else 0}")

    def lighting_network_status(self) -> dict[str, str]:
        return self.request("LIGHT_NET_STATUS")

    def notation_quantize(self, beats: float, grid: str) -> dict[str, str]:
        return self.request(f"NOTATION_QUANTIZE {float(beats):.9f} {grid}")

    def status(self) -> dict[str, Any]:
        if not self.available:
            return {
                "available": False,
                "path": str(self._path) if self._path else None,
                "error": self._last_error,
            }
        try:
            status = self.request("STATUS")
            time_state = self.request("TIME")
            core = self.request("CORE_STATUS")
            show_loop = self.request("EVENT_LOOP_STATUS")
            cue = self.request("CUE_STATUS")
            automation = self.request("AUTOMATION_STATUS")
            parameters = self.request("PARAM_STATUS")
            runtime_show = self.request("SHOW_RUNTIME_STATUS")
            routing = self.request("ROUTE_STATUS")
            journal = self.request("JOURNAL_STATUS")
            return {
                "available": True,
                "path": str(self._path),
                "hello": dict(self._hello),
                "status": status,
                "core": core,
                "clock": time_state,
                "showLoop": show_loop,
                "cue": cue,
                "automation": automation,
                "parameters": parameters,
                "runtimeShow": runtime_show,
                "routing": routing,
                "journal": journal,
            }
        except RuntimeError as exc:
            self._last_error = str(exc)
            return {"available": False, "path": str(self._path) if self._path else None, "error": self._last_error}

    def close(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            if process is None:
                return
            try:
                if process.poll() is None and process.stdin is not None:
                    process.stdin.write("QUIT\n")
                    process.stdin.flush()
                    process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
            finally:
                if process.stdin:
                    process.stdin.close()
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
