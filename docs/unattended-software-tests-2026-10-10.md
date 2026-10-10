# Unattended software checks — 2026-10-10

Base: current `main` at `63dfbe7caf378d205d8b00a1004548a97dd9caa0` (PR #151), plus the template interchange changes in this pull request. This session runs in a managed Linux x86-64 container, Python 3.12.14. It has no connection to the operator's Windows PC or attached devices. Source-native tests use pinned CMake 4.4.3; the frozen runtime uses pinned PyInstaller 6.16.0. Tool installation and builds use temporary directories.

## Results

| Check | Result | Scope / limitation |
| --- | --- | --- |
| Fresh release native build, RT instrumentation enabled, CTest | **5/5 passed** | Native tests, current ABI, capture-service owner, MIDI-input owner and MIDI-smoke evidence; no physical endpoint qualification. |
| Fresh ASan/UBSan native build and CTest | **5/5 passed** | No reported memory or undefined-behavior failures. Leak detection disabled by the script's default. |
| Native-backed complete Python discovery | **827 discovered; 826 passed; 1 skipped** | The isolated-rootfs ownership exercise requires its privileged opt-in. All native tests ran using the built engine. |
| Complete release gate with privileged opt-in | **Failed: 826 passed, 1 failed** | The ownership test cannot initialize `sudo`: `setresuid(-1, 1, -1): Invalid argument`. The release wrapper correctly refuses to pass with a failure or skip. |
| Direct isolated-rootfs package exercise as root | **Blocked** | `systemd-tmpfiles` cannot change staged state ownership: `fchownat() ... failed: Invalid argument`. No ownership bypass or acceptance was applied. |
| Frozen Linux desktop runtime build and smoke | **Passed** | Reserved-port refusal and child cleanup; authentication; template persistence across restart; corrupt-store fencing and recovery; graceful shutdown. This tests the frozen sidecar, not an installed Tauri app or a clean host. |
| Actual engine stdio authentication/dispatch smoke | **Passed** | Missing/wrong token rejected, authenticated commands and unknown-command rejection tested, quit completed. No outputs armed. |
| Linux target-OS engine reference smoke | **Passed** | Native binary present; platform reference only. |
| Core protocol conformance | **11 vectors passed** | `scripts/stagemesh-conformance.py`. |
| Session-channel conformance | **9 vectors passed** | `scripts/stagemesh-channel-conformance.py`. |
| Independent witness loopback exercise | **Passed** | Three process quorum; one-loss transfer and renewal; two-loss denial. Independent deployed failure domains remain unqualified. |
| Automation performance probes | **Passed** | 4,096 points, 8,192 prepared reads, 8,192 frames, 32 blocks; equivalent reads; timing is informational. |
| Template callback regressions | **15 passed** | Export, local mutation, import, server action, name and keyboard modules. |
| Python compilation, JSON schemas, frontend JS syntax, source hygiene, desktop version consistency, whitespace | **Passed** | Static software checks only. |
| Driver-catalog date audit, as of 2026-10-10 | **Passed: 5 current, 0 stale/invalid/unreviewed** | Checks the repository's review metadata; does not refresh vendor claims or qualify installed drivers. |
| Rendered Chromium workflow/accessibility-tree reference | **Blocked** | No Chromium executable. Playwright installed, but Chromium download failed with a truncated/non-ZIP archive. No rendered-browser or assistive-technology pass is claimed. |
| Live HTTP workload, default settings | **Failed twice** | Rate-policy model and normal burst passed; neither abuse burst observed a 429. Details below. |

## HTTP evidence requiring follow-up

Both executions used the unchanged command `python scripts/stagemesh-http-workload.py --json`, default counts/concurrency and acceptance thresholds. The first overlapped native builds; the second ran after those builds completed. The model admitted all 400 controller requests and rejected 802 attacker requests in both runs.

| Run | Normal burst | Normal p95 | Abuse burst | Abuse p95 | Throttled |
| --- | --- | --- | --- | --- | --- |
| Initial | 120/120 HTTP 200 | 43.863 ms | 320/320 HTTP 200 | 1,079.247 ms | 0 |
| Repeat | 120/120 HTTP 200 | 46.865 ms | 320/320 HTTP 200 | 1,132.946 ms | 0 |

These results do not establish why the live burst failed. Reproduce on a suitable host and inspect arrival timing/rate-limiter integration before accepting a fresh live rate-policy qualification. Historical SEC-037 evidence is retained, but this run supplies **no new live abuse qualification**. Neither workload run qualifies physical controllers or deployed LAN service. The rate policy and fail-closed criteria were not changed to obtain a pass.

## Reproduction

The release command was executed first without, then with, `STAGEMESH_PACKAGE_QUALIFY_SUDO=1`. The former leaves one explicit skip; the latter exercises and exposes the container's privilege restriction.

```sh
python scripts/release-check.py
STAGEMESH_PACKAGE_QUALIFY_SUDO=1 python scripts/release-check.py
python scripts/sanitizer-check.py
cmake -S . -B /tmp/stagemesh-unattended-build -DCMAKE_BUILD_TYPE=Release -DSTAGEMESH_BUILD_TESTS=ON -DSTAGEMESH_RT_QUALIFICATION=ON
cmake --build /tmp/stagemesh-unattended-build --parallel 2
ctest --test-dir /tmp/stagemesh-unattended-build --output-on-failure
STAGEMESH_NATIVE_ENGINE=/tmp/stagemesh-unattended-build/native/stagemesh_engine python ci/native_engine_stdio_smoke.py
python scripts/stagemesh-package-qualify.py --build-dir /tmp/stagemesh-unattended-build
python scripts/build-desktop-runtime.py --target x86_64-unknown-linux-gnu --native-engine /tmp/stagemesh-unattended-build/native/stagemesh_engine
python scripts/desktop-runtime-smoke.py --runtime desktop/src-tauri/binaries/stagemesh-runtime-x86_64-unknown-linux-gnu --native-engine desktop/src-tauri/binaries/stagemesh_engine-x86_64-unknown-linux-gnu --frontend frontend
STAGEMESH_NATIVE_ENGINE=/tmp/stagemesh-unattended-build/native/stagemesh_engine python scripts/platform-ci-smoke.py --output /tmp/stagemesh-platform-smoke.json
python scripts/stagemesh-conformance.py
python scripts/stagemesh-channel-conformance.py
python scripts/stagemesh-witness-qualify.py
python scripts/automation-performance.py --json
python scripts/stagemesh-driver-catalog-audit.py --as-of 2026-10-10 --json
python scripts/stagemesh-http-workload.py --json
```

The four pull-request workflows provide the separate hosted Linux/Windows/macOS and desktop packaging evidence; their exact-head results must be green before merge. They cannot qualify the operator's PC. Hardware, signing, legal approval, installed-app assistive technology, clean-host installation, deployed services and audible quality remain external gates.
