# Native MIDI callback ingress boundary

`MidiInputManager::capture_callback` provides a bounded handoff for MIDI
backends whose operating-system callbacks can run on threads separate from
the engine control loop. It copies the device and player tokens into a fixed
event and submits it through a sequence-numbered, bounded MPMC queue. The
callback path performs no allocation and takes no locks. Queue overflow is
counted; accepted callback events and test injections have separate audit
counters.

The existing Linux byte-stream poller and the engine's consumer use the same
queue. A four-producer native regression submits 1,600 uniquely timestamped
events while the consumer drains them, then verifies there are no duplicates,
missing events or drops. The ordinary full native test executable passes.

This is an ingress boundary only. Windows WinMM and macOS CoreMIDI input
handles are not yet opened by `MidiInputManager`; its target-OS `attach()` and
`poll()` paths remain fail-closed. Platform backends still need stable endpoint
resolution, callback context ownership, stop/disconnect/drain ordering, and
Windows/macOS compilation and runtime checks. In particular, the manager and
queue must outlive every native callback, and rescans or detach operations must
quiesce callback producers before mutating endpoint state.
