# Windows safe-suite observation — 2026-10-16

The private Windows runner completed the bounded `safe-suite` successfully against merged StageMesh source `1f11b32041db3e54d85fb8352ca09af94ef7da23` (PR #171). This records helper execution and evidence integrity; no external qualification row is closed.

## Run and source

- [Hardware-control run 38945585363](https://github.com/colinatwood/stagemesh-hardware-control/actions/runs/38945585363), job `117123765807`, attempt 1; completed 2026-10-16 UTC.
- Control repository commit: `73e783106d153d255a8e2e9a68874e6fa2596bc9`.
- Operation: `safe-suite`; observation-window input: 120 seconds. This input does not mean the smoke streams ran for 120 seconds.
- Each of the three native helper reports observed the exact StageMesh source above and a clean worktree, exit code zero, no timeout and source/binary stability during execution.
- Physical outputs were not armed. Capture buffers were discarded; playback was intentionally silent. No physical cable operation was requested.

## Observed results

| Exercise | Result |
| --- | --- |
| Native CTest suite | 21/21 passed; reported total test time 2.12 seconds |
| Device lifecycle helper | 25 cycles; active destruction, inactive snapshot refusal and wrong-thread refusal passed |
| Capture helper | 16 callbacks, 30,720 frames; callbacks observed, stop drained, explicit restart observed and non-exact configuration rejected |
| Silent playback helper | 16 callbacks, 30,720 frames; callbacks observed, stop drained, explicit restart observed and non-exact configuration rejected |
| Synthetic MIDI | Four observed events, four injected messages, zero queue drops; passed |

Both audio helpers reported 192,000 Hz, a configured period of 1,920 frames, two channels and float32 format. These configured settings and counters are not audio latency measurements. The native-topology-stop and single-explicit-rearm-after-native-event flags were false in both helper transcripts; their explicit software restart does not demonstrate physical hotplug recovery. Device inventory alone does not bind the exercised stream to the named BOOM endpoint.

## Evidence integrity

Artifact: `stagemesh-hardware-safe-suite-38945585363-1`, ID `12065941873`, 31,406-byte ZIP.

ZIP SHA-256: `c4789fed539bfe038e85fa48998fc3d390963852bcdc8f7918efa68e7310ac37`.

The downloaded archive matched GitHub's artifact digest. Its entry names were unique; the manifest covered exactly the other 23 members. Every member matched its declared byte length and SHA-256. The capture, playback and lifecycle report transcript lengths and hashes independently matched their corresponding archive members. Job/status reports agreed on operation, exact source and disarmed outputs, with overall pass status.

| Transcript | SHA-256 |
| --- | --- |
| Capture | `0092db0b8c2dfadb7445cd29ca6093481c4f83e5236cd2c019e464b699df1610` |
| Silent playback | `8f0f31b671848b5e27f56c4e3aa95c51a1a1137dd79646995e5ad5be8667e408` |
| Device lifecycle | `472e7b729e5a1ca2456fd1ab1ba6698a5cac694d12714677e3721500aa646116` |

Raw host, endpoint and driver inventory stays in the private artifact. The wrapper binds captured transcript and exit status to the helper execution and records the source snapshot. It explicitly leaves `binarySourceBindingVerified`, `physicalHardwareQualified` and `ownerReviewComplete` false. Workflow checkout/build observations do not turn this into independent binary-origin attestation.

## Remaining work

The authoritative workbook remains at 49 total items: 24 Done, eight In Progress, 11 Blocked and six Deferred. No status changes are justified by this smoke run.

Run the [installed-app BOOM recovery checklist](capture-recovery-app-qualification.md) on a desktop candidate built from the exact source above. Record three physical input-loss/explicit-rearm/fresh-callback cycles and the visible Connection details observations, keeping outputs disarmed. Installed-app interaction, physical hotplug soak, audible and recording quality, measured latency/dropout behavior, assistive technology, clean-host package lifecycle, signing and the other external gates remain open.
