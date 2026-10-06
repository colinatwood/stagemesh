# Astra checkpoint 35 validation — witness/replication secret lifecycle

Checkpoint 35 adds bounded private HMAC keyrings to replication, planned handoff
and witness quorum traffic. It preserves legacy single-secret compatibility when
keyring mode is not selected, while making keyring mode explicitly non-downgradable.

## Contract

- `STAGEMESH_REPLICATION_KEYRING_FILE` and `STAGEMESH_WITNESS_KEYRING_FILE`
  load owner-only, non-symlink, bounded JSON keyrings.
- Every keyring-authenticated wire object carries a HMAC-covered `keyId`.
- Outbound traffic uses only `activeKeyId`; inbound traffic resolves exactly the
  declared accepted key ID.
- Each witness quorum operation pins one immutable key snapshot even if the file
  rotates between individual witness replies.
- Witness responses are signed with the same key ID that authenticated the
  request and remain bound to the exact request digest/operation.
- Planned-handoff readiness uses the offer key ID. Removing that key before the
  transaction finishes fails closed instead of re-signing under the new active key.
- Keyring mode rejects missing/unknown key IDs and never falls back to the legacy
  environment secret.
- Rotation changes authentication only. Witness epoch/quorum fencing and explicit
  physical-output arming remain unchanged.

## Regression evidence

`tests/test_cluster_secret_rotation.py` covers private-file enforcement, atomic
reload, malformed replacement, old/new overlap, active-key switch, exact old-key
removal, no-key-ID downgrade rejection, planned-handoff key binding, per-operation
witness snapshot pinning, and a live production witness handler rotating without
restart.

Validation on the checkpoint source:

- native CTest: 2/2 passed;
- release Python suite: 500 tests passed;
- eight new cluster-secret rotation regressions passed;
- public schema set remains 117 and parses successfully;
- no native/audio/render implementation changed.

The remaining security work is real deployed LAN qualification, specialized
admin/adapter/machine authorization-audit unification, controller/rate workload
qualification, backend operation-cost bounds, and explicit witness clock/trust
qualification.
