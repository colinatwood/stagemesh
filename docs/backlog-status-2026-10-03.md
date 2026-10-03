# StageMesh backlog status refresh

As of 2026-10-03, based on `main` at `2c16b01fa2d20d7b525429b03fe3bd2aa2bf602c`.

## Work now on main

- PR [#41](https://github.com/colinatwood/stagemesh/pull/41) added a browser stage-template editor with local drafts, presets, JSON import/export, plus a readiness summary. This is a frontend workflow. The readiness cards do not qualify hardware or deployed services.
- PR [#42](https://github.com/colinatwood/stagemesh/pull/42) added backend stage-template list, get, create, validate, and publish operations backed by versioned draft records. Validation bounds the object list and coordinates. Responses explicitly keep physical outputs disarmed.
- Existing Checkpoint 86 capture and MIDI work remains software integration evidence. Target-hardware behavior, recording quality, and physical qualification stay open.

## Validation status

- Linux RT release gate and native memory/undefined-behavior checks passed on PR #42 merge commit `2c16b01`.
- macOS Apple Silicon build, platform-contract checks, and target-OS smoke passed on that run. Hosted macOS endpoint limitations still apply.
- Windows x64 compiled the engine, but CTest stopped at `device_lifecycle` because the hosted environment reported `native MIDI discovery/notifications unavailable`. The same failure appears on PR #41 run [36876848933](https://github.com/colinatwood/stagemesh/actions/runs/36876848933) and PR #42 run [36878362465](https://github.com/colinatwood/stagemesh/actions/runs/36878362465). The platform smoke and later steps were skipped on those two runs. PR #43's separate Native Device Lifecycle workflow later passed on both Windows and macOS ([run 37142053993](https://github.com/colinatwood/stagemesh/actions/runs/37142053993)). This conflicts with the earlier Windows failures. The full PR #43 StageMesh CI Windows lane is still running (PR run [37142054006](https://github.com/colinatwood/stagemesh/actions/runs/37142054006); post-merge run [37142125979](https://github.com/colinatwood/stagemesh/actions/runs/37142125979)). Keep the discrepancy open until that lane completes; a hosted pass does not qualify physical devices.

## Ordered next work

1. Close the Windows CI discrepancy. The separate native lifecycle workflow passed on PR #43, but the full StageMesh CI Windows lane is pending. If it passes, record that hosted result while keeping platform qualification boundaries. If it fails, compare runner capabilities and test assumptions without weakening supported-API checks.
2. Finish stage-template persistence end to end. Connect the frontend editor to the backend; add the missing update/delete behavior and revision checks; cover malformed, oversized, stale-revision, restart, and persistence-failure cases. Keep template publishing separate from hardware arming and show authority.
3. Refresh the Checkpoint 83 backlog workbook from the current source and evidence, mapping each changed feature to its accepted backlog row before changing statuses or totals. The workbook's `25 open / 22 P0` figures are a Checkpoint 83 snapshot and are not current totals.
4. Continue external qualification in the established order: target audio/MIDI hardware and recording quality; deployed LAN/TLS/IdP; licensed-plugin fixtures and platform binders; clean-host package/service operation; assistive-technology exercise; owner license decisions and independent-host witness evidence.

## Status rules

- Do not mark physical audio/MIDI, licensed-plugin compatibility, installed-package behavior, deployed LAN/TLS/IdP, or assistive-technology work complete based on hosted software checks.
- Keep `fullEngineIntegrated: false` until the native capture and MIDI owners have been exercised through the real engine lifecycle on target operating systems.
- The Checkpoint 83 workbook remains the last itemized backlog snapshot. This refresh records current implementation and CI evidence without inventing row mappings or recalculating its counts.
