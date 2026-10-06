# Lighting-console interoperability direction

QLC+ is a useful cross-platform reference for fixture definitions, DMX
patching, Art-Net/sACN output, MIDI control, hotplug behavior, and live-show
cue operation. StageMesh does not copy QLC+ source or claim fixture-library
compatibility from this note.

## StageMesh capabilities to reinforce

- Keep fixture profiles separate from show cues and physical output targets.
- Validate channel footprints, universe/address bounds, and conflicting
  patches before a show can be armed.
- Represent fixture parameters by stable logical names while retaining raw DMX
  channel mappings for transparent inspection.
- Support Art-Net and sACN as explicit, mutually exclusive output paths.
- Preserve sequence, refresh, priority, and output-arm state in diagnostics.
- Treat MIDI, OSC, and control-surface input as queued intent, never implicit
  physical-output authorization.
- Stop output and require explicit re-arm after network, node, or fixture
  identity loss.

## Qualification sequence

1. Load a fixture profile and reject malformed or overlapping patches.
2. Compile a cue into bounded DMX universe changes.
3. Inspect the resulting channel map before arming.
4. Send to a loopback or isolated Art-Net/sACN receiver.
5. Exercise cue timing, sequence progression, refresh, and network loss.
6. Verify output stops safely and explicit re-arm is required after recovery.

Loopback and receiver tests validate protocol and patch behavior only. They do
not qualify a physical fixture, dimmer, moving head, venue network, or stage
show.

QLC+ is Apache-2.0 licensed. Review its current license and fixture-data terms
before considering any reuse. Reference: [QLC+](https://github.com/mcallegari/qlcplus).
