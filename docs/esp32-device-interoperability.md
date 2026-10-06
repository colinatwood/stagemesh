# ESP32 device interoperability

StageMesh may use ESP32-class devices as low-cost telemetry, sensor, or
fixture-control endpoints. The [Arduino-ESP32 project](https://github.com/espressif/arduino-esp32)
supports multiple ESP32 families and provides a practical embedded adapter
target, but the device remains untrusted until it has passed identity and health
checks.

## Device contract

Each endpoint should report a stable device identity, firmware version, board
and pin capability, boot count, configuration version, monotonic sequence, and
clock status. Commands should name the target, session, command identifier,
expiry, expected firmware/capability version, and authorization context.

Reject stale, duplicated, expired, out-of-range, or wrong-target commands. Keep
telemetry and diagnostics available when command output is disabled.

## Connectivity and fail-safe behavior

Treat Wi-Fi, wired serial, UDP, and other transports as lossy unless delivery
and freshness are explicitly verified. Use bounded queues, sequence numbers,
heartbeats, retry limits, and a clear offline state. Loss of the control link,
watchdog reset, brownout, malformed message, or firmware mismatch must put
physical outputs into their defined safe state and require explicit re-arm.

Do not let boot completion, network reconnection, or automatic retry energize a
fixture or actuator. Hardware interlocks and independent emergency-stop paths
remain outside the network protocol.

## Firmware and configuration updates

Treat firmware and device configuration as versioned artifacts. Verify integrity,
compatibility, and rollback behavior before activation. Stage updates without
changing the active output configuration, and keep a recovery path if an update
is interrupted. Never update an endpoint during an armed show unless the show
plan explicitly models and authorizes that operation.

## Qualification scenarios

1. Run a simulated endpoint through discovery, identity verification, telemetry,
   command rejection, and safe shutdown.
2. Exercise packet loss, duplication, reordering, delay, reconnect, watchdog
   reset, and brownout behavior.
3. Verify that firmware/capability mismatches and invalid pin or range requests
   cannot arm outputs.
4. Interrupt an update and confirm rollback or safe recovery with outputs
   disabled.
5. Confirm that a fresh session and explicit operator authorization are required
   after reboot, reconnect, or safety fault.

## Integration boundary

Begin with read-only telemetry and a simulator. Add output control only through
an adapter that exposes device identity, capability, link health, command age,
and armed state. Arduino-ESP32 is an implementation option, not a requirement
for the StageMesh core or its software-only release gates.

The Arduino-ESP32 repository is distributed under LGPL-2.1 according to its
project metadata; review license obligations before bundling code or binaries.
