# StageForge Master Project File

> Canonical continuity record for development sessions. Git remains the source of truth; this file is the compact handoff point when chat/session context runs out.

## Current baseline

- Repository: `colinatwood/stagemesh`
- Canonical branch: `main`
- Baseline commit when this master file was introduced: `e79d8a1fbb9a3eb976cd325dbadb58cc51c457e6`
- Baseline milestone: **Checkpoint 85 — bridge native target-OS devices into full engine (incomplete in current tree)**
- Repository README states that recovered Checkpoint 69 engine/backend/frontend/schemas/packaging/tests are consolidated with Checkpoint 70–83 platform work, with Checkpoint 84 documenting recovery provenance/integration limits.

## Latest completed work

Checkpoint 85 was documented as merged to `main`, but the current tree does not contain the native bridge implementation required by its CMake configuration. The full-engine target-OS bridge therefore cannot currently configure or build in CI. The privacy-preserving identity contracts and related tests are present, but the native bridge qualification is not reproducible from this checkout.

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

At this baseline, restore the missing native bridge sources referenced by `native/devices.cmake` (`platform_audio_bridge.cpp` and `platform_audio_bridge_smoke.cpp`), then rerun the Windows/macOS native and full-tree CI gates. Only after those builds are green should the next checkpoint be started.

When advancing the project, replace this handoff section with:

- **Current checkpoint:** Checkpoint 85, native bridge incomplete in repository
- **Branch / PR:** `main`, PR #29 merged
- **Last known-good commit:** `8c01236`
- **Tests run / result:** 29 focused Python ownership/media/playback tests pass; native CI configuration fails because two bridge sources are missing
- **What changed:** Restored temporary ownership manifest imports and merged the fix
- **Open blockers / external evidence needed:** Restore `native/platform_audio_bridge.cpp` and `native/platform_audio_bridge_smoke.cpp`; then rerun native CI
- **Exact next action:** Recover the missing bridge implementation from the Checkpoint 85 source change or reconstruct it from its public interface and tests

## Backup policy

The GitHub repository is the durable project backup. A checkpoint is not considered safely preserved until its source changes and this continuity record (when the handoff changes) are committed to GitHub. Chat transcripts are working context, not project storage.
