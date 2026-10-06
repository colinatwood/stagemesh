# Media editing and recording interoperability

Audacity is a useful reference for StageMesh’s cross-platform recording and
media-editing boundaries. StageMesh does not copy Audacity code or claim
Audacity project-file compatibility.

## Capabilities to reinforce

- Import media without opening or arming a physical device.
- Preserve source identity, format, channel count, sample rate, and duration
  as explicit metadata.
- Keep edits non-destructive until an explicit render or publish operation.
- Publish recordings atomically with WAV-byte, parent-directory, and recovery
  durability evidence.
- Keep temporary takes, snapshots, and replacement files recoverable after a
  crash or interrupted render.
- Make conversion, resampling, clipping, and channel-layout choices visible
  rather than silently falling back.
- Keep recording activation, monitoring, and physical input permission as
  separate operator-confirmed actions.

## StageMesh mapping

The existing DAW capture, media import, conversion, temporary-resource, and
recording-publication paths are the foundation for these rules. The next
software tests should exercise a complete non-destructive sequence:

1. Import a source file.
2. Create a bounded edit or take.
3. Render a derived output.
4. Verify the source and temporary resources remain recoverable.
5. Publish atomically and verify the durable recording manifest.
6. Repeat after an injected interruption.

No step in this sequence should arm physical audio input or output implicitly.

Reference: [Audacity source repository](https://github.com/audacity/audacity).
Audacity’s repository currently documents a major Audacity 4 structural change;
StageMesh should therefore treat the project as a capability and workflow
reference, not as a stable source-layout dependency.
