# Broadcast playout interoperability

StageMesh can use a broadcast-style playout adapter for layered graphics,
audio, video, recording, and multiple presentation outputs. This guidance is
informed by [CasparCG Server](https://github.com/CasparCG/server), which
supports professional media and graphics playout across multiple outputs on
Linux and Windows.

## Model channels and layers explicitly

Represent a playout plan as independently addressable channels and layers. Each
layer should declare its content type, template or asset version, z-order,
start point, duration, transition, and target output. Do not encode these
relationships only in an opaque command string.

Separate:

- content and template assets;
- channel/layer composition;
- output-device routing;
- preview versus live authority;
- recording and monitoring outputs.

This lets an operator inspect a cue before it changes a live surface and makes
partial failure diagnosable.

## Deterministic playout

Every scheduled item should have a stable identifier, an explicit timebase, and
an observable lifecycle: prepared, cued, playing, paused, completed, failed, or
fenced. Report actual start time, frame position, dropped frames, and output
health. A missing template, invalid media asset, or unsupported output must fail
before live activation whenever possible.

Commands should be idempotent where practical. Reconnecting to a server or
replaying an acknowledgement must not duplicate a layer, advance a cue twice,
or unexpectedly clear unrelated content.

## Output and recovery safety

Preview, recording, monitoring, and live transmission are separate routes.
Hardware output is never implied by successful asset loading or preview
rendering. Loss of a GPU, capture/output device, playout server, or control
connection should fence the affected route and preserve enough state for an
operator to understand what was last active. Recovery requires health checks,
configuration validation, and explicit re-arm.

## Qualification scenarios

1. Prepare a multi-channel, multi-layer cue and verify ordering, timing,
   transitions, and target outputs in preview mode.
2. Submit duplicate, late, malformed, and out-of-order control commands; confirm
   idempotent or explicitly rejected behavior.
3. Remove a template, media asset, or output device and verify preflight failure
   or route fencing without affecting unrelated layers.
4. Interrupt the control connection during playback and confirm that reconnect
   reconciliation does not duplicate or silently clear content.
5. Compare preview, recording, and live-route diagnostics while keeping physical
   outputs disarmed.

## Licensing boundary

CasparCG Server is GPLv3-or-later according to its repository documentation.
StageMesh should use the documented protocol and interoperability concepts
without copying implementation code or bundling components before reviewing
license and distribution obligations.
