# Open Lighting Architecture interoperability direction

OLA is a reference for a protocol/device distribution layer: application code
produces lighting intent while a daemon and plugins abstract DMX, Art-Net,
sACN, RDM, and USB-DMX hardware. StageMesh should preserve that separation
when it grows beyond its current native UDP outputs.

## StageMesh adapter direction

- Keep fixture and cue compilation independent of transport and device plugin.
- Add an optional OLA client/bridge path rather than embedding `olad`.
- Expose protocol, node, universe, and device identity in read-only status.
- Reject ambiguous or stale node identity before sending physical output.
- Preserve explicit arm/disarm and generation fencing across daemon restart.
- Treat protocol conversion as a measured adapter boundary, not a transparent
  claim that every DMX device behaves identically.
- Keep RDM discovery and device mutation separate from ordinary DMX output.

## Qualification sequence

1. Run an OLA daemon with a virtual or isolated Art-Net/sACN endpoint.
2. Verify StageMesh can discover the intended node and universe.
3. Send a known cue through the client/bridge path.
4. Restart the daemon and remove/re-add the selected node.
5. Verify output fences and remains disarmed until explicit re-arm.
6. If using USB-DMX or RDM, record device permissions and mutation evidence
   separately from network-protocol evidence.

OLA supports Linux and macOS, with some Windows functionality. Its LGPL-2.1
licensing and plugin architecture require a dependency/license review before
any direct integration or redistribution.

Reference: [Open Lighting Architecture](https://github.com/OpenLightingProject/ola).
