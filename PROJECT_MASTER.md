# StageMesh Master Project File

> Canonical continuity record for development sessions. Git remains the source of truth; this file is the compact handoff point when chat/session context runs out.

## Current baseline

- Repository: `colinatwood/stagemesh`
- Canonical branch: `main`
- Baseline milestone: **Checkpoint 90 — verified macOS FLkey Mini CoreMIDI callback delivery**
- Latest main baseline: `2444b4d` — PR #60 fixed macOS CoreMIDI source callback routing by using the source connection refcon. A real FLkey Mini key event was observed on the Mac with `eventsObserved:1` and `callbackMessages:1`; this is MIDI callback evidence, not full physical audio qualification. See `docs/mac-flkey-midi-evidence-2026-10-03.md`.
- Repository README states that recovered Checkpoint 69 engine/backend/frontend/schemas/packaging/tests are consolidated with Checkpoint 70–83 platform work, with Checkpoint 84 documenting recovery provenance/integration limits.

## Latest completed work

PR #47 added persistent stage-template editor/storage behavior and its validation path. PR #48 added `NativePlaybackService`, exact hashed endpoint activation for Windows WASAPI and macOS CoreAudio, fail-closed fence/service handling, full-engine output status/shutdown wiring, and a missing-endpoint plus owner-thread smoke test. PR #50 added `docs/backlog/StageMesh-Master-Backlog-Refresh-2026-10-03.xlsx`, preserving the original Checkpoint 83 workbook as a historical snapshot. PR #52 added `playbackLifecycleQualified` and `playback-evidence` requirements to the Windows/macOS external qualification tasks. PR #54 recorded the 25 open-row execution pass. PR #56 made AUD-034 an explicit `audio-conversion-quality` qualification task with numeric error, SNR, THD+N, continuity, and measurement artifacts. PR #58 added a named macOS `midi_hardware_smoke` target that attaches through the production CoreMIDI callback path and waits for a real FL Mini event. PR #60 fixed the callback refcon routing; the connected FLkey Mini then produced a real callback event on the Mac. The complete 50-item execution ledger is `docs/backlog-execution-2026-10-03-all-50.md`.

The complete backlog pass confirms 24 previously Done rows against their recorded verification and preserves all 25 non-Done rows at their existing statuses. AUD-034 now has a dedicated external conversion-quality evidence contract. The full engine now has software-level native capture, MIDI, and playback ownership paths. Target hardware, audible output quality, recording quality, and physical device qualification remain open.

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

- **Latest main:** `2444b4d` (PR #60, following PR #59, PR #58, PR #56, PR #55, PR #54, PR #52, PR #50, and PR #48). Platform Modules run [37151827147](https://github.com/colinatwood/stagemesh/actions/runs/37151827147), Native Device Lifecycle run [37151827154](https://github.com/colinatwood/stagemesh/actions/runs/37151827154), and full CI run [37151827197](https://github.com/colinatwood/stagemesh/actions/runs/37151827197) passed. The hosted artifacts do not qualify physical target hardware.
- **Native capture/playback services:** `NativeCaptureService` and `NativePlaybackService` own their monitor, execution fence, callback/render context, activation, service, and close ordering on an owner thread. Exact hashed identity selection and fail-closed topology-loss behavior are integrated. Physical target execution remains unqualified.
- **Native MIDI ingress:** A fixed-capacity MPMC queue handles concurrent callbacks, and `MidiInputOwner` owns discovery, polling, attach/detach commands, periodic identity reconciliation, and shutdown on a dedicated worker. The macOS FLkey Mini smoke now has real callback delivery evidence (`eventsObserved:1`, `callbackMessages:1`); physical hotplug/topology-loss and audio qualification remain open.
- **Template persistence:** The stage-template editor and persistent API path are present, with publication kept separate from physical output arming. Continue edge-case coverage and lifecycle integration as needed.
- **SDK build helpers:** `scripts/build-native.sh` accepts CMake generator/toolchain/configuration arguments, keeps CTest on by default, and requires explicit opt-out for cross-builds. Older Windows SDK headers can compile without optional Configuration Manager notifications, with that availability reported separately. Details: `docs/sdk-builds.md`.
- **Backlog workbook:** `docs/backlog/StageMesh-Master-Backlog-Refresh-2026-10-03.xlsx` records PR #47/#48 evidence against AUD-035, AUD-036, DEV-033, and DEV-034. Those rows remain In Progress because physical endpoint/readback and live hotplug evidence are still open.
- **25-row execution pass:** `docs/backlog-execution-2026-10-03.md` records the earlier 25 open-row pass. `docs/backlog-execution-2026-10-03-all-50.md` reconciles all 49 workbook items plus the inventory-control record for the requested 50-item pass; 24 Done rows retain their recorded evidence and 25 non-Done rows remain gated.
- **Exact next action:** Set the Apogee BOOM as the Mac default input/output and rerun native playback/capture evidence with the device identity captured. Then continue the AUD-034 reference-signal measurement task; do not close physical audio or conversion-quality gates without the required measurements.
- **External evidence still needed:** AUD-034 conversion measurements, physical audio/MIDI, deployed LAN/TLS/IdP, licensed plugin fixtures, clean-host release qualification, assistive-technology exercise, owner license decisions, and independent-host witness evidence. See `docs/remaining-data-requirements.md`.

## Backup policy

The GitHub repository is the durable project backup. A checkpoint is not considered safely preserved until its source changes and this continuity record (when the handoff changes) are committed to GitHub. Chat transcripts are working context, not project storage.
