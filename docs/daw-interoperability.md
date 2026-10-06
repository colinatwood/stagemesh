# DAW interoperability direction

Ardour is a useful reference for StageMesh’s DAW-facing boundaries: a
real-time audio graph, transport/session state, MIDI control, and plugin
hosting. StageMesh does not copy Ardour source or claim Ardour compatibility
from this document.

## StageMesh alignment

- `DawStreamRenderer` and the playback queues provide bounded, block-oriented
  rendering and exact loop behavior.
- The transport clock and show-time event queues provide deterministic
  scheduling separate from device activation.
- MIDI mappings remain explicit show events rather than silently changing
  physical output authority.
- Plugin adapters are isolated processes with manifest verification and
  platform-specific launch binding requirements.
- Audio device selection and hotplug recovery remain identity-pinned and
  fail-closed.

## Next interoperability capabilities

1. Add an optional JACK/PipeWire bridge behind the existing audio endpoint
   contracts. It must be opt-in and must not replace the native ALSA path.
2. Expose transport position, sample rate, block size, and connection status as
   read-only diagnostics before allowing graph control.
3. Represent external DAW connections as capability-scoped endpoints with
   bounded names, explicit ownership, and disconnect recovery.
4. Keep plugin discovery, verification, launch, delay compensation, and audio
   restart as separate lifecycle stages.
5. Add loopback integration tests for graph connection, transport stop, device
   loss, and recovery without arming physical outputs.

## Qualification boundary

JACK/PipeWire loopback and hosted tests can verify graph contracts, framing,
transport, and recovery. They cannot establish physical latency, converter
quality, clock stability, plugin compatibility, or stage-audio qualification.

Reference: [Ardour source repository](https://github.com/ardour/ardour).
