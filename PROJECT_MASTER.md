# StageMesh Master Project File

> Canonical continuity record for development sessions. Git remains the source of truth; this file is the compact handoff point when chat/session context runs out.

## Current baseline

- Repository: `colinatwood/stagemesh`
- Canonical branch: `main`
- Baseline commit when this master file was introduced: `e79d8a1fbb9a3eb976cd325dbadb58cc51c457e6`
- Baseline milestone: **Checkpoint 85 — target-OS device discovery integration (native bridge smoke lane deferred)**
- Latest main baseline: `fad4995` — PR #44 reconciled Windows CI evidence. The standalone native lifecycle workflow passed, but full StageMesh CI again failed Windows `device_lifecycle` because MIDI discovery/notifications are unavailable. See `docs/backlog-status-2026-10-03.md`.
- Repository README states that recovered Checkpoint 69 engine/backend/frontend/schemas/packaging/tests are consolidated with Checkpoint 70–83 platform work, with Checkpoint 84 documenting recovery provenance/integration limits.

## Latest completed work

PR #41 added a local stage-template editor with presets, JSON import/export, and a readiness summary. PR #42 added backend list/get/create/validate/publish operations for persistent versioned drafts. Template publication does not arm physical outputs. See `docs/backlog-status-2026-10-03.md` for current CI state and ordered follow-up.

Checkpoint 85 was documented as merged to `main`. The full engine consumes the native `DeviceMonitor` through `AudioDeviceManager` and exports only hashed target-OS identity metadata. The separately named platform bridge smoke lane was absent, so its orphaned CMake references were removed; native device-monitor qualification remains the authoritative coverage.

PR #34 records a green validation baseline: 676 Python tests with the native engine configured and passing StageMesh Platform Modules, StageMesh Native Device Lifecycle, and StageMesh CI workflow runs.

Recent checkpoint-85 commits include:

- Link full engine to qualified target-OS device library.
- Bridge target-OS hashed audio identities into engine enumeration.
- Enumerate target-OS audio through native device monitor.
- Expose target-OS hashed MIDI identities through engine registry.
- Enumerate target-OS MIDI identities through native device monitor.
- Decode target-OS audio/MIDI identity evidence.
- Qualify full-engine target-OS device enumeration.
- Test full-engine hashed target-OS identity tokens.

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
5. **Recovery rule:** if chat history conflicts with Git, Git wins. Reconstruct state from `main`, recent commits/PRs, this file, README, changelog, and checkpoint docs.
6. **No false completion:** distinguish software/reference qualification from physical/target-environment qualification.

## Next-session handoff

- **Current checkpoint:** Checkpoint 86 capture and MIDI ownership work remains on `main`; PRs #41 and #42 then added stage-template frontend and backend slices. The Checkpoint 83 workbook is the last itemized backlog snapshot, not a current count. See `docs/backlog-status-2026-10-03.md`.
- **Latest main:** `fad4995` (PR #44 backlog evidence update; software baseline `2c16b01`). Linux release and memory/undefined-behavior checks passed; macOS build/smoke and the PR #43 native lifecycle workflow passed. The full PR #43 StageMesh CI Windows lane failed at `device_lifecycle` with unavailable MIDI discovery/notifications. Target-host hardware qualification remains separate.
- **Native capture service:** `NativeCaptureService` owns one stream's monitor, execution fence, callback context, activation, service and close ordering. The engine now constructs and drives it on a dedicated owner thread per active input. Idle service, unique selected-token resolution and callback-drain shutdown are integrated; physical target execution remains unqualified. Details: `docs/native-engine-service-loop.md`.
- **Native MIDI ingress:** A fixed-capacity MPMC queue handles concurrent callbacks, and `MidiInputOwner` now owns discovery, polling, attach/detach commands, periodic identity reconciliation, and shutdown on a dedicated worker. Linux tests submit 400 concurrent injections; CoreMIDI and WinMM source matching, callback delivery, close paths, and fail-closed missing-identity handling are implemented. Target callback delivery and topology-loss execution still require target hardware. Details: `docs/native-midi-callback-ingress.md`.
- **SDK build helpers:** `scripts/build-native.sh` accepts CMake generator/toolchain/configuration arguments, keeps CTest on by default, and requires explicit opt-out for cross-builds. Older Windows SDK headers can compile without optional Configuration Manager notifications, with that availability reported separately. Details: `docs/sdk-builds.md`.
- **Consolidation verification:** Linux engine and all Windows-target engine/device smoke executables compile and link. The Linux ABI smoke passes; the full native suite stops in an LE/UWB socket fixture under this workspace's socket restrictions. Focused capture-ingress and concurrent MIDI regressions are checked separately. Cross-builds are compile/link evidence only; Windows/macOS runtime qualification of this newer service/MIDI slice remains outstanding.
- **Naming:** Visible project, frontend, workflow, artifact and archive labels use StageMesh. Existing `STAGEFORGE_*` configuration, binary targets, API symbols and include paths remain compatibility identifiers.
- **Exact next action:** Resolve the Windows hosted `device_lifecycle` failure and rerun platform smoke. Then connect the stage-template editor to the persistent API, add update/delete and revision checks, and test failure/restart behavior. Continue target-OS engine capture/MIDI execution after the hosted gate; preserve `fullEngineIntegrated: false` until target lifecycle validation passes. See `docs/backlog-status-2026-10-03.md`.
- **External evidence still needed:** Physical audio/MIDI, deployed LAN/TLS/IdP, licensed plugin fixtures, clean-host release qualification, assistive-technology exercise, owner license decisions and independent-host evidence. See `docs/remaining-data-requirements.md`.

## Backup policy

The GitHub repository is the durable project backup. A checkpoint is not considered safely preserved until its source changes and this continuity record (when the handoff changes) are committed to GitHub. Chat transcripts are working context, not project storage.
