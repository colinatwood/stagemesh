# Remaining inputs required for backlog completion

Checkpoint 84 restores the full Checkpoint 69 source alongside the newer GitHub platform modules. Source access is resolved. Consolidation does not itself connect native device streams to the engine or complete qualification.

| Work | Required input or environment |
| --- | --- |
| AUD-035/036, DEV-033/034 integration | Implementation and tests connecting the recovered shared runtime fencing and conversion code to the newer native streams; source is now available. |
| Windows endpoint validation | A Windows host with an accessible audio endpoint. GitHub-hosted runs currently report zero playback/capture endpoints. Native MIDI enumeration sees one endpoint, but no PnP event was observed. |
| Capture integration and qualification | The Python `CaptureDrainer`/native record-queue bridge has software lifetime, bounded-drain, dropout, and failure-path coverage in `tests/test_daw_capture.py`. Checkpoint 86 factors the engine's non-blocking ring/recording-queue handoff into `native/include/stagemesh/capture_ingress.hpp`, used by the ALSA callback and covered for samples, generations, discontinuities, non-finite values, and disarmed rejection. The platform `NativeCaptureStream` callback is not yet connected to that full-engine path; native evidence still reports `fullEngineIntegrated: false`. Windows live capture needs an accessible endpoint, and physical recording quality needs a separate named-device environment. |
| AUD-034 | Recovered conversion implementation is available; an accepted reference-signal/measurement envelope is still required. No invented quality figures. |
| UX-035 | Recovered frontend/operator workflows are available; a selected assistive-technology environment is still required. |
| PKG-033/034 | Recovered package source and qualifier are available; build package artifacts and run on a clean target host with the required device namespaces. |
| REC-033/034, SEC-039, HW-037 | Independent witness/node hosts, clock/custody information, and declared power/network failure domains. Hosted jobs are not proof of physical independence. |
| SEC-040 | Actual deployment URL, TLS/proxy/IdP/firewall configuration and authorized workload/failure-injection environment. |
| PLUG-033, PLUG-035/036/038 | Selected product/version/OS/architecture matrix, licensed fixtures and permission to run the qualification cases. |
| LEGAL-001, PLUG-037 | Owner-approved license and fixture redistribution/automation terms. Apache-2.0 exists in this repository; owner approval covering recovered source and final packaged notices is not established. |
| DEV-035, LIVE-033, HW-033/034/035/036 | Named devices, physical routing/loopback or controller/RF environments, and agreed timing/audible measurement conditions. Native CoreMIDI/WinMM callback delivery and topology-loss behavior also need target-host evidence. |

These are limits on completing the corresponding acceptance criteria. They do
not turn hosted software tests into physical hardware or product qualification.
The four software rows remain In Progress; existing qualification/decision
statuses are preserved until their evidence or owner decisions are supplied.

Checkpoint 86's partial capture-ingress implementation and current verification
boundary are recorded in [checkpoint-86-capture-ingress.md](checkpoint-86-capture-ingress.md).
