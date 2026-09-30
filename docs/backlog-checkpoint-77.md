# Master backlog through merged Checkpoint 77

[Current workbook](backlog/StageMesh-Master-Backlog-Checkpoint-77.xlsx) reconciles
the prior Checkpoint 74 workbook with merged PRs #9, #10 and #11. Source baseline:
`c4e2c6a4fdd5f8759ce2056f013a48a4b41df6aa`. No additional row is closed.

| Category | Open |
| --- | ---: |
| Software | 4 |
| Qualification | 19 |
| Decisions | 2 |
| Total | 25 |
| P0 subset | 22 |

The four software rows remain AUD-035/036 and DEV-033/034. The workbook now records
native CoreAudio/CoreMIDI identities/events (75), explicit-rearm device fencing
(76), and WASAPI/CoreAudio preflight (77). The fence is a safety state machine;
integration with the owner of a real stream remains necessary.

[Checkpoint 77 hosted run](https://github.com/colinatwood/stagemesh/actions/runs/34885284915)
passed three native CTests per OS. macOS playback and capture preflight observed
48 kHz, 512-frame default period, 2-channel float32 endpoints. Windows had no
endpoints: its successful no-endpoint checks are not live WASAPI preflight proof.
No configuration was applied and no audio I/O was started. Reviewed evidence is
retained in `docs/evidence/checkpoint-77/`.

Licensed plugins, physical hotplug, hardware performance and deployment gates
remain separate. Checkpoint 78 branch work is excluded from this merged snapshot.
Overlapping PR #8 was closed in favor of the more complete merged implementation.

Workbook validation preserved all eight sheets, three tables, one chart and 63
formulas. Open totals were independently counted and formulas recalculated.
