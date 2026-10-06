# Checkpoint 80: native capture and selected endpoint recovery

[Master backlog](backlog/StageMesh-Master-Backlog-Checkpoint-80.xlsx):
**25 open / 22 P0**; four software, 19 qualification, two decisions.
All statuses and acceptance criteria are preserved, including PLUG-034 Done
for hosted verification-to-launch binding and separate licensed compatibility.
Workbook validation preserved eight sheets, three tables, one chart and 63
formulas; totals were recalculated and changed regions rendered for review.

Playback and capture now share a native endpoint owner. Windows capture uses
IAudioCaptureClient with bounded packet servicing and explicit silent-packet,
discontinuity and timestamp handling. macOS capture uses AUHAL input callbacks
and preallocated buffers. Borrowed capture samples are valid only during the
consumer callback. Tests discard samples without storing or transmitting them.
Pinned identity, exact float32 configuration, owner-thread control, drained
shutdown and explicit rearm apply to both directions. Conversion is rejected
until connected to the actual engine's explicit conversion implementation.

A hosted macOS fixture removes the selected software aggregate endpoint while
playback or capture runs, checks native stop and quiescence, recreates its UID,
then verifies that only explicit rearm allows a fresh stream. Monitor recreation
after HAL activity exposed a CoreMIDI client recreation failure; a process-owned
CoreMIDI client now supports successive monitor lifetimes with per-monitor
notification subscriptions.

## Hosted evidence

Code `a9294525ac2c2583d9a63f51a3164daee55aa6b0` passed all six checks.
[Native run 34926534068](https://github.com/colinatwood/stagemesh/actions/runs/34926534068)
records test merge `7625aea179ec725b15e0c441a16fcbf731c7f6ec` and source/binary
hashes, archived under `docs/evidence/checkpoint-80/`. Seven CTests passed per OS.

- macOS arm64 with AddressSanitizer: capture 23 callbacks / 11,776 frames;
  playback 19 callbacks / 9,728 frames, at verified 48 kHz, 512 frames,
  two-channel float32. Stop, explicit restart, nonexact configuration rejection
  and topology-triggered stop passed. The selected endpoint loss/recreation
  fixture observed 17 playback and 17 capture callbacks. Capture authorization
  already existed; the probe did not request permission. No samples were saved.
- Windows: capture/playback compile and contract/rejection tests pass. The host
  has zero audio endpoints; live WASAPI I/O and selected endpoint loss were not
  exercised. WinMM inventory and PnP registration remain covered, but actual
  Windows PnP event delivery remains unverified.

No physical disconnect, recording quality, hardware timing, audible output,
licensed product compatibility or full-engine integration is qualified.
The missing full-source takeover bundle and target environments remain required;
see [remaining data requirements](remaining-data-requirements.md).
