# Remaining inputs required for backlog completion

Checkpoint 84 restores the full Checkpoint 69 source alongside the newer GitHub platform modules. Source access is resolved. Consolidation does not itself connect native device streams to the engine or complete qualification.

| Work | Required input or environment |
| --- | --- |
| AUD-035/036, DEV-033/034 integration | Windows/macOS native playback and capture owners are connected to the full engine. Target-OS CI compiles this path and the authenticated engine smoke records the capability. Live selected-endpoint I/O and topology-loss evidence remain required. |
| Windows endpoint validation | A Windows host with an accessible audio endpoint. GitHub-hosted runs currently report zero playback/capture endpoints. Native MIDI enumeration sees one endpoint, but no PnP event was observed. |
| Capture integration and qualification | The Python `CaptureDrainer`/native record-queue bridge has software lifetime, bounded-drain, dropout, and failure-path coverage in `tests/test_daw_capture.py`. `stagemesh::submit_capture_packet` is used by both ALSA and the Windows/macOS `NativeCaptureService` callback, while the engine-owned worker preserves stream ownership and device-fence servicing. Target-OS authenticated engine evidence records `captureIngressIntegrated`, `nativeCaptureOwnerIntegrated`, and `targetOsCaptureIntegrationCompiled`. The standalone endpoint smoke remains correctly marked `fullEngineIntegrated: false` because it does not run through the engine. Windows live capture still needs an accessible endpoint, and physical recording quality needs a separate named-device environment. |
| AUD-034 | Recovered conversion implementation and the reproducible [`audio-conversion-quality.py`](../scripts/audio-conversion-quality.py) measurement helper are available; a physical reference-signal capture, accepted thresholds, and reviewed measurement envelope are still required. No invented quality figures. |
| UX-035 | Recovered frontend/operator workflows are available; a selected assistive-technology environment is still required. |
| PKG-033/034 | Cross-platform desktop candidates include fail-closed clean-host collectors: `windows-clean-host.py` for Windows and `posix-clean-host.py` for macOS/Linux. Run each exact candidate on fresh Windows 11 x64, macOS 14+ Apple Silicon, and Ubuntu 22.04/24.04 x64 hosts through baseline, install, restart recovery, real-version upgrade, and uninstall; run the Linux package/service qualifier with the required device namespaces. Exercise Windows NSIS/MSI and Linux AppImage/Debian separately. Owner review remains required. |
| REC-033/034, SEC-039, HW-037 | Independent witness/node hosts, clock/custody information, and declared power/network failure domains. Hosted jobs are not proof of physical independence. |
| SEC-040 | Actual deployment URL, TLS/proxy/IdP/firewall configuration and authorized workload/failure-injection environment. |
| PLUG-033, PLUG-035/036/038 | Selected product/version/OS/architecture matrix, licensed fixtures and permission to run the qualification cases. |
| LEGAL-001, PLUG-037 | Owner-approved license and fixture redistribution/automation terms. Apache-2.0 exists in this repository; owner approval covering recovered source and final packaged notices is not established. |
| DEV-035, LIVE-033, HW-033/034/035/036 | Named devices, physical routing/loopback or controller/RF environments, and agreed timing/audible measurement conditions. Native CoreMIDI/WinMM callback delivery and topology-loss behavior also need target-host evidence. |

These are limits on completing the corresponding acceptance criteria. They do
not turn hosted software tests into physical hardware or product qualification.
The four target-platform rows remain In Progress; hosted compile/runtime evidence
does not satisfy their selected-hardware acceptance criteria. Existing
qualification/decision statuses are preserved until their evidence or owner
decisions are supplied.

Checkpoint 86's capture-ingress implementation and the later target-owner
integration boundary are recorded in
[checkpoint-86-capture-ingress.md](checkpoint-86-capture-ingress.md).
