# Astra checkpoint 34 validation

Checkpoint 34 bounds the durable per-user authorization audit introduced at checkpoint
32 while preserving a verifiable chain across rotation.

The active `authorization-audit.jsonl` rotates before the next record would cross
`STAGEMESH_AUTH_AUDIT_ROTATE_BYTES` (default 4 MiB, accepted range 64 KiB to
256 MiB). Immutable rotated files live under `authorization-audit-segments/` and the
number retained is bounded by `STAGEMESH_AUTH_AUDIT_RETAIN_SEGMENTS` (default 8,
range 1 to 256). The next segment and active file continue from the exact prior hash;
rotation never restarts the chain at zero.

When retention prunes an old prefix, StageMesh first atomically writes and fsyncs
`authorization-audit-retention.json`. That anchor commits the exact previous head,
next retained sequence, pruned segment count and pruned record count. Only after the
anchor is durable are old segment bytes unlinked. A write failure such as ENOSPC
therefore prunes nothing. A crash after the anchor commit but before unlink leaves an
old segment as harmless residue: verification ignores only sequences already committed
into the anchor and reports the residue until later maintenance removes it.

The admin verification surface now reports retained records/bytes, active records,
rotation threshold, retention count, cryptographic retention anchor, pruned records and
segments, stale crash residue and the current chain head. `records` means locally
retained records; `totalRecords` includes the pruned-record count committed by the
retention anchor. The actual actor/action history is still not returned by the HTTP
verification endpoint.

Steady-state append cost remains bounded. After one verified scan, the repository caches
the current hash head and file identities; each decision append performs bounded file
metadata checks plus one fsynced append. Structural rotation performs the bounded full
scan. Unexpected external file replacement/change invalidates the cache and fails the
next mutation closed instead of silently continuing from changed bytes.

Five new rotation regressions cover chain-preserving retention, retained-segment tamper
detection, ENOSPC before the retention anchor, simulated crash after anchor commit and
steady-state cached-head behavior. Together with checkpoint 33, the full Python suite
passes 492 tests using the built native engine. Native source remained unchanged and
both CTest targets pass.

Specialized admin/adapter/machine authorization-audit unification remains separate.
Controller workload and real-disk fsync-cost qualification also remain required before
LAN/show claims; this checkpoint bounds the algorithm and storage, not the venue's
actual filesystem latency.
