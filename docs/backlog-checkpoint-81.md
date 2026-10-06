# Checkpoint 81: fresh authorization after native stream revocation

When a native topology notification stops a stream, its control-thread device
fence can still be Armed. Previously `explicit_rearm()` returned success without
changing that fence's generation. The stopped stream correctly rejected the
already-revoked generation, so recovery required an extra disarm/rearm cycle.

Every successful explicit rearm now issues fresh authority, including from an
already Armed state. Consumers holding the previous generation must stop and
prepare again. Initial arming is a one-shot attempt before other state changes;
it cannot bypass recovery after detach, ambiguity or an explicit disarm. Fence
objects cannot be copied, moved or assigned over a live authority. Callers still
own the control thread and must stop native I/O before preparing again.

Contract regressions cover native-only revocation, pending native stop, failed
initial arming, reused initial arming, old-generation replay and invalidation of
old consumers on reauthorization. Hosted macOS playback and capture tests also
create a real software topology event, verify native stop, then recover with one
explicit rearm without first disarming the still-Armed control fence.

Backlog statuses remain **25 open / 22 P0**: four software, 19 qualification and
two decisions. This fixes a native lifecycle recovery gap within AUD-035/036 and
DEV-033/034; it does not supply the missing full-engine integration. PLUG-034
remains Done for hosted verification-to-launch binding. Licensed compatibility,
Windows live audio and physical qualification remain separate.

## Hosted validation and workbook

[Checkpoint 81 master workbook](backlog/StageMesh-Master-Backlog-Checkpoint-81.xlsx)
preserves all row statuses and acceptance criteria, eight sheets, three tables,
one chart and 63 formulas. Recalculated totals remain 25 open / 22 P0; changed
regions were rendered and reviewed.

Code `60b1064a4de613d802b1cc3622272f92afb81c8a` passed all six checks.
[Native run 34981909094](https://github.com/colinatwood/stagemesh/actions/runs/34981909094)
records test merge `fb9ab228b2307b0f040626e84866a82bfcd889ad`, source hashes and
binary hashes in `docs/evidence/checkpoint-81/`. Seven CTests passed per OS.
macOS arm64/AddressSanitizer observed 32 playback callbacks / 16,384 frames and
27 capture callbacks / 13,824 frames at exact 48 kHz, 512 frames, two-channel
float32. Both report `singleExplicitRearmAfterNativeEvent: true`. Playback is
silence; capture samples are discarded without storage. Selected software
endpoint removal/recreation also remains covered by the existing test.

Windows passes the native build and contract regressions but has no audio
endpoint, so its native event recovery path is not claimed as live I/O evidence.
Full-engine integration and physical/recording qualification still require the
[remaining inputs](remaining-data-requirements.md).
