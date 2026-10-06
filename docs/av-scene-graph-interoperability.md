# Audiovisual scene-graph interoperability

OBS Studio is a reference for capture, compositing, encoding, recording, and
streaming. StageMesh can use the same separation between sources, scenes,
transitions, outputs, and recording sessions without adopting OBS internals.

## StageMesh capabilities to reinforce

- Keep source acquisition, scene composition, output routing, and recording as
  separate lifecycle stages.
- Provide a preview graph that cannot arm live physical outputs or publish a
  stream accidentally.
- Compile scene changes at a controlled boundary instead of mutating active
  graph state from arbitrary UI requests.
- Track source identity, format, timestamps, dropped frames, encoder state,
  and output authority in diagnostics.
- Make stream start/stop, recording start/stop, and physical capture permission
  independent operator actions.
- Preserve crash-safe recording manifests and recovery state.
- Treat plugins and capture sources as capability-scoped, bounded components.

## Qualification sequence

1. Build a scene from software or loopback sources.
2. Preview it without enabling any physical output.
3. Apply a bounded transition at a show-time boundary.
4. Start and stop recording independently from streaming.
5. Inject source loss, encoder failure, and output disconnect.
6. Verify safe stop, durable recording state, and explicit recovery/re-arm.
7. Record frame timing, dropped frames, audio/video sync, and output status.

Screen capture, camera, encoder, and network-stream tests do not qualify
physical cameras, venue networking, broadcast delivery, or stage safety.

OBS Studio is GPL-2.0-or-later. Review the license and plugin boundaries before
any reuse. Reference: [OBS Studio](https://github.com/obsproject/obs-studio).
