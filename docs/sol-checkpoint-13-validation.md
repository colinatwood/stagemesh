# Sol backlog checkpoint 13 validation

This checkpoint closes the remaining software-only DAW temporary-resource class.
Each isolated plugin adapter now receives private per-instance scratch owned by the
parent's exact boot/process-start identity. Normal close and all caught startup
failures remove it; parent crashes leave conservative, observable recovery evidence.

Failed handshakes, malformed replies and watchdog timeouts immediately reap the
child process and leave the effect bypassed. Adapter stderr cannot back-pressure the
protocol. Lifecycle status reports bounded active-host audit, exit/forced-kill
counters and scratch pressure without process IDs or paths. No automatic restart or
physical-output arming is introduced.

The configured scratch threshold gates new host admission and reports over-budget
state, but is not an operating-system disk quota. Hostile plugin containment,
licensed product fixtures and Windows/macOS launch hardening remain qualification
work rather than completed support claims.

## Checks

- 395 Python unit/integration tests passed without skips with the qualification
  native engine selected.
- `stagemesh_native_tests` and `stagemesh_current_abi_smoke` passed.
- All 113 JSON schemas and the OpenAPI document parsed.
- Frontend JavaScript syntax and the Production DOM workflow harness passed.

No native sources changed. The runtime still lacks `cmake` and `ctest`, so this
checkpoint exercised the existing freshly rebuilt native binaries directly rather
than repeating a clean configure or sanitizer build.
