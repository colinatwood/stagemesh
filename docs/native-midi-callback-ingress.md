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
missing events or drops. The owner-specific regression submits 400 concurrent
callback-safe injections. The ordinary full native test executable passes.

The manager now opens CoreMIDI and WinMM input handles behind the owner-thread
boundary. Stable hashed endpoint resolution, callback context ownership, and
stop/disconnect ordering are implemented. Windows/macOS compilation and runtime
checks remain target evidence; rescans and detach operations still require
hardware testing to confirm callback quiescence during topology changes.
## Owner-thread integration

`MidiInputOwner` now owns the `MidiInputManager` registry on a dedicated worker.
The worker performs initial discovery, non-blocking polls, attach/detach and
shutdown; command callers receive copied descriptors or scalar results. The
bounded callback queue remains independent of the command mutex, so native
callbacks can enqueue while a control command is waiting. Shutdown closes native
handles on the owner before the manager is destroyed.

The engine uses this owner for MIDI scan/device/attach/detach/poll/inject paths;
event routing drains the queue on the engine thread. Linux owner tests cover four
concurrent producers and 400 callback-safe injections. CoreMIDI now resolves the
hashed source identity, connects an input port, parses packet-list bytes and
disconnects before the owner releases the port. Windows WinMM physical callback
attach remains the next qualification step: enumeration is identity-safe, but
legacy interface hookup requires target SDK/hardware execution and must not be
inferred from a cross-build. WinMM now resolves the owner-thread snapshot index,
opens `HMIDIIN` with a function callback, forwards packed channel messages, and
stops/resets/closes the handle before slot release. The remaining target-only
work is exercising callback delivery and device removal on a real Windows host.

The owner also reconciles attached target identities periodically. A missing or
changed native hash detaches the slot and closes its handle; failed snapshots do
not authorize a rebind, and no endpoint is silently substituted.
