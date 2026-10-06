# Native device monitor: Checkpoint 75

The `stagemesh_devices` C++ library now covers target-OS device observation,
privacy-preserving persistent identity, and fail-closed reconciliation. It remains
a control-thread module: callbacks only advance an atomic topology revision and
never open streams, allocate audio-path work, invoke user code, or automatically
rearm an output.

Snapshots expose only SHA-256-derived identity tokens. Raw endpoint IDs, CoreAudio
UIDs, CoreMIDI UniqueIDs, and device names are not exported by the monitor.
Selections may automatically rebind only when the OS supplies a strong identity
and exactly one current endpoint matches it. Duplicate strong identities fail as
`ambiguous`; missing endpoints become `detached`; installation-scoped/volatile
identities refuse automatic rebind.

## Platform identity

On macOS, audio endpoints use `kAudioDevicePropertyDeviceUID` and MIDI endpoints
use direction-scoped `kMIDIPropertyUniqueID`. Both are hashed before leaving the
native monitor and are eligible for exact-unique automatic recovery.

On Windows, the preferred strong identifier is `PKEY_AudioEndpoint_StableId`.
The hosted Windows Server 2025 runner currently compiles with Windows SDK 26100,
which predates that header symbol, so CMake feature-detects the API. With this SDK
`stableIdentityApiCompiled=false`; ordinary IMMDevice IDs are treated only as
installation snapshots and are not eligible for automatic rebind. A newer SDK
that exposes the StableId property can enable the strong path without weakening
fallback behavior.

## Hosted evidence

Checkpoint 74 first proved enumeration and notification registration lifecycle on
both target OSes. Checkpoint 75 run
[34881629489](https://github.com/colinatwood/stagemesh/actions/runs/34881629489)
then exercised identity/reconciliation on Windows and real software topology
changes on Apple Silicon macOS. PR source head:
`8028ac5005e81ddd6f69a8df2bfed0a28ee7e313`.

| Observation | Windows x64 | macOS 14 arm64 |
| --- | --- | --- |
| Explicit lifecycle cycles | 25 passed | 25 passed |
| Native lifecycle CTest | passed | passed under AddressSanitizer |
| Device count | 0 | 3 |
| Stable identity API compiled | false (SDK 26100) | true |
| Stable identities in baseline snapshot | 0 | 3 |
| Identity reconciliation contract | passed | passed |
| Native software CoreAudio add/remove/recreate event | n/a | passed |
| Native software CoreMIDI add/remove/recreate event | n/a | passed |
| Exact-unique identity recovery after recreate | synthetic contract only | CoreAudio + CoreMIDI passed |
| Observed topology revision | 0 | 11 |

macOS uses a temporary virtual CoreMIDI source and a temporary CoreAudio aggregate
device. These are real CoreMIDI/CoreAudio OS objects and real notification paths,
but they are software fixtures, not physical unplug/replug qualification. The
CoreMIDI wait pumps the creator CFRunLoop because CoreMIDI delivers the client
notification callback on that run loop.

Evidence artifacts:
- macOS: `sha256:08ed7bea660a89e1140eb02bfc96dac8775987d5c1e1a7f735b78bd7b8433d03`
- Windows: `sha256:6b3902bed5602f5b9ccf73307d33c518cbbf80910a43605780b7398f59e3f6dd`

Every evidence record explicitly keeps `physicalOutputsArmed`,
`physicalHardwareQualified`, `audioStreamingQualified`, and
`physicalHotplugQualified` false.

## Remaining implementation and qualification

- Integrate the native snapshots/revisions and selection resolver with the full
  StageMesh engine lifecycle so detach/ambiguity immediately fences unsafe
  physical execution and requires explicit recovery/rearm.
- Add Windows MIDI native enumeration/notifications and run Windows stable-ID
  evidence with a Windows SDK that exposes `PKEY_AudioEndpoint_StableId` and a
  real endpoint.
- Implement WASAPI/CoreAudio stream format negotiation, start/stop, loss handling,
  and bounded recovery outside the audio callback.
- Add per-device macOS alive/sample-rate/stream-configuration listeners and race
  tests where they materially affect an active stream.
- Qualify physical disconnect/reconnect, real audio performance, and named
  hardware separately.

## Build

```sh
cmake -S native -B build
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

Hosted macOS CI additionally configures `-DSTAGEMESH_DEVICE_ASAN=ON`.

Historical continuation: [Checkpoint 78 guarded lifecycle and manual rendering](backlog-checkpoint-78.md).

[Checkpoint 79](backlog-checkpoint-79.md) adds native playback ownership and Windows MIDI discovery.

[Checkpoint 80](backlog-checkpoint-80.md) adds shared native capture/playback
ownership and hosted macOS selected software endpoint loss/recreation tests.
Full-engine integration and Windows live endpoint evidence remain outstanding.

[Checkpoint 81](backlog-checkpoint-81.md) makes every successful explicit rearm
issue fresh authority, including after native-only revocation while the control
fence is still Armed. Initial arming is single-use; authority is noncopyable.
Rearm invalidates previous-generation consumers, which must stop and prepare
again. Hosted macOS capture/playback exercise this native stop/restart path.

[Checkpoint 82](backlog-checkpoint-82.md) requires current stable identity and
reconnect assurance for strong selections. Downgrades fence even unchanged native
objects; restoring evidence requires explicit rearm. Native macOS tests inject
weaker metadata during playback/capture and verify stop/recovery, without claiming
an OS-generated or physical identity downgrade.

[Checkpoint 83](backlog-checkpoint-83.md) adds `probe_audio_endpoint(selection,
direction)` for exact pinned native capability readback. It never falls back to
the default or silently follows a rebound identity. Hosted macOS uses non-default
aggregate capabilities for native playback/capture and rejects the removed pin
while a default remains available. Probing does not authorize execution.
