# Windows unattended testing — 2026-10-18

## Installed candidate comparison

The fresh private-PC read-only comparison completed and rejected a mismatch.
The selected candidate's integrity passed, but the sole policy-allowlisted
installed executable did not match its post-bundle executable reference.
This supersedes the earlier historical-hash-only observation for this selected
candidate. It does not identify the installed application's source revision.

- [Comparison run 39135956305](https://github.com/colinatwood/stagemesh-hardware-control/actions/runs/39135956305), job `117700392112`, attempt 1.
- Control commit: `21d1d36fa322af3ca523a19b39c6f54bb71eca6c` (private PR #8 merged).
- Verifier source: independently pinned `ae19cef1327e4a80c1e0e127f152074cdfeda8fd` (public PR #176 head, subsequently merged).
- Candidate: public Desktop run `39044932951`, Windows `online` channel, manifest source `77e46d6ccf9314e653422e985b9e965e163568cf`, installer `msi/StageMesh_0.1.0_x64_en-US.msi`.
- Artifact `12139384967`, `stagemesh-installed-comparison-39135956305-1`, 774-byte ZIP. Downloaded SHA-256 matches GitHub's artifact digest: `15b9b0152ed5a382777728002bd7a395e02432284e2558ca92e20d8cc1bca457`.

| Receipt field | Observed result |
| --- | --- |
| Candidate integrity | Passed |
| Installed executable matches selected reference | False |
| Failure reason | Selected executable differs from this installer's build reference |
| Installed source verified | False |
| Publisher/source provenance authenticated | False |
| Physical outputs armed | False |

The workflow did not launch the app, send keys, execute the installer or replace
the installation. This failure is a candidate mismatch, not evidence of an
audio defect. The check neither extracts the installer payload nor qualifies
installed resources, installation lifecycle, accessibility or hardware.

## Current-source native safe suite

[Safe-suite run 39138381430](https://github.com/colinatwood/stagemesh-hardware-control/actions/runs/39138381430)
was dispatched against clean merged source
`392ac5d0baa2d40fdf2c9d61af0cb283c0a30e06`, using control commit
`21d1d36fa322af3ca523a19b39c6f54bb71eca6c`.
The run passed on the private Windows PC. It did not request physical cable
operations or audible output.

| Exercise | Observed result |
| --- | --- |
| Native CTests | 21/21 passed; reported total test time 2.47 seconds |
| Lifecycle helper | 25 cycles; active destruction, inactive snapshot refusal and wrong-thread refusal passed |
| Capture helper | 16 callbacks, 30,720 frames; native callbacks, drained stop and explicit restart observed |
| Silent playback helper | 16 callbacks, 30,720 frames; native callbacks, drained stop and explicit restart observed |
| Synthetic MIDI | Four observed events, four injected messages, zero queue drops |

Both audio helpers reported 192,000 Hz, a configured period of 1,920 frames,
two float32 channels and rejection of non-exact configuration. Capture buffers
were discarded without storing audio samples; playback was intentionally silent.
These counters and configured settings are not measured latency or quality.
Both physical-topology-stop and rearm-after-native-event flags were false, so
the software restart does not demonstrate physical hotplug recovery. The native
helper run does not qualify the installed desktop or bind the exercised stream
to a named BOOM endpoint.

Artifact `12140975995`, `stagemesh-hardware-safe-suite-39138381430-1`, is a
31,245-byte ZIP with SHA-256
`c63f360f281fae59419011c6a723545cb93cd532f10088de2c5193528d11adb7`.
The downloaded archive matched GitHub's digest; entry names were unique and
safe, and its manifest covered exactly the other 23 members. All member sizes
and hashes verified. Capture, playback and lifecycle reports each identified
the exact source above with a clean worktree, successful exit and no timeout;
their transcript lengths and hashes independently matched the archive members.
Job and status reports agreed on exact source, safe-suite operation and disarmed
physical outputs. Raw host, endpoint and driver inventory stays private.
Binary origin, owner review and physical qualification remain outside this
evidence boundary.

## Acceptance and next action

No workbook row closes: 24 Done and 25 open remain. The next installed-app step
is to identify or explicitly authorize updating the PC to a selected candidate,
then repeat the read-only comparison. A mismatch alone does not authorize
installation replacement. After a matching comparison, perform three physical
BOOM unplug/explicit-Reconnect/fresh-callback cycles with outputs disarmed.
Audio quality, measured latency/dropouts, physical MIDI soak, screen-reader
acceptance, clean-host package lifecycle, signing and owner/legal gates remain
open.
