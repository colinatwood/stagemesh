# PipeWire interoperability direction

PipeWire is a reference for low-latency multimedia processing and sharing on
modern Linux. StageMesh should support it as an optional session/graph
adapter while retaining direct ALSA and future JACK paths.

## Adapter boundaries

- Discover nodes by stable identity and capability, not display name alone.
- Read negotiated sample rate, channel layout, quantum, and latency before
  activation.
- Treat WirePlumber/session-policy changes as observable state transitions.
- Stop and fence the selected stream when its node disappears or its format
  changes unexpectedly.
- Require explicit re-arm after node recovery or session restart.
- Keep media permissions and physical output authority separate.
- Expose whether a path is direct ALSA, JACK-compatible, PipeWire-managed, or
  software loopback.

## Qualification sequence

1. Run a PipeWire null/loopback graph with no physical output.
2. Enumerate nodes and verify stable identity/capability readback.
3. Exercise graph connect/disconnect and quantum/rate renegotiation.
4. Restart the PipeWire session manager and verify fail-closed recovery.
5. Confirm the engine remains disarmed until explicitly re-armed.
6. Run the same graph through the PipeWire ALSA and JACK compatibility paths.
7. Record xruns, quantum, negotiated format, and recovery generations.

PipeWire loopback and compatibility-layer evidence validate graph behavior;
they do not establish physical latency, converter quality, clock stability,
or stage-hardware qualification.

The PipeWire project maintains the core graph, WirePlumber session policy,
ALSA integration, and JACK compatibility layers. StageMesh should integrate
through documented APIs and package contracts rather than vendor their source.

Reference: [PipeWire on GitHub](https://github.com/PipeWire).
