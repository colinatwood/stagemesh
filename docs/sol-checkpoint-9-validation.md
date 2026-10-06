# Sol backlog checkpoint 9 validation

Validated 2026-09-11 in the available Linux development environment.

## Completed

- ALSA playback and capture query current hardware parameters after configuration.
- Requested and configured sample rate, period, channels and format are reported
  separately.
- Streams fail before start if configured parameters cannot be queried, exceed
  engine bounds, or require undeclared rate/channel conversion.
- The conversion planner requires separate choices for bounded sinc rate conversion,
  signed integer normalization and channel mapping.
- HTTP API, OpenAPI contract and UI opt-in controls expose the policy.

## Checks

- 378 Python unit/integration tests passed without skips with the rebuilt
  qualification native engine selected.
- `stagemesh_native_tests` and `stagemesh_current_abi_smoke` passed.
- All 110 JSON schemas and the OpenAPI document parsed.
- `frontend/app.js` passed the Node syntax check.
- The ALSA null endpoint returned a configured 31-frame period for a requested
  64-frame period; the protocol retained and tested both values.

The original pinned CMake executable is no longer installed. The three changed C++
translation units and native test object were rebuilt with the exact flags recorded
in the existing CMake build tree, then the generated link recipes were reproduced.
This is not a fresh CMake configure or CTest runner pass.

Physical conversion quality, real interface negotiation, integer/multichannel
adapters, latency and dropout remain unqualified without hardware. Windows and macOS
implementations also remain open.
