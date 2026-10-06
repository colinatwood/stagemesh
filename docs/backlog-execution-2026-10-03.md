# Open backlog execution record

As of 2026-10-03, this record covers the 25 rows that remain not Done in the refreshed Checkpoint 83 workbook. It records repository-supported progress and the evidence still required for external rows. It does not convert hosted checks into hardware, deployment, licensing, accessibility, or owner-decision qualification.

## Latest current-main hosted verification (2026-10-06)

After PR #100 merged, commit [145e9994f9f62a9d0a5fba0f000a0ff0f8e81cdf](https://github.com/colinatwood/stagemesh/commit/145e9994f9f62a9d0a5fba0f000a0ff0f8e81cdf) passed the current-main workflows:

- [StageMesh CI run 37542866404](https://github.com/colinatwood/stagemesh/actions/runs/37542866404): Windows x64 native build/tests/platform smoke, macOS Apple Silicon platform smoke, and Linux RT release gate: **all green**.
- [StageMesh Desktop run 37542866431](https://github.com/colinatwood/stagemesh/actions/runs/37542866431): Windows, macOS and Ubuntu packaging plus the cross-platform release-candidate index: **all green**.
- Fresh artifact digests are recorded here for exact-candidate review:
  - Windows: `sha256:85a042800d6d07285aa22a91b91f2f1b1779f6e40e5863a37eaac36ceee29dd1`
  - macOS: `sha256:2a0b1684298fed04f46b0152ec1f30c9298451c050f8ab89ffa57d7a65b58cef`
  - Ubuntu: `sha256:9db0290133e65425a556e3cf9c32ca5a7eb3a83bcf643acb71dd9a9025f53300`
  - Release index: `sha256:189b9f2fbbad17230fb51de5ee85e64745ea4a79d0a0f281a0e1c8701c833040`

These hosted checks establish build, packaging, provenance/SBOM and release-index evidence only. They do **not** qualify clean-host installation, signing/notarization, assistive technology, legal release decisions, physical audio/MIDI I/O, audible quality, licensed plugins, LAN/IdP/firewall deployment or independent witness failure domains. No backlog status is changed by this section; the remaining acceptance evidence is still listed below.

## Repository checks run

- `python3 -m unittest tests.test_native_engine tests.test_audio_backend_neutral_runtime tests.test_audio_identity tests.test_qualification_bundle tests.test_qualification_review tests.test_qualification_status`: **44 passed, 13 skipped**.
- `python3 -m compileall -q backend tests`: passed.
- `git diff --check`: passed.
- Windows/macOS native playback integration and target-OS lifecycle smoke passed in hosted CI runs [37151827154](https://github.com/colinatwood/stagemesh/actions/runs/37151827154) and [37151827197](https://github.com/colinatwood/stagemesh/actions/runs/37151827197). These runs do not qualify physical endpoints, audible output, recording quality, or live hotplug behavior.

## 25-row disposition

| ID | Current status | Execution result | Evidence still required |
| --- | --- | --- | --- |
| REC-033 | Blocked | External recovery gate identified; no independent multi-host exercise is available in the repository environment. | Witness, clock, output-state and one-witness-loss drill across separate hosts. |
| REC-034 | Blocked | External failure-domain gate identified; no physical witness deployment performed. | Independent host, power and network failure-domain exercise. |
| SEC-039 | Blocked | External witness deployment gate identified; no real clock/partition exercise performed. | Multi-host skew, partition, witness-loss and custody/rotation evidence. |
| AUD-034 | Blocked | External measurement gate identified; no reference-signal measurement performed. | Noise, distortion, phase continuity and resampling measurement suite. |
| AUD-035 | In Progress | PR #48 integrates Windows WASAPI playback ownership; hosted Windows build/lifecycle checks pass. | Selected physical endpoint readback/I/O and representative Windows audio qualification. |
| AUD-036 | In Progress | PR #48 integrates macOS CoreAudio playback ownership; hosted macOS build/lifecycle checks pass. | Selected physical endpoint readback, audible output and representative macOS audio qualification. |
| DEV-033 | In Progress | PR #48 integrates Windows `DeviceMonitor`/`DeviceExecutionFence` playback lifecycle; PR #52 adds the required playback evidence contract. | Live Windows PnP/MIDI hotplug, exact replacement and topology-loss evidence on target hardware. |
| DEV-034 | In Progress | PR #48 integrates macOS `DeviceMonitor`/`DeviceExecutionFence` playback lifecycle; PR #52 adds the required playback evidence contract. | Live CoreAudio/CoreMIDI churn, exact replacement and topology-loss evidence on target hardware. |
| DEV-035 | Deferred | External named-device soak identified; no physical hotplug soak performed. | Named-device hotplug soak with fail-closed recovery evidence. |
| LIVE-033 | Deferred | External streaming-voice soak identified; no long-duration named-hardware run performed. | Long-duration physical streaming-voice soak. |
| PLUG-033 | Blocked | External licensed-plugin gate identified; no licensed fixtures are available in the repository environment. | Licensed VST3/CLAP/LV2/AU live-audio matrix. |
| UX-035 | In Progress | External AT gate identified; no NVDA/VoiceOver exercise performed here. | Screen-reader/keyboard exercise with issue log and operator workflow evidence. |
| PKG-033 | In Progress | Repository packaging logic is testable, but no clean-host install/upgrade/uninstall run was performed. | Fresh VM/host package exercise with actual service boot. |
| PKG-034 | In Progress | Repository permission logic is testable, but no clean-host hardware namespace run was performed. | Clean-host service identity, permissions, udev/group and hardware evidence. |
| LEGAL-001 | Blocked | Owner decision required; no license choice was inferred. | Owner approval, published license and release-check validation. |
| PLUG-035 | Blocked | External Windows plugin gate identified; no licensed Windows fixtures are available. | Licensed Windows plugin matrix. |
| PLUG-036 | Blocked | External macOS plugin gate identified; no licensed macOS fixtures are available. | Licensed macOS plugin matrix. |
| PLUG-037 | Blocked | Owner/fixture decision required; no fixture inventory was invented. | Reviewed licensed fixture inventory. |
| PLUG-038 | Blocked | External compatibility gate identified; no repeatable product matrix was run. | Repeatable compatibility runs across claimed products and platforms. |
| HW-033 | Deferred | External physical performance gate identified; no named-hardware latency/dropout soak performed. | Qualification-harness measurements for latency, dropout and soak. |
| HW-034 | Deferred | External physical loopback gate identified; no physical recording/listening run performed. | Physical loopback, recording and audible correctness evidence. |
| HW-035 | Deferred | External controller gate identified; no controller timing/reconnect measurement performed. | Controller timing and reconnect measurements. |
| HW-036 | Deferred | External RF/clock gate identified; no LE Audio/UWB hardware exercise performed. | RF and clock qualification harness evidence. |
| HW-037 | Deferred | External multi-host gate identified; no two-node rehearsal or witness capture performed. | Independent multi-host timing and failover measurement. |
| SEC-040 | Blocked | External deployment gate identified; no venue LAN/TLS/IdP/firewall deployment performed. | Deployed qualification report with failure injection and controller traffic. |

## Boundary

The four software rows have current hosted implementation evidence but remain In Progress because their acceptance criteria include target-environment behavior. The other 21 rows require external hardware, deployment, licensed fixtures, assistive technology, or owner decisions. No status is changed by this execution record alone.
