# StageMesh backlog status refresh

As of 2026-10-03, based on `main` at `d33159320fb916106036a4d9b4135fd3b0020e25`.

## Work now on main

- PR [#41](https://github.com/colinatwood/stagemesh/pull/41) added a browser stage-template editor with local drafts, presets, JSON import/export, plus a readiness summary. The readiness cards do not qualify hardware or deployed services.
- PR [#42](https://github.com/colinatwood/stagemesh/pull/42) added backend stage-template list, get, create, validate, and publish operations backed by versioned draft records. Validation bounds the object list and coordinates. Responses explicitly keep physical outputs disarmed.
- PR [#46](https://github.com/colinatwood/stagemesh/pull/46) aligned the full CI Windows native-test environment with the unavailable-MIDI capability gate.
- PR [#47](https://github.com/colinatwood/stagemesh/pull/47) added persistent stage-template editor/storage behavior and its validation path.
- PR [#48](https://github.com/colinatwood/stagemesh/pull/48) integrated target-OS native playback into the full engine through `NativePlaybackService`, with exact hashed endpoint selection, fail-closed lifecycle handling, status/shutdown wiring, and owner-thread smoke coverage.
- Existing capture and MIDI work remains software integration evidence. Target-hardware behavior, recording quality, audible output, and physical qualification stay open.

## Validation status

- Fresh Platform Modules run [37151827147](https://github.com/colinatwood/stagemesh/actions/runs/37151827147) passed.
- Fresh Native Device Lifecycle run [37151827154](https://github.com/colinatwood/stagemesh/actions/runs/37151827154) passed, including Windows and macOS target-OS build/smoke coverage.
- Fresh full StageMesh CI run [37151827197](https://github.com/colinatwood/stagemesh/actions/runs/37151827197) passed Linux RT release, macOS Apple Silicon build/platform smoke, and Windows x64 build/platform smoke.
- These are hosted software checks. They do not qualify physical audio/MIDI hardware, audible output quality, deployed services, licensed plugins, or target-environment behavior.

## Ordered next work

1. Refresh the Checkpoint 83 backlog workbook from the current source and evidence, mapping each changed feature to its accepted backlog row before changing statuses or totals. The workbook's `25 open / 22 P0` figures are a Checkpoint 83 snapshot and are not current totals.
2. Continue target-environment qualification: exercise native audio/MIDI/playback lifecycle on representative hardware and capture evidence for device identity, topology loss, callback/render behavior, recording quality, and audible output.
3. Continue external qualification in the established order: deployed LAN/TLS/IdP; licensed-plugin fixtures and platform binders; clean-host package/service operation; assistive-technology exercise; owner license decisions and independent-host witness evidence.

## Status rules

- Do not mark physical audio/MIDI, licensed-plugin compatibility, installed-package behavior, deployed LAN/TLS/IdP, or assistive-technology work complete based on hosted software checks.
- Keep software and physical qualification claims separate: PR #48 proves hosted target-OS integration and lifecycle smoke, not real hardware output or recording quality.
- The Checkpoint 83 workbook remains the last itemized backlog snapshot until it is refreshed from current evidence.
