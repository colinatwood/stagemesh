# Checkpoint 83: pinned audio endpoint capability probes

Native stream ownership already accepted a selected endpoint, but capability
probing only supported the system default. Callers selecting another device had
to supply their own probe or risk planning from the wrong endpoint's settings.

`probe_audio_endpoint(selection, direction)` now reads the exact selected native
object. It resolves current native/persistent identity and directional capability
before and after OS readback, checks notified topology revisions, and rejects
missing, ambiguous or weakened identities. It never substitutes the default or
silently accepts a replacement native object. The caller must explicitly recover
the selection before probing a rebound endpoint. OS read failures propagate;
concurrent identity changes otherwise produce no endpoint, requiring a refresh.

The probe does not change device settings, start I/O or authorize execution.
Capabilities are a snapshot. Native streams still require a current execution
fence and verify exact configuration during preparation/start. Default probing
remains available through the existing API.

Tests compare pinned/default capability readback and reject missing, mismatched
and wrong-kind selections. The macOS selected-endpoint fixture uses a non-default
software aggregate's pinned capabilities to configure native playback/capture.
After its removal, the selected probe must report absence while the default is
still available. Explicitly recovered selection probes the recreated endpoint.
Existing injected identity downgrade and native stop/recovery tests remain.

Backlog stays **25 open / 22 P0**: four software, 19 qualification, two decisions.
AUD-035/036 and DEV-033/034 still need full-engine integration and applicable
target evidence. Windows hosted runners have no audio endpoints. Licensed plugin
compatibility and physical qualification remain separate; see
[remaining inputs](remaining-data-requirements.md).

## Hosted validation and workbook

[Checkpoint 83 master workbook](backlog/StageMesh-Master-Backlog-Checkpoint-83.xlsx)
preserves all statuses and acceptance criteria, eight sheets, three tables, one
chart and 63 formulas. Totals were recalculated and changed regions rendered for
review. PLUG-034 remains Done for hosted native launch binding.

Code `1c597df574c9a1af2a2e65837f0565eb8911d762` passed all six checks.
[Native run 34998947927](https://github.com/colinatwood/stagemesh/actions/runs/34998947927)
records test merge `28a9f9ff736e91f512956cf300957c2d729a7773` and source/binary
hashes under `docs/evidence/checkpoint-83/`. Seven native CTests passed per OS.
macOS arm64/AddressSanitizer passed pinned default input/output comparisons,
non-default aggregate readback and removal without fallback. The selected-endpoint
fixture recorded 39 playback and 29 capture callbacks across its phases.

Windows compiles the selected-endpoint path and passes missing-pin rejection,
but zero hosted endpoints means no live pinned Windows readback or I/O is claimed.
No physical hardware, timing, licensed compatibility or full-engine integration
qualification is added by these tests. Capture samples are discarded, not stored.
