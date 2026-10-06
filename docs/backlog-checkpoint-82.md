# Checkpoint 82: fence weakened device identity assurance

A selection pinned with stable identity could previously resolve as Attached or
Rebound when a later matching record withdrew its identity assurance. Matching
hashes alone preserved execution, including when the native object was unchanged.
Strong selections now require the current record to retain both stable endpoint
identity and reconnect assurance. A downgrade resolves Detached and fences
execution; explicit rearm cannot override weak evidence. Restored strong evidence
remains disarmed until explicitly rearmed.

Contradictory weak records cannot enable automatic reconnect when pinned. Empty
selection/native identities fail closed. Weak duplicate candidates still count
toward ambiguity, so filtering does not manufacture a unique strong match.
Existing weak selections retain exact-native matching without automatic rebound.

Regression cases cover both audio and MIDI identities, unchanged and replacement
native hashes, revoked reconnect assurance, weak duplicates, malformed records,
execution fencing and explicit recovery. The macOS selected-endpoint fixture
injects weaker metadata into a copy of real inventory during native playback and
capture, verifies drained stop and rejected weak rearm, restores strong inventory
and explicitly restarts. This metadata downgrade is synthetic; native I/O is real.
It is not evidence of an OS-generated or physical identity downgrade.

Backlog totals remain **25 open / 22 P0**: four software, 19 qualification and two
decisions. AUD-035/036 and DEV-033/034 remain In Progress. Full-engine integration,
Windows live audio, licensed compatibility and physical qualification still
require the [remaining inputs](remaining-data-requirements.md).

## Hosted validation and workbook

[Checkpoint 82 master workbook](backlog/StageMesh-Master-Backlog-Checkpoint-82.xlsx)
preserves statuses, acceptance criteria, eight sheets, three tables, one chart
and 63 formulas. Totals were recalculated and changed regions rendered/reviewed.
PLUG-034 stays Done for hosted native launch binding; licensed compatibility is
not closed by this work.

Code `c8f58d075519134324567fa4aa852f48e6c72643` passed all six checks.
[Native run 34985922021](https://github.com/colinatwood/stagemesh/actions/runs/34985922021)
records test merge `1bc5383cd7cf3dd47e150ec66bd69fe6bebc78d0`, source hashes and
binary hashes in `docs/evidence/checkpoint-82/`. Seven native CTests passed per OS.
The macOS arm64/AddressSanitizer selected-endpoint fixture recorded 27 playback
and 33 capture callbacks across injected assurance loss/recovery and actual
software endpoint removal/recreation. Both new injected-assurance checks passed.
Playback writes silence; capture samples are discarded without storage.

Windows passes resolver/fence regressions and native builds, but the hosted
runner has no audio endpoints. Native Windows stream-loss behavior, real device
identity downgrades, physical hotplug and recording quality remain unqualified.
