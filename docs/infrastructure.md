# StageForge infrastructure slice

## Principle

The frontend is a control client. Show-critical state belongs to an authoritative runtime, and real-time audio/MIDI/lighting execution belongs behind replaceable native adapters.

The current bridge intentionally separates **authoritative intent/state** from **native execution**. This lets the native core take over timing/audio responsibilities incrementally without replacing every UI/API client.

## Current process boundary

```text
Browser / tablet / future hardware control points
        |
        | HTTP commands + resource revision tokens
        | Server-Sent Events invalidation stream
        v
Python development bridge
  - authoritative revisioned show state
  - per-resource concurrency revisions
  - idempotent command handling
  - atomic checkpoints
  - hash-linked event record
  - capability/resource planning
  - latency-plan fallback implementation
        |
        | authenticated local stdio IPC (development transport)
        v
Native C++20 engine follower
  - monotonic transport clock
  - audio-device abstraction + explicit Linux ALSA playback stream
  - atomic personal MonitorBus state
  - allocation-free monitor block mixer + graph router
  - fixed-capacity timestamped MIDI scheduler
  - raw-MIDI discovery/input queue + hot-plug bindings
  - external clock discipline + holdover state
  - latency/lookahead planner
  - bounded SPSC queues
  - explicitly armed Art-Net UDP output
```

Each bridge-spawned native process receives a random per-process IPC token and rejects commands until `AUTH` succeeds. The stdio transport is still deliberately replaceable. It validates the semantic seam without making UPP depend on Python, JSON-RPC, protobuf, sockets, or a vendor runtime. A later binary local IPC transport should preserve the same commands and state semantics.

## Global and per-resource revisions

Every snapshot has a monotonically increasing global `revision` for audit ordering.

For multi-control-point operation the snapshot also contains `resourceRevisions`:

```json
{
  "revision": 41,
  "resourceRevisions": {
    "transport": 9,
    "show": 4,
    "system": 7,
    "monitor:alex": 12,
    "monitor:sam": 3
  }
}
```

Clients may still use the global optimistic-concurrency token:

```http
If-Match: "rev-41"
```

For independent departmental controls they should additionally use the relevant resource token:

```http
X-StageForge-Resource-If-Match: "monitor:alex@12"
```

When a resource token is present, an unrelated global change does not invalidate that operation. A stale write to the same resource still receives `409`.

This preserves a single audit order without making FOH, lighting, production and personal monitor surfaces unnecessarily block each other.

## Command idempotency

Every mutation may send:

```http
X-StageForge-Command-Id: <unique command id>
```

Retries with the same command ID return the original result instead of re-executing the command. This is essential once commands travel across unreliable or reconnecting control links.

State mutation, persistence and native synchronization are serialized so native execution cannot receive revision 42 after revision 43 during concurrent writes.

## Event delivery

`GET /api/v1/events` provides a Server-Sent Events stream. Events carry monotonically increasing `eventId` values and global revisions. The browser uses this as an invalidation stream and fetches authoritative state only when a new revision exists.

This is intentionally one-way. Show-control commands remain explicit mutations rather than being hidden inside a bidirectional socket protocol.

## Persistence and public record

`.runtime/show-state.json` is written atomically after successful mutations.

`.runtime/events.jsonl` is the append-only hash-linked operational event journal. Adaptation and operational-authority receipts also enter `.runtime/public-record.jsonl`, whose exact payload chain is SHA-256 linked and authenticated with the persisted node identity key. A separately configured witness can attest an exact record hash through `/api/v1/public-record/witness`; accepted attestations are kept in their own hash-linked ledger. HMAC node signatures are not public-key transparency, so production witness independence still requires a genuinely separate failure/administrative domain.

On ordinary crash recovery the current show state is recovered with transport held paused. Replica application is different: a standby may keep the replicated transport clock warm, but physical output authority remains fenced and never auto-arms.

## Native execution follower

When `build/native/stagemesh_engine` exists, the bridge starts it automatically. Override the path with:

```bash
STAGEFORGE_NATIVE_ENGINE=/path/to/stagemesh_engine ./scripts/run.sh
```

Disable native integration explicitly with:

```bash
STAGEFORGE_NATIVE_ENGINE=off ./scripts/run.sh
```

The engine currently accepts a small line protocol over stdin/stdout:

```text
AUTH <spawn-token>
HELLO
PING
TIME
STATUS
TRANSPORT play|pause|stop|rewind
SET_BPM <number>
SEEK <seconds>
AUDIO_SCAN
AUDIO_DEVICE <index>
AUDIO_SELECT <deviceId>
AUDIO_INPUT_SELECT <slot:0..3> <deviceId>
AUDIO_INPUT_BIND_PLAYER <slot:0..3> <playerId>
AUDIO_INPUT_ACTIVATE <slot:0..3> <sourceSampleRate> <bufferFrames> <channels> <graphSource>
AUDIO_INPUT_DEACTIVATE <slot:0..3>
AUDIO_INPUT_STATUS <slot:0..3>
AUDIO_INPUT_ROUTE <slot:0..3> <graphOutput> <gain>
AUDIO_ACTIVATE <sampleRate> <bufferFrames> <graphOutput>
AUDIO_DEACTIVATE
AUDIO_STREAM_STATUS
AUDIO_ROUTE <source> <output> <gain>
AUDIO_OUTPUT <output> <master> <limiterDb>
HUB_CONFIG <epoch> <targetLeadNs> <maxEndToEndNs> <freshNs> <holdoverNs> <maxClockUncertaintyNs> <maxJitterNs> <maxRangeUncertaintyMm> <maxDriftPpm> <requireAuthenticated:0|1>
HUB_HW_UWB_OPEN <devicePath> <baud>
HUB_HW_UWB_CLOSE
HUB_HW_LE_OPEN <nodeId> <localAddress> <remoteAddress> <randomAddress:0|1>
HUB_HW_LE_CLOSE <nodeId>
HUB_HW_POLL [budget]
HUB_HW_STATUS [nodeId]
PROFILE_CONFIG <profileId> <authorityEpoch>
PROFILE_SET <namespaceId> <keyId> <layer:0..4> <revision> <type:0..3> <value>
PROFILE_GET <namespaceId> <keyId>
PROFILE_CLEAR_LAYER <layer:0..4>
PROFILE_STATUS
INTEROP_LOCAL_BEGIN <participantId> <protocolMin> <protocolMax> <profileSchemaMin> <profileSchemaMax> <preservesUnknown:0|1> <offlineCapable:0|1>
INTEROP_LOCAL_CAP <capabilityId> <required:0|1>
INTEROP_LOCAL_COMMIT
INTEROP_ADAPTER <fromCapabilityId> <toCapabilityId> <quality:1..100>
INTEROP_REMOTE_BEGIN <participantId> <protocolMin> <protocolMax> <profileSchemaMin> <profileSchemaMax> <preservesUnknown:0|1> <offlineCapable:0|1>
INTEROP_REMOTE_CAP <capabilityId> <required:0|1>
INTEROP_PLAN
SESSION_OFFER <sessionId> <transcriptHash> <nonce> <authorityEpoch> <sequence> <expiresUnixMs>
SESSION_AUTH <signatureVerified:0|1> <nowUnixMs> <expectedEpoch> <minimumSequence>
SESSION_NEGOTIATE <compatible:0|1> <protocol> <profileSchema> <profileRevision> <registryRevision>
SESSION_CONSENT <accepted:0|1> <projectionDigest>
SESSION_ACTIVATE <nowUnixMs> <authorityEpoch> <profileRevision> <registryRevision>
SESSION_INVALIDATE <authorityEpoch> <profileRevision> <registryRevision>
SESSION_STATUS
CHANNEL_BEGIN <sessionIdHigh> <sessionIdLow> <keyEpoch>
CHANNEL_CAP <capabilityId>
CHANNEL_COMMIT
CHANNEL_OUT <capabilityId> <payloadSize>
CHANNEL_IN <sessionIdHigh> <sessionIdLow> <keyEpoch> <sequence> <capabilityId> <payloadSize> <authenticationVerified:0|1>
CHANNEL_ROTATE <newKeyEpoch> <previousKeyGraceFrames>
CHANNEL_RESTORE <keyEpoch> <outboundSequence> <inboundSequence> <checkpointVerified:0|1>
CHANNEL_STATUS
HUB_NODE <nodeId> <leStreamId> <role:0..4> <presentationDelayNs> <required:0|1>
HUB_UWB <nodeId> <sequence> <epoch> <hubNs> <nodeNs> <distanceMm> <rangeUncertaintyMm> <clockUncertaintyNs> <authenticated:0|1>
HUB_LE <nodeId> <sequence> <epoch> <eventCounter> <hubNs> <transportLatencyNs> <jitterNs> <authenticated:0|1>
HUB_PLAN <hubNowNs> <showNowNs> <epoch>
HUB_TARGET <nodeId> <planGeneration>
HUB_STATUS <nodeId>
MONITOR_SET <player> <field> <value>
MONITOR_GET <player>
MIDI_SCHEDULE <eventId> <showTimeNs> <status> <data1> <data2>
MIDI_DRAIN <showTimeNs>
MIDI_SCAN
MIDI_DEVICE <index>
MIDI_ATTACH <deviceId> <playerId>
MIDI_DETACH <deviceId>
MIDI_INPUT_POLL
MIDI_INPUT_NEXT
CLOCK_SOURCE <sourceId>
CLOCK_OBSERVE <localNs> <sourceNs>
CLOCK_STATUS [localNs]
LIGHT_SCHEDULE <eventId> <showNs> <universe> <channel> <value>
LIGHT_DRAIN <showNs>
LIGHT_NET_CONFIG <unicastIPv4> <port>
LIGHT_NET_ARM <0|1>
LIGHT_NET_STATUS
LIGHT_ARTNET <universe>
TIMING_PLAN <nowNs> <targetNs> <fixedNs> <jitterNs> <lookaheadNs> <timestamped:0|1>
NOTATION_QUANTIZE <beats> <1/4|1/8|1/16|1/32>
QUIT
```

The native process is an execution follower for now. The bridge remains authoritative for revisions and persisted state. The next migration can make the native show clock authoritative while preserving the public API.

All graph mixing, automation, monitoring and effect-chain processing occurs in one canonical planar float32 domain at 192 kHz. Capture slots retain independent native sample rates (current hardware activation range 8–384 kHz); the real-time boundary converts each source with a fixed-memory 16-tap windowed-sinc converter before it enters the graph. The final graph result is converted to each output device's own rate. Fractional frame accounting is retained between callbacks, so 44.1/48/88.2/96/176.4 kHz sources do not accumulate whole-frame rate error. Integer PCM adapters can normalize signed 16-, packed signed 24-, and signed 32-bit samples to float32 before rate conversion.

This standardizes processing resolution; it does not manufacture musical bandwidth absent from a lower-rate source. Rate conversion, sink drift correction and Show Time are separate domains: neither source conversion nor output clock correction changes transport position.

## LE-UWB live-stage synchronization hub

The native hub treats LE and UWB as complementary evidence domains. A platform adapter maps Bluetooth LE Audio isochronous stream/event timing and presentation delay into `HUB_LE`. An IEEE 802.15.4z/Fira-style adapter maps paired clock timestamps, range and measurement uncertainty into `HUB_UWB`. UWB range is used to remove one-way propagation skew from the clock pair; UWB is not assumed to carry the audio program.

Up to 64 endpoints can be registered as performer inputs, monitor outputs, stage outputs, lighting or controls. Each required endpoint needs fresh authenticated observations from both domains under the current authority epoch. Core separately rejects sequence replay, stale LE evidence, expired UWB holdover, excessive drift, clock/range uncertainty, jitter, latency and presentation lead.

`HUB_PLAN` produces one target in hub monotonic time and StageForge Show Time. `HUB_TARGET` projects that boundary into each locked endpoint's disciplined device clock, allowing adapters to schedule locally instead of reacting to a last-moment network message. Optional endpoints can degrade without blocking the required group. A ready plan is execution timing permission only and always reports `physicalOutputsArmed=0`.

The default policy targets 10 ms presentation lead, caps admitted end-to-end timing at 30 ms, requires LE observations within 100 ms, permits UWB clock holdover to 500 ms, and limits reported clock uncertainty to 250 µs and jitter to 500 µs. These are admission defaults, not claims about unmeasured hardware. Codec, controller, RF, buffering, amplifier and transducer latency must be reported and proven by adapters before a device is accepted for a live-stage path.

## Audio-device and stream boundary

`AudioDevice` remains the lifecycle/configuration abstraction and `NullAudioDevice` remains the safe fallback. Linux now also has an `AlsaAudioOutput` adapter that loads `libasound.so.2` dynamically, configures interleaved 32-bit float playback, preallocates its render buffer before start, and records callback/xrun counts. There is still no compile-time ALSA dependency.

Desired endpoint selection is intentionally separate from stream activation. Persisting `alsa-...` in venue/show state does not start hardware. `POST /api/v1/audio/activate` requires explicit physical-output acknowledgement, and restart/demotion returns execution to the null backend.

`MonitorGraphRouter` maps personal monitor controls into the fixed `AudioGraph`: shared vocal/band/click/talkback/ambient stems use stable global source slots while each player gets a dedicated self stem and monitor output. Actual input/source producers are the next audio boundary.

The audio render callback performs no network I/O, filesystem I/O, persistence or IPC waits. Platform adapters must keep allocation and locking out of steady-state callback work.

## Personal MonitorBus

Each player receives an independent `MonitorBus` with atomic values for:

- master
- self
- vocals
- band
- click
- talkback
- ambient
- muted

Registry mutation is control-thread work. Individual bus reads/writes are atomic so future audio callbacks can snapshot them without taking a mutex.

`MonitorMixer` is allocation-free and mixes caller-provided mono stems into caller-provided stereo output buffers. Limiting, spatial rendering and actual hardware output remain separate stages.

## Timestamped MIDI

`MidiScheduler<N>` is fixed-capacity and stable-orders events by target show time and event ID. It does not allocate while scheduling/draining.

This establishes the model for control protocols generally: devices do not need identical latency; they need known timing profiles and commands that can be scheduled to land at the same target show time.

## Latency planning

`LatencyResolver` calculates required dispatch reserve from:

```text
fixed path latency
+ jitter × safety multiplier
or minimum endpoint lookahead,
whichever is larger
```

The HTTP bridge exposes the same semantic operation at:

```text
POST /api/v1/timing/plan
```

Example:

```json
{
  "nowNs": 80000000,
  "targetNs": 100000000,
  "fixedLatencyNs": 5000000,
  "jitterNs": 2000000,
  "minimumLookaheadNs": 6000000,
  "timestamped": true
}
```

This yields a 9 ms reserve and a 91 ms dispatch point for a 100 ms target.

## Public C ABI

`include/stageforge/core_api.h` is now API 1.55 and keeps the base ABI small. Domain functionality is discovered through versioned extension identifiers, including:

- event sink
- resource control
- state provider
- audio device, slot-0 compatibility output, four-slot multi-output streaming, single-input compatibility and four-slot multi-input capture lifecycle
- canonical float32/192 kHz processing, sample-format normalization, bounded rate-converter and format-neutral effect-chain contracts
- LE-UWB live-stage hub coordination with dual-radio evidence, per-device presentation targets and explicit output-authority separation
- Linux LE ISO socket and normalized UWB evidence hardware bridges; BAP/UCI/vendor control remains in replaceable platform adapters
- layered user-profile customization and explicit interoperability handshake planning with unknown-field preservation
- authenticated interoperability sessions, consent-bound profile projection, semantic capability provenance and hardware bench reports
- authenticated framed session channels with capability scopes, replay watermarks, key rotation and reconnect checkpoints
- personal monitor control
- timing profiles
- MIDI scheduling
- MIDI input discovery/binding
- clock discipline
- notation capture
- lighting network output
- node authority
- replication envelopes and automatic peer transport
- failover health/promotion
- witness quorum leases and authority fencing
- failover continuity measurement separating timeline alignment from physical-output re-arm delay

Unknown extension identifiers remain valid data even when an implementation cannot execute them.

## Adapter/resource boundary

Adapters publish:

- identity
- semantic capabilities
- priority
- estimated CPU/memory
- real-time status
- supported fallback levels

The resource planner can therefore suspend visual/AI work before critical audio/control modules. Vendor-specific logic stays out of the show model.

## Native MIDI input + desired-state bindings

The native MIDI input seam now treats physical endpoints as replaceable capacity. On Linux, StageForge can discover and open raw `/dev/snd/midiC*D*` inputs without linking libasound. The parser handles running status and ignores SysEx payloads in this first channel-voice slice. Other operating systems can implement CoreMIDI/Windows MIDI Services backends behind the same `MidiInputManager` and C extension semantics.

MIDI device mappings are **desired state** in the show model. If a mapped controller is absent, the binding remains pending. Native hot-plug scans automatically reattach the endpoint when the same device ID returns. MIDI activity owns `midi:<player>` resource revisions; notation owns `notation:<player>` revisions and only advances when it actually observes a note event.

The development bridge runs a small internal MIDI pump that drains the native bounded input queue into authoritative state. This is not UI polling and is expected to disappear when the native engine becomes authoritative for event storage/recording.

## External clock discipline

`ClockDiscipline` accepts paired local/source timestamps from future PTP, MTC, Link, MIDI-clock or hardware adapters. It estimates rate drift, applies only a fraction of phase error per observation, and enters holdover after source observations stop. It never abruptly rewrites transport position.

Clock authority and transport authority remain separate: the current native transport remains StageForge-controlled while the external clock layer provides a disciplined time reference. The next migration step is to let transport/sample-time progression consume that reference with explicit authority handoff.

## Next native/infrastructure work

1. Extend the canonical bounded sinc conversion into a phase-continuous asynchronous resampler with explicit cross-device clock calibration.
2. Add non-Linux CoreAudio/Windows/JACK capture/playback adapters while preserving the same four-slot logical I/O contracts.
3. Expand fixed capture/output slots into venue patch/channel maps and larger fixed-capacity banks without changing the show model.
4. Measure actual audible handoff gaps from timestamped output telemetry and add a witness-backed controlled-handoff/re-arm policy.
5. Qualify semantic fixture/venue patch mapping and Art-Net/sACN output on real venue networks and consoles.
6. Replace stdio with framed authenticated IPC and capability-scoped process isolation; typed authority leases and signed/witnessable adaptation receipts are implemented, with governance/conformance Public Record bindings remaining.


## Auto notation boundary

Notation is a **derived representation**, not an authority over the performance. StageForge stores completed raw note timing independently from the quantized score view. Changing the notation grid or project-key spelling therefore never rewrites the captured performance.

Each player owns an independent notation resource:

```text
notation:<player-id>
```

This lets a player or arranger alter a notation view without colliding with FOH, lighting, system-capacity or personal-monitor mutations.

The development bridge accepts player-scoped note-on/note-off capture and exposes a MIDI input observer route (`POST /api/v1/players/{id}/midi/input`). Note messages on that path automatically feed notation while non-note MIDI leaves the notation resource untouched. It derives:

- raw show-time timing
- raw beat timing
- quantized onset/duration
- project-key-aware pitch spelling
- a lightweight browser preview
- MusicXML 4.0 partwise export

The browser's **Add dev note** control is only an integration probe. The intended production path is:

```text
hardware MIDI / software instrument
        |
 timestamped MIDI adapter
        |
 raw performance event
        +------------------> audio/MIDI execution
        |
        +------------------> notation capture
                                  |
                            derived score view
                                  |
                             MusicXML export
```

`notation-core` is priority 3 (`enhancement`): under constrained capacity it may degrade to capture-only or suspend score derivation while the show-critical audio/MIDI path continues. Raw notation input must never be allowed to stall real-time MIDI execution.

The native core now includes an allocation-free `NotationQuantizer` primitive so quantization semantics can migrate out of Python without changing the public notation model. Full native note pairing/part storage should occur only after timestamped MIDI input routing is established.

### Notation traffic stays bounded

The ordinary global show snapshot carries only the most recent 16 derived notation notes per player plus a `rawNoteCount`. It deliberately omits full raw-note history so unrelated control operations do not grow in network cost as a show progresses.

Full raw capture is retained in atomic persistence checkpoints and is available through the player-specific notation endpoint and MusicXML export. This keeps notation interoperable and recoverable without making a monitor-fader mutation serialize an entire score.


## Native audio routing and discovery

The development engine now separates three concepts that must not be conflated:

1. **desired endpoint** stored in show/venue state,
2. **discovered endpoint** reported by a platform backend, and
3. **execution backend** that is actually moving audio samples.

Linux discovery, playback and capture dynamically load `libasound.so.2` when available. The native engine can explicitly activate a selected ALSA playback or capture endpoint, while `null-audio` remains the safe fallback. A missing desired endpoint remains pending rather than being erased, and selecting an endpoint never grants physical execution authority by itself.

`AudioGraph` is a fixed 32x16 source/output matrix. Route and master gains are atomic; `process()` allocates no memory and takes no locks. Output protection uses an instant-attack peak limiter with a configurable ceiling. This is digital peak protection, not calibrated hearing-exposure management.

External clock drift updates transport rate after rebasing the current transport position, avoiding a discontinuous show-time jump. Clock authority and transport authority remain separate.

## Lighting scheduling

Lighting state changes use the same StageForge show-time domain as MIDI. The bridge computes a dispatch time from target show time plus the endpoint timing profile, then queues the event in the native fixed-capacity scheduler. A development dispatch loop drains events as show time reaches the dispatch timestamp.

The native core can encode the resulting 512-slot universe into ArtDMX or an E1.31 data packet and send it through the explicitly selected Art-Net or sACN unicast adapter. The network adapters accept unicast IPv4 only in this slice, and **configuration is not authority**: neither can transmit until explicitly armed. Reconfiguration, restart, standby demotion and shutdown disarm both. Multicast sACN, synchronization packets and physical console/network qualification remain future work.

## Primary/standby replication and authority fencing

The development bridge now models node authority independently from show state. A node is either `primary` or `standby`. Only the primary accepts ordinary show mutations, mapped MIDI ingestion, physical audio activation and lighting arming. A standby can receive verified replicated state and keep its native transport warm, but it is read-only to normal control clients.

Replication uses a versioned canonical JSON envelope containing source node, authority epoch, monotonic sequence, show revision, complete recoverable snapshot and SHA-256 digest. When `STAGEFORGE_REPLICATION_SECRET` is configured the digest is additionally authenticated with HMAC-SHA256. The protocol rejects tampering, stale epochs and duplicate/out-of-order sequences. The envelope contract remains transport-neutral. The development bridge now supplies an optional authenticated HTTP push transport for venue-LAN primary-to-standby heartbeat/state delivery, so another transport can replace it later without changing the state contract.

Authority handoff is explicit. Demotion immediately disarms Art-Net/sACN, deactivates hardware audio and detaches native MIDI inputs. Promotion re-enables the ability to bind/receive MIDI, but **does not automatically re-arm audio or lighting**. This prevents failover from producing duplicate physical output simply because two machines are healthy at once.

Planned handoff has a separate native transaction. `CorePlannedHandoff` permits only one prepared transfer, fixes the source and target authority epochs plus an explicit Show-Time boundary, and requires target acknowledgement before commit. Commit succeeds only when the observed source epoch and witness-acquired target epoch match exactly and the boundary has arrived. An explicitly declared degraded-program transfer may acknowledge without pre-roll readiness; otherwise missing program readiness fails closed. Commit transfers no physical-output permission: all audio and lighting outputs remain disarmed until their existing explicit authorization paths run.

The coordination layer carries this transaction as a target-bound canonical offer authenticated with the replication HMAC secret. The standby verifies digest, signature, target node and replicated source before preparing native state. Operator pre-roll acknowledgement consumes the existing execution decision and cannot manufacture readiness, then delivers an authenticated receipt to the offering primary. At the Show-Time boundary the old primary demotes and fences itself before requesting an atomic, target-bound witness transfer from the exact source epoch to the exact next epoch. Partial quorum transfer is irreversible and therefore remains fail-closed. Commit is standby-owned and requires it to acquire the transferred witness epoch, preventing the primary or an HTTP caller from asserting a lease it does not possess.


## Automatic replication, witness leases and failover

When `STAGEFORGE_PEER_URL` and replication authentication are configured, the primary pushes authenticated state changes and heartbeat envelopes to the standby. Legacy `STAGEFORGE_REPLICATION_SECRET` remains supported; `STAGEFORGE_REPLICATION_KEYRING_FILE` adds restart-free old/new overlap with an authenticated key identifier and no legacy downgrade fallback. Replica age still provides the `healthy` / `suspect` / `eligible` failure signal.

For automatic authority transfer, StageForge now supports external witness leases. Configure an odd set of independent witness services with `STAGEFORGE_WITNESS_URLS`; a majority is required. Each witness persists one unexpired holder per cluster and advances its epoch when authority changes. Lease requests are HMAC authenticated.

A configured primary is authoritative only while it holds a quorum lease. If renewal fails until the lease expires, the old primary self-fences: physical audio input/output and lighting are disabled, mapped MIDI is detached, and the node demotes to standby. This solves the dangerous side of split brain rather than merely electing a new node.

With `STAGEFORGE_AUTO_FAILOVER=1`, a standby promotes only when **both** conditions are true:

1. replicated-primary heartbeat age exceeds the promotion threshold, and
2. the standby successfully acquires a witness quorum lease.

Promotion adopts the witness authority epoch into the replication tracker. Physical audio and lighting remain disarmed after promotion. Without witnesses configured, StageForge retains the previous manual-after-failure-detection behavior.

## Native multi-input / multi-output audio and logical player sources

Linux ALSA capture/playback are dynamically loaded from `libasound.so.2`, preserving compile-time independence. The native engine owns four capture slots and four independently activatable physical output slots. Capture data is written once into a fixed-capacity `AudioFanoutRing`; each active output owns an independent read cursor, so FOH, a player monitor, broadcast and another sink can consume the same captured source without stealing samples from one another. Slow sinks accrue their own dropped/underrun telemetry rather than blocking the capture producer or another sink.

Each output slot can bind directly to a fixed graph output or resolve a logical player monitor output through `MonitorGraphRouter`. Each ALSA sink reports callbacks, xruns, fan-out queue/drop/underrun counts and an observed sample-rate ppm estimate. Each sink also feeds the measured ppm and queue error into the bounded adaptive drift controller described above; correction changes only sink consumption and never StageForge Show Time. Steady-state render/fan-out paths allocate no memory and take no locks.

The show model stores four portable desired mappings:

```json
{
  "audio": {
    "inputs": [
      {"slot":0,"deviceId":"vox-interface","playerId":"jordan","sampleRate":44100,"route":{"output":0,"gain":0.7}},
      {"slot":1,"deviceId":"bass-interface","playerId":"sam","sampleRate":96000,"route":{"output":0,"gain":0.6}}
    ]
  }
}
```

The native graph source is deliberately absent from this persisted contract. At activation, `MonitorGraphRouter` resolves the logical player onto its current self-source bus. This keeps a show portable if venue hardware/channel assignments change.

The older `inputDeviceId`, `inputPlayerId` and `inputRoute` fields remain slot-0 compatibility aliases. Older control clients therefore continue to operate while newer clients can use `audio.inputs[]` and `/api/v1/audio/inputs/{slot}`.

Capture activation and signal routing remain separate authority decisions per slot. Selecting a device does nothing by itself; capture requires explicit acknowledgement, and a nonzero persisted FOH route requires a second signal-route acknowledgement.

## Cross-node program continuity

Replication protocol v2 carries a signed `executionTelemetry` object beside the recoverable show snapshot. This data is **not** artistic state and is never allowed to overwrite the show model. It describes the execution edge of the current authority so a standby can compare program positions in StageForge Show Time.

For each active output the primary reports the last rendered block end in Show-Time nanoseconds. On promotion the standby retains that cursor. When its newly armed sink renders its first block, the runtime computes:

```text
new first rendered Show Time - old last block end Show Time
```

A positive value is a program gap; a negative value is an overlap. Machine-local `steady_clock`/physical-write timestamps remain useful for local start/stall telemetry but are intentionally excluded from cross-node comparison because their epochs are unrelated.

Handoff readiness is explicit:

- `state-warm`: show/control state is replicated, but there is no active program output to prebuffer.
- `deterministic-prebuffer-eligible`: active program output has no live capture dependencies, so a future shadow renderer may safely pre-render locally.
- `live-input-state-warm`: microphones/instruments are active. Control replication alone cannot recreate those samples; a duplicated physical/network audio feed is required before audio prebuffer can honestly become ready.

The runtime records `handoffTargetShowNs`, but it does not seek authoritative transport toward a rendered-buffer edge. Buffer lead is execution detail, not transport authority.


## Deterministic handoff decision layer

Failover election, authority transfer and program continuity are separate decisions. `backend/handoff.py` is deliberately pure logic: it consumes signed replication facts plus persisted show/venue redundancy intent and returns an explainable decision. It performs no I/O, never arms hardware and never changes transport.

The policy evaluates replica age, local Show-Time lag, source program cursor availability, active live-input slots, duplicated feed declarations and deterministic source readiness. The result has separate `authorityBlockers` and `programBlockers`. This permits a dead-primary recovery to transfer control even when program continuity is degraded, while still preventing the system from claiming that audio is ready.

Live-input configuration is declarative: `split` or `network` redundancy must name a source and be explicitly enabled. Deterministic source readiness requires a required source to be shadow-capable and locally available. A separate ephemeral `HandoffExecutionRegistry` holds fresh evidence from the components actually doing the work. A live feed must report matching source identity and health; a shadow renderer must report health, matching content hash when declared, and a buffered horizon extending beyond the handoff target by the policy `requiredPrebufferMs`. Evidence expires after `executionStatusFreshMs` and is discarded when the replicated authority generation changes.

The decision used immediately before promotion is retained in failover continuity telemetry. Postmortem analysis can therefore distinguish a known degraded takeover from a takeover that unexpectedly violated its declared readiness conditions.


### Handoff execution acknowledgement

The decision layer intentionally distinguishes three levels:

1. **declared**: the show/venue says redundancy or shadow rendering should exist,
2. **logic-ready**: declarations are internally sufficient for the current handoff facts, and
3. **execution-ready**: a fresh runtime report proves the standby feed/buffer actually exists.

Only level 3 can set `readyForProgramTakeover=true`. For deterministic sources, every required source must have a fresh report whose optional content hash matches and whose `bufferedUntilShowNs` reaches at least `handoffTargetShowNs + requiredPrebufferMs`. For live inputs, every active slot must have a fresh healthy report matching the declared duplicated source ID.

These reports are ephemeral execution state, not show intent, and therefore are never checkpointed or replicated as authority state. A change of replicated source node/epoch clears them immediately.

## Technology-openness logic

Technology evolution is deliberately outside the real-time/show-authority path. `backend/technology.py` evaluates extension maturity, scale safeguards and capability negotiation without touching transport or hardware.

The invariant is asymmetric: ecosystem growth may increase the evidence required to make something universal, but never increases the permission required to experiment. Experimental namespaces are therefore unconstrained by ecosystem size. Standard/Core promotion requires independent implementation groups, while existing recognized Standards remain compatible even if larger-scale revalidation later asks for broader evidence.

Unknown fields are preserved in technology-extension records. Capability negotiation is exact-match only at the core layer: common capability IDs are executable, while unknown IDs remain preserved and require an explicit translator. The core never guesses semantic equivalence.

Standards/Core registry records are append-like in lifecycle semantics. They cannot be deleted through ordinary state mutation; deprecation/supersession keeps the old record and can declare a migration bridge. A configurable mandatory-Core budget discourages growth of the universal required surface as the ecosystem becomes large.

Technology catalog size is explicitly isolated from show-control traffic. Routine `ShowState.snapshot()` contains policy/scale summary plus `extensionCount`, while `technology_snapshot()` contains the full registry. Disk checkpoints retain the full registry; show-critical replication uses `replication_snapshot()` and omits technology catalog/resource data, preserving the receiving node's local catalog. This allows a large ecosystem registry to grow without enlarging every monitor mutation, SSE refresh or failover heartbeat.

Grandfathered Standard recognition is not inferred from a maturity string alone. A lower-evidence Standard at a larger scale tier requires `adoptionRecordRef`; future work will verify that reference against the signed Public Record/conformance evidence ledger. Without that record, current-scale promotion thresholds apply.

## Community governance and hype maturity

Platform governance is intentionally off the show-critical path. `CommunityGovernance` owns accounts, proposals, time-bound email invitations and votes in a separate checkpoint. The community monitor computes hype directly from proposal age, so no polling thread is required: day 1 is `1.0`, day 365 is `0.0` by default, and hype itself contributes exactly zero choice-vote units. The complement `1-hype` matures every cast raw vote equally for binding-quorum purposes.

Each admin ballot email stamps `sentAt` immediately before delivery handoff, embeds both `sentAt` and immutable `expiresAt`, and records SMTP/outbox acceptance separately. Material proposal edits increment the version and invalidate older invitations. Active emailed windows cannot be administratively closed. Adopted proposal text/change payloads are immutable.

Once any community proposal exists, direct governance-policy and technology-openness-policy mutation is fenced unless the explicit bootstrap override is enabled. Permanent policy changes are represented as canonical proposal `change` payloads, voted on, adopted only after deterministic binding readiness, then explicitly applied. This keeps administration operational while making platform-rule changes community-authorized.

Governance data is excluded from live show snapshots and failover replication. It may grow independently without changing audio callback deadlines, control-point SSE payloads or standby heartbeat size.


## Venue realization reconciliation

A committed Venue Patch Layer is only the intended environment mapping. StageForge separately reconciles that mapping against the current venue compatibility plan and fresh adapter realization evidence. The reconciler reports `realized`, `unverified`, `drift`, or `blocked`; it does not silently rewrite mappings or arm hardware. Repair uses the normal adaptation transaction path.

Execution adapters can report logical patch key, provider, target, health, execution state, and current authority holder. Reports are ephemeral and freshness-bounded so a stale green report cannot become durable venue truth.

Temporary operational authority leases may delegate an exact venue patch, a known department, or an exact runtime resource for a bounded period. Typed scope identity prevents resource/department name collisions, exact resource ownership resolves before department ownership, and expiry fails closed. Venue-context leases are cleared when the active patch changes; runtime-context resource/department leases survive venue remaps; all leases are cleared when node authority is fenced. This allows deliberate live ownership changes without turning an operational lease into cluster or API authorization.

## Native Core control-state boundary

Transport intent and personal monitor state now have a native `CoreControlState` rather than being only side effects of the development bridge. Core maintains its own global revision, transport revision, player-monitor revisions, bounded command deduplication and external snapshot revision.

The bridge migration seam is transactional:

```text
CORE_SYNC_BEGIN revision
  CORE_SYNC_TRANSPORT ...
  CORE_SYNC_MONITOR ...
  CORE_SYNC_MONITOR ...
CORE_SYNC_COMMIT
```

Nothing staged becomes visible before commit. A stale external revision is refused, and replaying an already-applied external revision is a duplicate rather than another mutation. Existing single-operation native commands remain compatibility aliases but now pass through the same Core mutation accounting.

`TransportClock::snapshot()` is a real-time read. It uses two publication slots with reader pins: the audio thread reads an immutable published state without taking a mutex; the control writer is the only side allowed to wait before reusing an old slot. This keeps Show Time coherent without putting a control-thread lock in the audio callback.

Core also owns a fixed-capacity `CoreResourcePlanner`. The planner understands only universal resource facts: priority, estimated CPU, health, whether a module can degrade/suspend, total capacity and operating mode. It returns full/degraded/suspended/unavailable decisions. Vendor or domain-specific fallback names remain adapter concerns.

## Core typed show-event timeline

The native Core owns a fixed-capacity typed show timeline for transport, MIDI, lighting, cue and automation events. Producers submit trivially-copyable events through SPSC ingress; exactly one dispatcher owner ingests and orders them. Equal Show-Time events are ordered by priority, event type and event ID. Replay protection keys are `(event type, event id)` so legacy domains may reuse numeric IDs without cross-domain collisions.

Metrics are atomic observation only. Status callers never ingest pending events. This is intentional so a future dedicated Core dispatcher thread remains the sole timeline consumer. Late events are counted explicitly; events carrying `drop-if-late` are discarded rather than executed after their intended moment.

Legacy MIDI and lighting scheduler commands currently feed the typed timeline and then retain their established drain/output surfaces. This is a migration seam: clients keep compatibility while scheduling policy consolidates inside Core.

## Core show execution ownership

The typed show timeline has one native execution owner. `ShowExecutionLoop` continuously compares the published `TransportClock` Show Time with the next event and routes due events into transport, cue state, or bounded MIDI/lighting/automation handoff queues. Control clients may submit events, inspect atomic status, or request compatibility drain/cancel operations, but those owner operations are executed by the loop thread itself.

Cue state is now Core-owned. MIDI and lighting retain their existing domain schedulers for compatibility, but the Core loop never mutates those schedulers concurrently with their consumers; it writes only to SPSC domain handoff queues. Automation point/ramp state is now Core-owned; the legacy automation queue is observation-only after native application.


## Native runtime execution stack

The Core execution model is compiled rather than executed directly from mutable show JSON. The document layer remains responsible for open-format parsing, unknown-field preservation, migration, governance metadata and durable checkpoints. `CoreRuntimeShow` receives only validated execution facts: bounded role IDs, cue IDs, route edges and parameter descriptors. A compiled snapshot receives a monotonically increasing generation and may be queued for a Show-Time activation boundary. The execution-loop owner publishes that generation atomically; existing readers keep their previously pinned generation until release.

`CoreParameterRegistry` is the universal parameter seam between automation and concrete domains. Descriptors declare stable target/parameter identity, unit, range, default, timing class, safety class, persistence and endpoint kind. The engine currently binds audio-output masters, audio routes, monitor master/channels and DMX values. Audio-master evaluation may occur from the audio callback through immutable automation reads and atomic gain writes. Route-matrix publication, monitor graph synchronization and lighting-state writes remain on non-audio Core/control execution because those operations may wait on RCU readers or touch domain-owned state.

A newly registered endpoint explicitly seeds the corresponding automation baseline. This prevents the first linear ramp from starting at an invented zero when the physical/control endpoint already has a nonzero default.

Cue actions are compiled into `CoreCueActionGraph`. When a cue event becomes due, the sole show-timeline owner updates native cue state and schedules its deterministic action bundle back into the owner-owned timeline using an owner-only scheduling path. Derived actions retain normal validation, replay protection, priority ordering and Show-Time offsets; they do not create a second producer race.

Routing changes use two layers. `CoreRoutingState` validates the logical directed graph as one expected-revision transaction, including cycle rejection. For audio execution, `AudioGraph` publishes the entire 32x16 route matrix through two immutable slots with reader pins. An audio process block pins exactly one route generation, so a multi-route transaction cannot be observed halfway through. Writers may wait; the audio reader does not.

The plugin bridge is deliberately format-neutral. Core exposes target/parameter identity and a native-parameter setter callback. A CLAP-first host can bind that callback today; VST3/LV2/AU adapters can use the same seam later without teaching Core those formats. Plugin callbacks marked real-time safe remain the adapter's responsibility to implement without blocking/allocation.

`CoreEffectChain` now owns the format-neutral audio-processing seam. Each physical/logical output has a bounded ordered chain whose adapters identify as built-in, VST3, CLAP, LV2 or Audio Unit. SDK-specific discovery, factories, state chunks, licensing and UI stay outside Core. Adapters activate on the control thread and provide an in-place real-time callback; Core performs no allocation or plugin lifecycle work in the audio callback. A failed processor is counted and bypassed for subsequent blocks, while the rest of the chain continues. Declared latency is accumulated for telemetry but is not yet compensated across parallel paths.

`CoreJournal` is a bounded execution record, not a disk writer. Transport, cue, automation, MIDI, lighting, routing and runtime-generation events receive a local sequence plus a compact hash chain. The persistence service drains these records over the native IPC boundary and wraps them as `native-core` events inside the repository's existing SHA-256 ledger. This keeps disk/filesystem latency out of Core while establishing a deterministic persistence boundary suitable for later snapshot-plus-journal recovery.

`CoreShadowRenderPlanner` tracks deterministic-source ID, runtime generation, show revision, content identity, shadow capability, local asset readiness, health and buffered Show-Time horizon. Reports with stale generation/revision/hash are refused. `CoreShadowRenderExecutor` supplies the bounded execution seam: a source adapter registers a block callback and Core drives it sequentially toward a requested horizon. Only successful callbacks become contiguous `CoreShadowPrebuffer` evidence and planner readiness. The adapter still owns actual sample production; Core never substitutes silence, arms outputs or acquires authority.
