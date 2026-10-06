# Pyrotechnic visualization and show safety

StageMesh can learn from
[FireShow](https://github.com/giuseppe-coco/FireShow)'s 3D fireworks design,
particle visualization, event timeline, and synchronized audio concepts. These
capabilities belong in a simulation and planning layer; they must never imply
that a physical initiator or pyrotechnic device is connected or armed.

## Simulation-first model

Represent each effect as a versioned visual event with an identifier, show-time
position, duration, location, visual parameters, audio association, and source
asset. Keep the simulated effect separate from any physical channel mapping.
Preview should support play, pause, reset, seek, and deterministic replay with
no hardware side effects.

Use seeded or recorded simulation inputs when reproducibility matters. Record
the renderer, effect-library, asset, and show-plan versions so a review can
recreate what the operator saw.

## Physical-output boundary

Pyrotechnic, actuator, and other hazardous outputs require a separate capability
with independent authorization, interlocks, device identity, continuity/health
checks, geographic and timing constraints, and an emergency-stop path. A visual
timeline event is not a firing command. A failed preview, stale plan, lost
connection, or mismatched device must result in no physical action.

StageMesh should not implement or document construction, ignition, wiring, or
operational procedures for pyrotechnic devices. It can provide safe planning,
simulation, audit, and clearly fenced integration points for qualified operators
and compliant external systems.

## Qualification scenarios

1. Create a synthetic multi-effect timeline with audio cues and verify exact
   ordering, seeking, reset, and deterministic replay.
2. Change an asset, effect-library version, or renderer and confirm the plan is
   marked changed rather than silently treated as equivalent.
3. Exercise missing assets, invalid timing, overlapping events, and out-of-range
   locations; confirm preview diagnostics and no hardware activation.
4. Simulate device loss, stale authorization, interlock failure, and emergency
   stop; verify that all physical routes remain fenced.
5. Export a review package containing the plan, versions, simulation settings,
   warnings, and audit events without exporting an executable firing command.

## Integration boundary

The first implementation should be a software-only visualizer and timeline
validator. Any later physical integration must remain opt-in, separately
qualified, and governed by applicable safety rules and trained human operators.
