# JACK interoperability direction

JACK provides the reference model for a low-latency, graph-connected audio
runtime. StageMesh should use that model at an adapter boundary rather than
making JACK a hidden runtime dependency.

## Adapter contract

An optional JACK adapter should:

- negotiate sample rate and block size before activation;
- create bounded named input/output ports;
- perform only preallocated, non-blocking work in the process callback;
- publish connection and xrun status as read-only diagnostics;
- stop safely when the JACK server or selected port disappears;
- require explicit re-arm after device or server recovery;
- preserve StageMesh’s show-time clock and generation fencing.

JACK MIDI bridging should follow the same rule: incoming messages can become
queued, validated show events, but cannot silently arm physical outputs or
rewrite authoritative mappings.

## Qualification sequence

1. Run against a JACK or PipeWire-JACK loopback server.
2. Verify port discovery and bounded connection names.
3. Verify audio and MIDI graph connection/disconnection.
4. Inject server restart and selected-port loss.
5. Confirm the engine stops safely and remains disarmed.
6. Confirm explicit re-arm is required after recovery.
7. Measure callback block size, xrun count, and transport discontinuities.

Loopback evidence validates graph behavior only. It does not qualify physical
latency, clock stability, converter quality, or stage hardware.

The reference organization maintains JACK2, JACK1, example tools, MIDI
bridging, and session-management projects. StageMesh should inspect those
interfaces and licenses before implementing an adapter, without vendoring
their source.

Reference: [JACK Audio Connection Kit](https://github.com/jackaudio).
