# Core 5.10.5 software validation

Date: 2026-09-11. This checkpoint supersedes the pending CMake/CTest validation
notes recorded for Core 5.10.1 through 5.10.4. It remains a local Linux developer
alpha source checkpoint, not a stage-qualified release or a binary installer.

## Toolchain

| Tool | Observed version |
| --- | --- |
| CMake / CTest | 4.4.3 |
| GNU C / C++ | 13.3.0 |
| Python | 3.12.14 |
| Node.js | 24.19.0 |

The pinned `requirements-release.txt` restored the missing build tools. Each gate
configured and built its own new temporary tree rather than reusing prior objects.

## Results

`python3 scripts/release-check.py` passed with Release configuration and
`STAGEMESH_RT_QUALIFICATION=ON`. The gate now supplies
`STAGEMESH_REQUIRE_RT_QUALIFICATION=1`, requiring the native handshake to advertise
enabled probes. Outside release mode, protocol tests accept either probe mode
provided the handshake and audit status agree.

- Native CTest: 2 of 2 targets passed, including the current C ABI smoke test.
- Python: 316 tests passed, no skipped coverage.
- Public schemas: all 104 JSON files parsed.
- Frontend: JavaScript syntax checks passed.
- Automation: deterministic work budget and probe-frame equivalence passed.

`python3 scripts/sanitizer-check.py` also passed both native CTest targets in a
fresh Debug build under AddressSanitizer and UndefinedBehaviorSanitizer. This
separate build uses ordinary, non-qualification mode. Leak detection was disabled;
this run provides no LeakSanitizer evidence.

## Remaining work

Authorized recovery/rejoin for a persistently fenced node remains the next safety
item. Witness independence, response authentication, clock uncertainty, named
hardware latency/soak tests, and actual installer deployment remain separate
qualification work. These software gates do not establish those properties.
