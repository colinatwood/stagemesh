# Checkpoint 78: guarded stream lifecycle and manual software rendering

[Current master workbook](backlog/StageMesh-Master-Backlog-Checkpoint-78.xlsx).
Code revision: `ec7bd4e4dc2977ac578048a8a95509a14ebcc1cd` (PR #13).

The lifecycle guard connects an exact preflight decision to one device execution
fence lifetime. It rejects stale authority and unimplemented conversion plans,
revokes callback permission on loss, and retains a pending native stop across
recovery and close. A newer explicit rearm and acknowledgment of the completed
native stop are required before preparing after revocation.

This is a single control-thread contract, not an atomic callback gate. It owns
no OS stream. Asynchronous adapters must safely publish permission to callbacks,
stop native I/O and acknowledge completion themselves.

## Hosted evidence

[Native CI run 34904550438](https://github.com/colinatwood/stagemesh/actions/runs/34904550438)
passed four native CTests per OS. All six PR checks passed for the code revision.
Evidence records test merge `00dae0d1647d718fa38cc319482ac591816355f2`, executable
hashes and native source hashes. All source hashes match the committed code,
accounting for Windows checkout line endings. Reports are archived under
`docs/evidence/checkpoint-78/`.

- Windows: lifecycle, stale generation, pending stop and explicit-rearm contracts
  passed. The macOS software renderer truthfully reports unavailable. Hosted
  Windows still has no playback/capture endpoint; there is no WASAPI I/O evidence.
- macOS arm64 with AddressSanitizer: Apple's Generic Output unit was created,
  configured for stereo float32 at 48 kHz, initialized, started, manually rendered,
  stopped, restarted and disposed. Eighteen callbacks rendered 4,608 frames in
  256-frame slices. Every normal sample was checked against 0.125; the revoked
  callback was checked for silence. Callback/frame accounting also passed.

The macOS fixture calls AudioUnitRender synchronously with increasing sample
positions. It does not use a hardware output or device clock. It demonstrates
software rendering and resource lifecycle, not device-clocked streaming, timing,
audible behavior, endpoint-loss handling or physical qualification.

## Backlog disposition

49 rows: 24 Done and **25 open**, including **22 P0**. Open work remains:
4 software, 19 qualification and 2 decisions. AUD-035/036 and DEV-033/034 stay
In Progress. PLUG-034 stays Done for hosted verification-to-launch binders;
licensed plugin compatibility remains separate.

Next software work is exact endpoint configuration and native stream ownership,
including callback synchronization, stop-on-loss and explicit recovery. Windows
native MIDI/stable identity/events, per-device listeners and full-engine
integration remain unfinished. The full engine is not present in this repository.

Workbook checks preserve eight sheets, three tables, one chart and 63 formulas;
totals were independently counted, recalculated and reviewed in rendered sheets.
