# Astra backlog checkpoint 46 validation

Checkpoint 46 turns venue-adaptation and operational-authority receipts into a signed append-only Public Record and adds a separately authenticated external-witness attestation path.

## Public Record

`backend/public_record.py` adds a control-plane-only `PublicRecordStore` backed by `.runtime/public-record.jsonl`.

Each record contains a monotonic sequence, record ID/type, nanosecond timestamp, payload, previous hash, SHA-256 record hash, signer identity and an HMAC-SHA256 node signature. The signature key is the existing persisted StageMesh security-state root key; no third-party Python runtime dependency is introduced.

The record chain verifies sequence continuity, previous-hash continuity, payload hash and node signature. A changed payload, reordered record, broken link, wrong signer or wrong signature fails verification.

The node signature is intentionally described as an authenticated signature rather than public-key transparency: HMAC verification requires the StageMesh identity secret. Independent verification is supplied by the separate witness boundary below.

## External witness attestations

Optional `STAGEMESH_PUBLIC_RECORD_WITNESS_FILE` configures an absolute, owner-only private witness policy:

```json
{
  "version": 1,
  "quorum": 1,
  "witnesses": {
    "witness-a": "separate-shared-secret-at-least-32-bytes"
  }
}
```

The file is opened without symlink following, must be a regular file owned by the service UID, must deny group/other permissions, is size bounded and is rejected if it changes while being read.

An external witness signs the exact StageMesh `recordHash` plus its witness identity and issue time using the distinct witness secret. `POST /api/v1/public-record/witness` verifies that attestation, rejects unknown records/witnesses/bad MACs and persists accepted attestations in their own hash-linked `.runtime/public-record-witnesses.jsonl` chain. Exact witness/record replay is idempotent.

`GET /api/v1/public-record` reports chain verification, signer identity, record/head counts, witness quorum, attestation count and whether every retained record meets the configured external-witness quorum. The witness submission route is excluded from human RBAC because its body carries the separate machine witness credential; it does not inherit operator/authority roles.

## Signed operational receipts

- Every committed Venue Patch Layer receipt is appended as `venue-adaptation` before the post-commit runtime event is persisted. Its persisted adaptation receipt receives a stable `publicRecord` reference containing record ID, sequence, record hash, signer ID and signature.
- Operational authority lease grants append `authority-lease-grant`; a grant is revoked fail-safe if the Public Record append cannot complete.
- Authority revocations append `authority-lease-revoke`. Revocation remains in effect even if later Public Record persistence fails.
- The existing event journal remains separate. Public Record evidence does not mutate show intent or auto-arm physical output.

## Validation

- Release Python suite: **545 tests passed**.
- Focused Public Record / authority / adaptation group passed, including payload tamper detection, external witness authentication, witness replay idempotence, private-policy permission rejection, persisted adaptation references and authority grant/revoke references.
- Existing HTTP venue-authority coverage now checks Public Record status and verifies that an unconfigured witness submission is rejected.
- Native source is unchanged from checkpoint 44; RT native CTest remains **2/2 passed**.
- Automation performance passed with 4096 points / 8192 frames.
- Public JSON schemas: **120** parsed successfully; `frontend/openapi.json` parsed successfully.
- Frontend JavaScript: **7/7** files passed `node --check`.

## Remaining boundary

This checkpoint does not claim public-key signatures, transparency-log gossip, externally hosted append-only storage, key escrow or production witness deployment. The software protocol supports a genuinely separate witness credential and exact-hash attestation, but production independence still depends on placing that witness outside the StageMesh failure/administrative domain.

The Public Record is currently append-only and unbounded. Retention/archival policy must not discard evidence silently if added later.
