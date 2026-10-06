# Lighting-console operator model

ChamSys is a reference for professional lighting-console operation and
dedicated show-control hardware. Its public organization also exposes console
kernel and platform repositories, which are useful for studying appliance
constraints and embedded deployment boundaries.

## StageMesh capabilities to reinforce

- Separate programming mode, rehearsal mode, and live output mode.
- Make cue stacks, playbacks, priorities, overrides, and blackout state
  visible and auditable.
- Require a deliberate operator action before a playback can affect physical
  output.
- Display active output authority, network target, universe, fixture scope,
  and last-known device identity together.
- Make emergency stop/blackout independent of ordinary cue execution.
- Preserve show state and operator actions across reconnects without silently
  restoring physical output.
- Design controls for hardware surfaces as well as browser/operator clients,
  with bounded state synchronization and explicit ownership.

## Qualification sequence

1. Program and inspect a cue stack with no physical output armed.
2. Exercise playback priority, override, blackout, and emergency-stop paths.
3. Disconnect the lighting transport and verify output fencing.
4. Restart the control surface/session and verify disarmed restoration.
5. Re-arm only through an explicit, authenticated operator action.
6. Preserve an auditable event sequence for every output authority change.

This reference informs operator workflow and appliance constraints; it does
not establish compatibility with ChamSys consoles or any particular fixture.

Reference: [ChamSys GitHub organization](https://github.com/ChamSys).
