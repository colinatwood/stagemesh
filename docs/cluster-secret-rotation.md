# Cluster HMAC key rotation

StageMesh replication, planned handoff and witness control traffic support an
optional private JSON keyring so authentication keys can rotate without process
restart. This is control-plane authentication only; it does not grant authority,
change witness epochs, or arm physical outputs.

## Private keyring files

Set either or both of:

```text
STAGEMESH_REPLICATION_KEYRING_FILE=/etc/stagemesh/replication-keys.json
STAGEMESH_WITNESS_KEYRING_FILE=/etc/stagemesh/witness-keys.json
```

If the witness keyring path is unset, it follows the replication keyring path,
matching the old witness-secret fallback. Separate files are recommended when
replication and witness credentials have different custody.

The file must be an absolute, owner-matched, non-symlink regular file with no
group/other permissions and at most 32 KiB. At most 16 keys are accepted. Key
identifiers are 1..64 ASCII alphanumeric/`._-` characters; secrets are bounded
printable ASCII strings of 32..512 characters.

```json
{
  "version": 1,
  "activeKeyId": "2026-09-b",
  "keys": {
    "2026-09-a": "replace-with-private-random-secret-a-at-least-32-chars",
    "2026-09-b": "replace-with-private-random-secret-b-at-least-32-chars"
  }
}
```

StageMesh opens and validates a fresh immutable snapshot for every replication
or witness operation. Atomic file replacement therefore changes the next
operation without changing a key halfway through one quorum request.

## Rotation sequence

1. Install `old + new`, leaving `activeKeyId=old`, on every node and witness.
2. Verify every participant accepts traffic carrying either exact key ID.
3. Atomically replace each keyring with `old + new`, `activeKeyId=new`.
4. Verify all outbound replication/witness traffic carries `keyId=new`.
5. After all in-flight handoffs using `old` have completed or been aborted,
   atomically replace the files with `new` only.

Keyring mode never falls back to an unlabelled legacy HMAC. A missing or unknown
`keyId` is rejected. Removing a key therefore rejects the next operation that
still depends on it. Planned-handoff readiness receipts must use the same key ID
as their offer, so rotating the active key cannot silently change an in-flight
authority transaction.

Legacy `STAGEMESH_REPLICATION_SECRET` and `STAGEMESH_WITNESS_SECRET` remain
available only when the corresponding keyring file is not configured. They are
compatibility mode, not a fallback from keyring mode.

## Failure semantics

Malformed, insecure, unreadable or non-atomic replacement files fail the next
authentication operation closed. A previously loaded key is not cached as an
emergency fallback. Authentication rotation changes neither witness lease
ownership nor the persistent handoff/recovery fence; those authority facts keep
their existing epoch/quorum rules.
