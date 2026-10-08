# StageMesh Master Project File

> Canonical continuity record for development sessions. Git remains the source of truth; this file is the compact handoff point when chat/session context runs out.

## Current baseline

- Repository: `colinatwood/stagemesh`
- Canonical branch: `main`
- Current milestone: **Attested desktop release candidates and external qualification execution**
- Verified `main` baseline as of 2026-10-08: `76000e8` (PR #124). Its exact-head commit `8127799` passed all four required workflows and their 13 jobs: StageMesh CI [37804106136](https://github.com/colinatwood/stagemesh/actions/runs/37804106136), Desktop [37804106072](https://github.com/colinatwood/stagemesh/actions/runs/37804106072), Platform Modules [37804106343](https://github.com/colinatwood/stagemesh/actions/runs/37804106343), and Native Device Lifecycle [37804105953](https://github.com/colinatwood/stagemesh/actions/runs/37804105953). Hosted software checks do not qualify signing, clean-host installation, physical audio/MIDI, accessibility, legal approval, deployed services, or audible quality.
- Repository README states that recovered Checkpoint 69 engine/backend/frontend/schemas/packaging/tests are consolidated with Checkpoint 70–83 platform work, with Checkpoint 84 documenting recovery provenance/integration limits. The current desktop release path now also records dependency inventory, signing readiness, exact artifact checksums, offline bundle verification, and graceful runtime teardown.

## Active backlog work (2026-10-08)

- PR #112 merged at `5522645afc2aba7ecd4b24b8b9aea3d0fd61ff73`, preserving the Windows operator observations without asserting source-bound hardware qualification. PR #113 was closed as superseded by the broader merged diagnostics implementation in PR #114.
- PR #120 is pending CI: separate Windows online/offline desktop bundles, plus exact channel-specific clean-host review. A current candidate requires seven installer tracks (Windows NSIS/MSI for each channel, macOS DMG, Linux Debian/AppImage); historical indexes retain five tracks. All 71 desktop tests passed locally. The installation instructions now show all seven reports.
- PR #121 is pending CI: playback/capture smoke `--help` and `-h` exit before device discovery; unknown or extra arguments exit with usage status 2. Six CLI tests passed in the initial Windows device run (15/15 overall). A follow-up narrows macOS CTest exclusions to exact endpoint test names so safe CLI and playback service tests execute there; the updated head must pass before merge.
- PR #122 is pending CI: MIDI smoke JSON escapes device/configured names, reports `callbackDeliveryObserved`, and keeps `hardwareQualified:false`. The historical FLkey result remains unchanged, with its callback-only boundary explained. The portable C++17 regression test passed with warnings as errors; Python independently parsed the report and verified string round-tripping.
- Next action: inspect each exact PR head, resolve failures and merge only when all reported checks pass and the change is mergeable. Then record merged baseline evidence. Windows BOOM capture `0x800700AA`, live MIDI/hotplug, signing, legal, accessibility, and clean-host acceptance remain open; these changes do not resolve those external gates.

## Current native-evidence follow-up (2026-10-08)

PR #121 merged at `9910db8b5fef2d6eb3f003ca2e2e6ec0cf6ffa1c` after all 13 checks passed. Playback/capture smoke help now exits before device access, unknown arguments return usage status 2, and macOS CI includes the safe CLI and playback-service tests. PR #122 merged at `8e1f8afb8ebbec9e5b7ded91a0b1382a90614b5b` after all 13 checks passed; MIDI callback evidence now escapes JSON names, records `callbackDeliveryObserved`, and keeps hardware qualification false.

The read-only `scripts/native-host-evidence.py` collector is the next software follow-up. It records source snapshot/dirty state, binary/transcript file hashes, host version/architecture and existing device/driver inventory, without running tests or opening streams. It explicitly does not verify binary origin, transcript provenance, test success or hardware qualification. Five focused regression tests cover file preservation, dirty source detection, unavailable probes, no binary execution, and failed-write cleanup. The Windows observation guide contains the command and remaining owner-input requirements. The periodic-sine negative gain observation is now correctly left ambiguous between phase alignment and physical polarity inversion.

Next: finish exact-head CI and merge the collector when green, then record a fresh Windows session and preserve actual build/test transcripts. BOOM capture `0x800700AA`, MIDI/hotplug, clean-host installation, signing, legal, accessibility and other external gates remain open.

## Latest completed work

PR #47 added persistent stage-template editor/storage behavior and its validation path. PR #48 added `NativePlaybackService`, exact hashed endpoint activation for Windows WASAPI and macOS CoreAudio, fail-closed fence/service handling, full-engine output status/shutdown wiring, and a missing-endpoint plus owner-thread smoke test. PR #50 added `docs/backlog/StageMesh-Master-Backlog-Refresh-2026-10-03.xlsx`, preserving the original Checkpoint 83 workbook as a historical snapshot. PR #52 added `playbackLifecycleQualified` and `playback-evidence` requirements to the Windows/macOS external qualification tasks. PR #54 recorded the 25 open-row execution pass. PR #56 made AUD-034 an explicit `audio-conversion-quality` qualification task with numeric error, SNR, THD+N, continuity, and measurement artifacts. PR #58 added a named macOS `midi_hardware_smoke` target that attaches through the production CoreMIDI callback path and waits for a real FL Mini event. PR #60 fixed the callback refcon routing; the connected FLkey Mini then produced a real callback event on the Mac. PR #61 recorded clean-worktree BOOM endpoint lifecycle evidence at 48 kHz with 4-channel playback and 2-channel capture. The complete 50-item execution ledger is `docs/backlog-execution-2026-10-03-all-50.md`.

PR #103 [bundles the WebView2 Evergreen offline installer](https://github.com/colinatwood/stagemesh/pull/103) in Windows packages, guards `offlineInstaller` in desktop readiness, and documents the package-size/connectivity tradeoff. Its 13-check matrix passed before merge; fresh post-merge Windows, macOS, and Linux packages plus the SHA-256 release index are recorded in the current-main handoff below. This remains package-build evidence; a no-network install on a clean host is still open.

PR #110 recorded a third 100-entry executable-readiness pass against merged main and preserved the distinction between software evidence and external qualification. The complete backlog pass confirms 24 previously Done rows against their recorded verification and preserves all 25 non-Done rows at their existing statuses. AUD-034 now has a dedicated external conversion-quality evidence contract and a deterministic helper that measures aligned reference/capture WAV files without asserting qualification. The full engine now has software-level native capture, MIDI, and playback ownership paths. The release-hardening path verifies and attests each downloadable desktop bundle and binds the exact Windows, macOS, and Linux manifests into one commit/version-specific unsigned CI candidate. Cross-platform clean-host evidence collection is now the active external slice; the broad Python suite passes 777 tests with 24 expected skips. Target hardware, audible output quality, recording quality, signing, legal review, clean-host installation, accessibility, and physical device qualification remain open.

The 2026-10-07 Windows host observation is preserved in `docs/windows-native-observation-2026-10-07.md`. It records 12 non-capture native tests passing and a repeatable BOOM capture failure with `HRESULT 0x800700AA` (`ERROR_BUSY`) while keeping capture and MIDI qualification open because the run lacked source/build binding and complete host evidence. PR #114 now emits signed decimal plus canonical eight-digit hexadecimal HRESULTs consistently from Windows endpoint streaming, audio preflight, and device enumeration; the formatter has platform-neutral regression coverage.

PR #114 closes the software gap around loopback-port collisions: server bind failure now always closes the runtime and native child, and the packaged-runtime smoke reserves the selected port, requires a fail-closed nonzero exit without credential disclosure, then releases the port and proves the same package/data directory can start, authenticate, and shut down cleanly. The broad Python suite passes 780 tests with 24 expected skips. Windows, macOS, and Ubuntu packaged sidecar exercises passed in the PR desktop workflow.

PR #116 extends that exact packaged-runtime smoke through a persisted stage-template lifecycle. It creates a template through the packaged API, gracefully stops the runtime, starts the same target-tagged package against the same data directory, and requires the template identity, name, revision, state, and normalized object payload to survive. All 13 PR checks passed, including Windows, macOS, and Ubuntu package exercises and cross-platform release-candidate binding. This is software/package evidence only; PKG-033 clean-host installation, upgrade, and uninstall remain open.

PR #118 makes stage-template corruption fail closed instead of silently loading an empty store. Malformed JSON, invalid persisted schema, and an incomplete same-directory temporary write now fence startup while preserving the source evidence. The exact packaged-runtime smoke proved corrupt-store refusal, unchanged corrupt bytes, exact known-good restoration, and unchanged template recovery on Windows, macOS, and Ubuntu. The broad Python suite passes 783 tests with 24 expected skips. Installed clean-host recovery remains open.

PR #120 splits Windows desktop candidates into explicit `online` and `offline` WebView2 distribution channels and binds the channel through artifact manifests, signing-readiness reports, download verification, the cross-platform release index, and clean-host review. CI now requires Linux/standard, macOS/standard, Windows/online, and Windows/offline bundles for a current release index. Clean-host review requires seven distinct package/channel tracks: Windows NSIS and MSI for each channel, macOS, Linux Debian, and Linux AppImage. The broad Python suite passes 790 tests with 24 expected skips, and all four required workflows and their 13 jobs passed. These are unsigned package/software candidates only; no clean-host, signing, hardware, accessibility, legal, deployed-service, or audible-quality gate is closed.

PR #124 closes the remaining self-description gap in those clean-host evidence files. Windows collectors now require and record the manifest-declared `online` or `offline` channel; macOS and Linux collectors require and record `standard`; and the cross-platform reviewer rejects both missing and mismatched channel claims for current indexes while preserving legacy-index compatibility. The broad Python suite passes 792 tests with 24 expected skips, and all four required workflows and their 13 jobs passed. This is evidence-contract hardening only and does not qualify an installed host or any external release gate.

## Build / verification entry points

From repository root:

```bash
cmake -S . -B build
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

Linux developer-alpha software gate:

```bash
python scripts/release-check.py
```

Install release-check build requirements from `requirements-release.txt` and provide Node.js.

## Important qualification boundary

Hosted/software evidence does **not** by itself qualify physical audio/MIDI hardware, licensed plugins, deployed services, installed packages, Windows/macOS runtime behavior, or other external acceptance inputs. Keep those claims explicit and fail closed. See `docs/remaining-data-requirements.md` and the external qualification tooling/evidence workflow before closing hardware/platform backlog items.

## Continuity protocol

Use this file to prevent progress loss when a ChatGPT/project session reaches its context or storage limit:

1. **At the start of work:** read `PROJECT_MASTER.md`, then inspect the latest commits on `main` and any active PR/branch.
2. **Before substantial work:** create/use a checkpoint branch rather than relying on chat state.
3. **After each meaningful checkpoint:** commit code/tests/docs to GitHub. Do not leave the only copy of progress in chat.
4. **Before ending or when context is getting crowded:** update this file with the new baseline commit, completed checkpoint, verification status, unresolved blockers, and exact next action; commit that update.
5. **Recovery rule:** if chat history conflicts with Git, Git wins. Reconstruct state from `main`, recent PRs, this file, README, changelog, and checkpoint docs.
6. **No false completion:** distinguish software/reference qualification from physical/target-environment qualification.

## Next-session handoff

- **Verified baseline:** `76000e85dd7043635ae03d95fc76f5366eade054` (PR #124 merged). Exact-head commit `8127799e403327cd46e8499c320b8eadd0598211` passed all four required workflows and their 13 jobs, including Linux/standard, macOS/standard, Windows/online, and Windows/offline packaging plus the final cross-platform release-index binding. These remain unsigned CI candidates; they do not qualify hardware, signing/notarization, clean-host installation, accessibility, legal approval, deployed services, or audible quality.
- **Native capture/playback services:** `NativeCaptureService` and `NativePlaybackService` own their monitor, execution fence, callback/render context, activation, service, and close ordering on an owner thread. A clean main worktree produced BOOM-compatible silent endpoint evidence: playback 25 callbacks/12,800 frames/4 channels and capture 26 callbacks/13,312 frames/2 channels at 48 kHz/512 frames, with topology stop/rearm checks passing. Physical output, audible quality, and recording quality remain unqualified.
- **Windows follow-up:** The observed BOOM capture failure is `0x800700AA` (`ERROR_BUSY`), not a qualified capture result. Re-run from a recorded source commit after closing applications that may own the input endpoint and capture the Windows build, BOOM driver/firmware, Apogee Control version, endpoint format/exclusive-mode settings, and full CTest transcript. The updated native diagnostic paths retain both decimal and hexadecimal HRESULT forms.
- **Native MIDI ingress:** A fixed-capacity MPMC queue handles concurrent callbacks, and `MidiInputOwner` owns discovery, polling, attach/detach commands, periodic identity reconciliation, and shutdown on a dedicated worker. The macOS FLkey Mini smoke now has real callback delivery evidence (`eventsObserved:1`, `callbackMessages:1`); physical hotplug/topology-loss and audio qualification remain open.
- **Template persistence:** The stage-template editor and persistent API path are present, with publication kept separate from physical output arming. PR #116 proves a created template survives graceful restart of the exact packaged runtime on Windows, macOS, and Ubuntu CI. PR #118 adds fail-closed malformed-store/schema/temporary-write detection and proves exact-byte restoration through the same packaged matrix. This does not substitute for recovery evidence from an installed package on a clean host.
- **SDK build helpers:** `scripts/build-native.sh` accepts CMake generator/toolchain/configuration arguments, keeps CTest on by default, and requires explicit opt-out for cross-builds. Older Windows SDK headers can compile without optional Configuration Manager notifications, with that availability reported separately. Details: `docs/sdk-builds.md`.
- **Backlog workbook:** `docs/backlog/StageMesh-Master-Backlog-Refresh-2026-10-03.xlsx` records PR #47/#48 evidence against AUD-035, AUD-036, DEV-033, and DEV-034. Those rows remain In Progress because physical endpoint/readback and live hotplug evidence are still open.
- **25-row execution pass:** `docs/backlog-execution-2026-10-03.md` records the earlier 25 open-row pass. `docs/backlog-execution-2026-10-03-all-50.md` reconciles all 49 workbook items plus the inventory-control record for the requested 50-item pass; 24 Done rows retain their recorded evidence and 25 non-Done rows remain gated.
- **Desktop release hardening:** PR #84 packages `verify-download.py` with every desktop bundle and checks exact manifests, checksums, safe paths, and signing-report binding without claiming publisher authenticity. PR #85 makes desktop teardown request authenticated loopback shutdown, verifies clean sidecar exit in the package smoke, and keeps a bounded force-termination fallback. PR #120 makes the desktop workflow re-verify four channel-bound CI bundles—Linux/standard, macOS/standard, Windows/online, and Windows/offline—then emits a SHA-256-bound release-candidate index for one source commit and version, attests the exact bundle subjects and CycloneDX SBOMs, and gives the final index its own provenance attestation. It does not create a GitHub Release or override signing, legal, clean-host, accessibility, deployed-service, audible-quality, or hardware gates.
- **Port-collision recovery:** PR #114 adds deterministic packaged-runtime collision/restart coverage and ensures an HTTP bind failure closes the native child. The exact packaged smoke passed on Windows, macOS, and Ubuntu, so EX3-037/038 now have CI/software evidence; this does not replace clean-host installation or production recovery exercise.
- **Cross-platform clean-host evidence:** the desktop bundles package fail-closed collectors for Windows 11 x64, macOS 14+ Apple Silicon, and Ubuntu 22.04/24.04 x64. They require and record exact installer/manifest/channel binding, hashed runner identity, installed state, and baseline/install/restart/real-upgrade/uninstall phases. The reviewer rejects missing or mismatched channel claims for current release indexes. A current candidate requires seven separate evidence reports: Windows online/offline NSIS and MSI, macOS, Linux Debian, and Linux AppImage. Complete evidence is only eligible for owner review; it cannot mark PKG-033 qualified.
- **Exact next action:** Repeat the BOOM capture test on Windows from merged commit `76000e8` with the source revision and host/device fields listed in `docs/windows-native-observation-2026-10-07.md`; preserve `0x800700AA` as an open endpoint-ownership/configuration diagnosis unless the bound rerun resolves it. Continue the exact attested-candidate clean-host exercises on fresh Windows 11 x64, macOS 14+ Apple Silicon, and Ubuntu 22.04/24.04 x64 hosts. Exercise Windows online/offline NSIS and MSI, macOS, Linux Debian, and Linux AppImage as seven separate tracks; record baseline, install, readiness, save/restart recovery, and uninstall evidence. Keep real-version upgrade phases open until a distinct prior StageMesh desktop version exists. In parallel, run the physical BOOM loopback in `docs/audio-conversion-quality.md`; do not close either gate from software-only evidence.
- **External evidence still needed:** AUD-034 conversion measurements, physical audio/MIDI, deployed LAN/TLS/IdP, licensed plugin fixtures, clean-host release qualification, assistive-technology exercise, owner license decisions, and independent-host witness evidence. See `docs/remaining-data-requirements.md`.

## Backup policy

The GitHub repository is the durable project backup. A checkpoint is not considered safely preserved until its source changes and this continuity record (when the handoff changes) are committed to GitHub. Chat transcripts are working context, not project storage.


## Release readiness update — 2026-10-07

The application is suitable for controlled developer testing with unsigned CI candidates. Public end-user release remains gated on the following evidence:

- Clean-host installation, readiness, persistence recovery, upgrade, and uninstall on Windows 11 x64, macOS 14+ Apple Silicon, and Ubuntu 22.04/24.04 x64.
- Seven separate package/channel exercises bound to the exact release-candidate index: Windows online/offline NSIS and MSI, macOS, Linux AppImage, and Linux Debian.
- Apogee BOOM 48 kHz/24-bit balanced-TRS playback/capture measurements, including aligned WAV, SNR, THD+N, continuity, latency, and dropout artifacts.
- FLkey Mini event, disconnect, reconnect, and topology-loss evidence.
- NVDA/VoiceOver and keyboard/focus accessibility exercises.
- Owner license/notice review, Windows signing, Apple signing/notarization, and Linux package-signing policy.
- Exact signed-artifact re-verification and a versioned public release.

The 451 MB combined offline Windows NSIS/MSI archive remains a distribution tradeoff. PR #120 now produces separate smaller online and self-contained offline channels and binds each to its own manifest and evidence track. Hosted CI remains software evidence and does not close physical, clean-host, accessibility, legal, signing, deployed-service, or audible-quality gates.
