# StageMesh Master Project File

> Canonical continuity record for development sessions. Git remains the source of truth; this file is the compact handoff point when chat/session context runs out.

## Current baseline

- Repository: `colinatwood/stagemesh`
- Canonical branch: `main`
- Current milestone: **Attested desktop release candidates and external qualification execution**
- Verified baseline entering this milestone: `6e04f5f` — PR #99 made `PROJECT_MASTER.md` changes rebuild the desktop matrix and exact-source release-candidate attestation. The merged PR passed 13/13 checks, and the post-merge `main` run passed 8/8 checks; these software paths still do not qualify signing, clean-host installation, physical audio/MIDI, accessibility, legal approval, or audible quality.
- Repository README states that recovered Checkpoint 69 engine/backend/frontend/schemas/packaging/tests are consolidated with Checkpoint 70–83 platform work, with Checkpoint 84 documenting recovery provenance/integration limits. The current desktop release path now also records dependency inventory, signing readiness, exact artifact checksums, offline bundle verification, and graceful runtime teardown.

## Latest completed work

PR #47 added persistent stage-template editor/storage behavior and its validation path. PR #48 added `NativePlaybackService`, exact hashed endpoint activation for Windows WASAPI and macOS CoreAudio, fail-closed fence/service handling, full-engine output status/shutdown wiring, and a missing-endpoint plus owner-thread smoke test. PR #50 added `docs/backlog/StageMesh-Master-Backlog-Refresh-2026-10-03.xlsx`, preserving the original Checkpoint 83 workbook as a historical snapshot. PR #52 added `playbackLifecycleQualified` and `playback-evidence` requirements to the Windows/macOS external qualification tasks. PR #54 recorded the 25 open-row execution pass. PR #56 made AUD-034 an explicit `audio-conversion-quality` qualification task with numeric error, SNR, THD+N, continuity, and measurement artifacts. PR #58 added a named macOS `midi_hardware_smoke` target that attaches through the production CoreMIDI callback path and waits for a real FL Mini event. PR #60 fixed the callback refcon routing; the connected FLkey Mini then produced a real callback event on the Mac. PR #61 recorded clean-worktree BOOM endpoint lifecycle evidence at 48 kHz with 4-channel playback and 2-channel capture. The complete 50-item execution ledger is `docs/backlog-execution-2026-10-03-all-50.md`.

The complete backlog pass confirms 24 previously Done rows against their recorded verification and preserves all 25 non-Done rows at their existing statuses. AUD-034 now has a dedicated external conversion-quality evidence contract and a deterministic helper that measures aligned reference/capture WAV files without asserting qualification. The full engine now has software-level native capture, MIDI, and playback ownership paths. The release-hardening path verifies and attests each downloadable desktop bundle and binds the exact Windows, macOS, and Linux manifests into one commit/version-specific unsigned CI candidate. Cross-platform clean-host evidence collection is now the active external slice; the broad Python suite passes 777 tests with 24 expected skips. Target hardware, audible output quality, recording quality, signing, legal review, clean-host installation, accessibility, and physical device qualification remain open.

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

- **Verified baseline entering this checkpoint:** `6e04f5f` (PR #99, following PR #97–#98). The post-merge Platform Modules/Native Device Lifecycle/CI run [37536639174](https://github.com/colinatwood/stagemesh/actions/runs/37536639174), Desktop packaging/release-index run [37536639183](https://github.com/colinatwood/stagemesh/actions/runs/37536639183), and Cloudflare deployment all passed. The exact current-main artifacts are Windows `sha256:56e382ce7a33a77c42d0ee62e7e6a334b2981cff75e02ac713a1553d751f4378`, macOS `sha256:97affedb5eca10b151b842ff73bf558bc9c25f2bcddaa28fa30ba965f9d8929f`, Ubuntu `sha256:20eb3154f7d0cbe8e8af3aababe90cd167fa3a061d008ce54518fcd6ed93b492`, and release index `sha256:63aadaaa8dfaa854ce256b5d9518e4cd5303daffb1a9a3e54bf411c7ea591771`. The desktop jobs generated provenance and SBOM attestations for each exact platform bundle and the aggregate release-candidate index. The hosted artifacts do not qualify physical target hardware, signing, clean-host installation, accessibility, or legal approval.
- **Native capture/playback services:** `NativeCaptureService` and `NativePlaybackService` own their monitor, execution fence, callback/render context, activation, service, and close ordering on an owner thread. A clean main worktree produced BOOM-compatible silent endpoint evidence: playback 25 callbacks/12,800 frames/4 channels and capture 26 callbacks/13,312 frames/2 channels at 48 kHz/512 frames, with topology stop/rearm checks passing. Physical output, audible quality, and recording quality remain unqualified.
- **Native MIDI ingress:** A fixed-capacity MPMC queue handles concurrent callbacks, and `MidiInputOwner` owns discovery, polling, attach/detach commands, periodic identity reconciliation, and shutdown on a dedicated worker. The macOS FLkey Mini smoke now has real callback delivery evidence (`eventsObserved:1`, `callbackMessages:1`); physical hotplug/topology-loss and audio qualification remain open.
- **Template persistence:** The stage-template editor and persistent API path are present, with publication kept separate from physical output arming. Continue edge-case coverage and lifecycle integration as needed.
- **SDK build helpers:** `scripts/build-native.sh` accepts CMake generator/toolchain/configuration arguments, keeps CTest on by default, and requires explicit opt-out for cross-builds. Older Windows SDK headers can compile without optional Configuration Manager notifications, with that availability reported separately. Details: `docs/sdk-builds.md`.
- **Backlog workbook:** `docs/backlog/StageMesh-Master-Backlog-Refresh-2026-10-03.xlsx` records PR #47/#48 evidence against AUD-035, AUD-036, DEV-033, and DEV-034. Those rows remain In Progress because physical endpoint/readback and live hotplug evidence are still open.
- **25-row execution pass:** `docs/backlog-execution-2026-10-03.md` records the earlier 25 open-row pass. `docs/backlog-execution-2026-10-03-all-50.md` reconciles all 49 workbook items plus the inventory-control record for the requested 50-item pass; 24 Done rows retain their recorded evidence and 25 non-Done rows remain gated.
- **Desktop release hardening:** PR #84 packages `verify-download.py` with every desktop bundle and checks exact manifests, checksums, safe paths, and signing-report binding without claiming publisher authenticity. PR #85 makes desktop teardown request authenticated loopback shutdown, verifies clean sidecar exit in the package smoke, and keeps a bounded force-termination fallback. The desktop workflow now also re-verifies all three downloaded CI bundles, emits a SHA-256-bound release-candidate index for one source commit and version, attests the exact bundle subjects and CycloneDX SBOMs, and gives the final index its own provenance attestation. It does not create a GitHub Release or override signing, legal, clean-host, accessibility, or hardware gates.
- **Cross-platform clean-host evidence:** the desktop bundles package fail-closed collectors for Windows 11 x64, macOS 14+ Apple Silicon, and Ubuntu 22.04/24.04 x64. They record exact installer/manifest binding, hashed runner identity, installed state, and baseline/install/restart/real-upgrade/uninstall phases. Complete evidence is only eligible for owner review; it cannot mark PKG-033 qualified.
- **Exact next action:** Run the exact attested CI candidates on fresh Windows 11 x64, macOS 14+ Apple Silicon, and Ubuntu 22.04/24.04 x64 hosts. Exercise NSIS/MSI and AppImage/Debian separately; record baseline, install, readiness, save/restart recovery, and uninstall evidence. Keep real-version upgrade phases open until a distinct prior StageMesh desktop version exists. In parallel, run the physical BOOM loopback in `docs/audio-conversion-quality.md`; do not close either gate from software-only evidence.
- **External evidence still needed:** AUD-034 conversion measurements, physical audio/MIDI, deployed LAN/TLS/IdP, licensed plugin fixtures, clean-host release qualification, assistive-technology exercise, owner license decisions, and independent-host witness evidence. See `docs/remaining-data-requirements.md`.

## Backup policy

The GitHub repository is the durable project backup. A checkpoint is not considered safely preserved until its source changes and this continuity record (when the handoff changes) are committed to GitHub. Chat transcripts are working context, not project storage.
