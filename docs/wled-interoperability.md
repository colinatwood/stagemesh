# WLED interoperability direction

WLED is a useful reference for network-controlled LED fixtures: segmented
outputs, presets, JSON control, Art-Net/E1.31 input, realtime sync, brightness
limiting, and embedded-device recovery. StageMesh should treat WLED-class
devices as explicitly identified network fixtures, not as generic UDP sinks.

## StageMesh adapter direction

- Model LED strips, matrices, RGBW, and RGB+CCT outputs as declared fixture
  capabilities with bounded channel footprints.
- Keep segment, palette, effect, and brightness state separate from show cues.
- Prefer a versioned JSON/device adapter with schema validation and bounded
  payloads over arbitrary HTTP requests.
- Use Art-Net/sACN for deterministic show output where appropriate; use a
  device API for configuration and non-realtime preset operations.
- Apply a global safety brightness/power envelope before physical output.
- Require device identity, network authorization, timeout, retry, and stale
  state handling.
- Stop realtime output and require explicit re-arm after device loss or
  authentication failure.
- Preserve an operator-visible record of effect, palette, segment, brightness,
  and firmware/device identity.

## Qualification sequence

1. Use a virtual or isolated WLED-class endpoint first.
2. Validate device identity, API version, capabilities, and authentication.
3. Send a bounded segment/preset update and verify the resulting state.
4. Exercise timeout, stale response, reconnect, and firmware/state mismatch.
5. Verify the safety brightness envelope and explicit re-arm behavior.
6. Test Art-Net/E1.31 realtime input separately from configuration API calls.

Network simulation and loopback validate protocol behavior only. They do not
qualify LED power, thermal limits, RF reliability, visible effects, venue
networking, or physical safety.

WLED is EUPL-1.2 licensed. Review the license and API terms before reusing
code or device assets. Reference: [WLED](https://github.com/wled/WLED).
