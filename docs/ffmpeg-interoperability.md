# FFmpeg interoperability

StageMesh may use FFmpeg as a media inspection and conversion boundary. The
[FFmpeg documentation](https://ffmpeg.org/ffmpeg-all.html) covers the formats,
codecs, filters, timestamps, and devices that make this useful, but a media
tool must remain subordinate to StageMesh's show and output authority model.

## Probe before use

Before importing media, record and validate:

- container and stream types;
- codec, pixel/sample format, channel layout, and sample rate;
- frame rate, duration, time base, start time, and discontinuities;
- dimensions, color metadata, and rotation/orientation;
- file size, decoded duration, and resource limits.

Do not infer timing from a filename or assume that nominal frame rate equals
presentation timestamps. A media asset with missing, non-monotonic, or ambiguous
timestamps should be marked for review or normalized into a new version.

## Conversion boundary

Transcoding and filtering should run in a bounded worker process with explicit
limits for input size, decoded frames, duration, memory, and output size. Write
to a temporary destination, verify the result, then publish it atomically with
its source hash, command/options, FFmpeg version, and conversion metadata.

Keep the original asset immutable. Never replace a show asset in place while a
rehearsal or live session can reference it.

## Clock and output safety

Media playback must expose its clock, buffering state, dropped/duplicated frame
counts, and end-of-stream state. Decode, preview, recording, and physical output
routes should be independently observable. A decoder error or stalled input
must stop or fence the affected route; it must not silently repeat stale frames
into an armed physical output.

FFmpeg device inputs and outputs are optional host capabilities. Their presence
does not qualify an ALSA, PipeWire, JACK, camera, GPU, or display path. Hardware
arming remains an explicit StageMesh operation with its own interlocks.

## Qualification scenarios

1. Probe valid audio, video, image-sequence, and subtitle assets and compare
   metadata against expected values.
2. Reject oversized, malformed, unsupported, and resource-exhausting inputs
   within bounded time.
3. Normalize a known variable-frame-rate asset and verify duration, timestamps,
   frame count, and audio/video alignment.
4. Interrupt a conversion and confirm that no partial file is published.
5. Exercise decoder failure, end-of-stream, and device loss in preview and live
   modes; confirm that only the affected route is fenced and recovery is
   explicit.

## Licensing and distribution

FFmpeg builds can differ in enabled components and licensing configuration.
Record the detected build configuration and keep distribution obligations
separate from runtime media support. StageMesh should integrate through a
documented adapter boundary rather than assuming every codec or device is
available everywhere.
