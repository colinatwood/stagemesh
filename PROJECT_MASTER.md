# StageMesh Master Project File

> Canonical continuity record for development sessions. Git remains the source of truth; this file is the compact handoff point when chat/session context runs out.

## Current baseline

- Repository: `colinatwood/stagemesh`
- Canonical branch: `main`
- Baseline milestone: **Checkpoint 86 — persistent templates and target-OS audio lifecycle integration**
- Latest main baseline: `b600e307` — PR #50 added the refreshed StageMesh-named backlog workbook after PR #48 integrated the target-OS native playback service and PR #47 added persistent stage-template editor/storage behavior. Fresh hosted checks passed Platform Modules, Native Device Lifecycle, Linux RT release, macOS Apple Silicon, and Windows x64. This remains hosted software evidence, not physical device qualification. See `docs/backlog-status-2026-10-03.md`.
- Repository README states that recovered Checkpoint 69 engine/backend/frontend/schemas/packaging/tests are consolidated with Checkpoint 70–83 platform work, with Checkpoint 84 documenting recovery provenance/integration limits.

## Latest completed work

PR #47 added persistent stage-template editor/storage behavior and its validation path. PR #48 added `NativePlaybackService`, exact hashed endpoint activation for Windows WASAPI and macOS CoreAudio, fail-closed fence/service handling, full-engine output status/shutdown wiring, and a missing-endpoint plus owner-thread smoke test. PR #50 added `docs/backlog/StageMesh-Master-Backlog-Refresh-2026-10-03.xlsx`, preserving the original Checkpoint 83 workbook as a historical snapshot.

The full engine now has software-level native capture, MIDI, and playback ownership paths. Target hardware, audible output quality, recording quality, and physical device qualification remain open.

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

- **Latest main:** `b600e307` (PR #50, following PR #48). Platform Modules run [37151827147](https://github.com/colinatwood/stagemesh/actions/runs/37151827147), Native Device Lifecycle run [37151827154](https://github.com/colinatwood/stagemesh/actions/runs/37151827154), and full CI run [37151827197](https://github.com/colinatwood/stagemesh/actions/runs/37151827197) passed. The hosted artifacts do not qualify physical target hardware.
- **Native capture/playback services:** `NativeCaptureService` and `NativePlaybackService` own their monitor, execution fence, callback/render context, activation, service, and close ordering on an owner thread. Exact hashed identity selection and fail-closed topology-loss behavior are integrated. Physical target execution remains unqualified.
- **Native MIDI ingress:** A fixed-capacity MPMC queue handles concurrent callbacks, and `MidiInputOwner` owns discovery, polling, attach/detach commands, periodic identity reconciliation, and shutdown on a dedicated worker. Target callback delivery and topology-loss execution still require target hardware.
- **Template persistence:** The stage-template editor and persistent API path are present, with publication kept separate from physical output arming. Continue edge-case coverage and lifecycle integration as needed.
- **SDK build helpers:** `scripts/build-native.sh` accepts CMake generator/toolchain/configuration arguments, keeps CTest on by default, and requires explicit opt-out for cross-builds. Older Windows SDK headers can compile without optional Configuration Manager notifications, with that availability reported separately. Details: `docs/sdk-builds.md`.
- **Backlog workbook:** `docs/backlog/StageMesh-Master-Backlog-Refresh-2026-10-03.xlsx` records PR #47/#48 evidence against AUD-035, AUD-036, DEV-033, and DEV-034. Those rows remain In Progress because physical endpoint/readback and live hotplug evidence are still open.
- **Exact next action:** Exercise native audio/MIDI/playback lifecycle on representative Windows/macOS hardware and capture device identity, topology-loss, callback/render, recording-quality, and audible-output evidence. Then continue external qualification in the established order.
- **External evidence still needed:** Physical audio/MIDI, deployed LAN/TLS/IdP, licensed plugin fixtures, clean-host release qualification, assistive-technology exercise, owner license decisions, and independent-host witness evidence. See `docs/remaining-data-requirements.md`.

## Backup policy

The GitHub repository is the durable project backup. A checkpoint is not considered safely preserved until its source changes and this continuity record (when the handoff changes) are committed to GitHub. Chat transcripts are working context, not project storage.
