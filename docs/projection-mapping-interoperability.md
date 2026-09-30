# Projection-mapping interoperability

StageMesh can treat projection mapping as a presentation surface driven by
time-aligned show events. This guidance is informed by
[Splash](https://github.com/paperManu/splash), a modular video-mapping system
that uses calibrated 3D surfaces, multiple projectors, video inputs, and
rendering/output pipelines.

## Separate the mapping layers

Keep these concerns distinct:

- **Content:** video, images, text, and generated media.
- **Geometry:** the versioned 3D model or surface mesh.
- **Calibration:** projector intrinsics/extrinsics, warp, blend, and color
  parameters.
- **Routing:** which content is assigned to which projector or output.
- **Authority:** whether the presentation is preview-only or allowed to feed a
  live output.

A calibration update must not silently change show timing, output authority, or
the meaning of an existing cue. Store geometry and calibration versions with
the show plan and expose mismatches before rehearsal or playback.

## Safe runtime behavior

Preview and live output should be separate modes. The preview path may use
synthetic frames, recorded media, or loopback outputs without arming physical
devices. Live projection requires an explicit operator action and should report
projector identity, signal health, frame timing, dropped frames, and active
calibration versions.

If a projector, capture source, GPU output, or inter-process transport
disappears, freeze or blank the affected presentation surface and mark the
route unavailable. Do not redirect content to an unexpected physical output.
Recovery should require revalidation and explicit re-arm.

## Interoperability boundary

An adapter may support video files, capture devices, NDI, shared-memory feeds,
and other media transports, but each adapter must declare its format, clock,
latency, and failure behavior. Configuration exchange should be versioned and
validated; unsupported mesh, codec, color, or display metadata must produce a
diagnostic rather than a silent fallback.

Real-time scheduling and GPU/display tuning are host qualifications, not
assumptions of the portable StageMesh core. Record them as environment facts
and keep the software usable in a non-real-time preview environment.

## Qualification scenarios

1. Load a synthetic surface mesh and verify calibration and geometry versions.
2. Render a known test pattern in preview mode and check projector routing,
   warp, blend, color, and frame counters.
3. Replace a media source with a loopback source and verify that no physical
   output becomes armed.
4. Remove a configured output or invalidate calibration; confirm that the
   affected route is fenced and recovery requires explicit revalidation.
5. Save and reopen a show plan, confirming that content, geometry, calibration,
   routing, and authority remain independently inspectable.

## Licensing and reuse

Splash is GPL-licensed according to its project documentation. StageMesh should
borrow interoperability concepts and documented boundaries without copying
implementation code or bundling dependencies unless licensing and distribution
obligations have been reviewed.
