# Audio inventory isolation

Windows BOOM capture observation run `38788475935` reached live capture, then
failed with `MIDI topology changed during snapshot; refresh required`.
The combined monitor deliberately rejects a MIDI snapshot if device counts or
the shared topology revision change during enumeration. Audio owners previously
depended on that combined result even though their fences only need audio
records. Their existing error handling stops capture/playback on a failed scan.

`DeviceMonitor::audio_snapshot()` uses the same audio enumeration and identity
construction as `snapshot()`, returning before MIDI enumeration. Audio discovery,
endpoint preflight, native capture/playback services, and selected-audio endpoint
smokes use that API. The combined snapshot remains the API for MIDI and mixed
device discovery; its instability rejection is unchanged.

The new path still requires an active monitor and its constructing control
thread. Audio enumeration failures propagate; missing or ambiguous selected
audio identities still disarm fences. Native endpoint invalidation, callback
fencing, stream draining, and explicit rearm rules are unchanged. This does not
make monitor construction/notification registration independent of MIDI, suppress
audio topology events, or automatically restart streams.

Lifecycle tests check audio-only records/counts, hashed identities, inactive and
wrong-thread refusal, and audio snapshots while the macOS virtual MIDI fixture
exists and is removed. `audio_service_snapshot_tests` links the production
capture/playback controllers and real execution-fence/identity code against
deterministic monitor and stream doubles. A permanently failing combined MIDI
snapshot must not interrupt activation or servicing. Audio enumeration failure,
selected-device loss and identity ambiguity must still stop/refuse execution;
device return alone must not restart it. These tests open no physical endpoint.
Windows/macOS native CI is required because this platform
monitor implementation is not compiled on Linux. Physical MIDI/audio churn,
latency, audible quality, and application recovery remain separate qualification
tasks. The earlier private helper's successful three-cycle BOOM run is evidence
for its exact old source, not for this change.
