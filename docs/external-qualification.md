# External qualification evidence

StageMesh software/reference qualification can be executed in the source environment, but the remaining production gates require independent hosts, target operating systems, licensed fixtures, assistive technology or named hardware. Checkpoint 63 makes those runs reproducible and exact-build-bound.

Generate a plan after building the native engine:

```sh
python3 scripts/stagemesh-qualification-plan.py --build-dir "$PWD/build" --output stagemesh-qualification-plan.json
```

The plan contains a deterministic source fingerprint, exact native-engine SHA-256 and eight external tasks. Generate a result skeleton for one task with:

```sh
python3 scripts/stagemesh-qualification-plan.py --build-dir "$PWD/build" --template independent-witness
```

A result is accepted only for the exact `planId`, source fingerprint and native-engine digest. Runner identity is represented only as a SHA-256 hash. Passing results must set every task-specific required claim to true. Artifact references are bounded and carry SHA-256 digests; large/raw artifacts remain outside the envelope.

The envelope never arms physical output and does not automatically mutate the product backlog. Qualification/release review must still decide whether the attached evidence is sufficient and authentic for the target claim.

Current task IDs are:

- `independent-witness`
- `lan-security`
- `linux-packaging-host`
- `windows-platform`
- `macos-platform`
- `assistive-technology`
- `licensed-plugin-matrix`
- `stage-hardware`

## Evidence review

Checkpoint 64 adds an explicit review step between an external runner and any backlog decision. A passing result must include every task-specific required artifact class. Each artifact reference carries a bounded relative path, byte count and SHA-256; the reviewer hashes the actual file beneath a supplied evidence directory and rejects path escapes, missing files, digest/size mismatches or changed files.

Create a private reviewer key file owned by the service/reviewer account with mode `0600`:

```json
{"version":1,"keyId":"release-reviewer-1","reviewerIdHash":"sha256:<64 hex>","secret":"<32+ printable secret bytes>"}
```

Then review one exact-build result:

```sh
stagemesh-qualification-review.py \
  --plan stagemesh-qualification-plan.json \
  --result independent-witness-result.json \
  --artifacts-dir ./evidence \
  --review-key-file /etc/stagemesh/qualification-review-key.json \
  --decision approve \
  --output independent-witness-review.json
```

An approval is accepted only when the result itself passed, every required claim is true and every required evidence artifact verifies. The output is HMAC-authenticated and binds the canonical result SHA-256, exact plan/build, hashed reviewer identity and backlog IDs. It sets `eligibleForBacklogReview=true`; it **does not** edit the backlog or authorize physical output. Rejection and `needs-evidence` decisions are also authenticated.

Verify an existing review with `--verify <review.json>` using the same private reviewer key. Reviewer-key custody is a release-process control, not a substitute for independent external evidence or organizational identity governance.

## Intake status

Checkpoint 65 adds a directory-level intake view for one exact-build plan. Each task directory may contain `result.json`, `review.json` and an `artifacts/` directory. Run:

```sh
stagemesh-qualification-status.py \
  --plan stagemesh-qualification-plan.json \
  --submissions-dir ./qualification-submissions \
  --review-key-file /etc/stagemesh/qualification-review-key.json \
  --output stagemesh-qualification-status.json
```

The helper revalidates the result, re-hashes the actual artifacts, verifies the review HMAC/result digest and checks that the review's artifact-verification set exactly matches the files now present. Task states are `pending`, `awaiting-review`, `approved`, `rejected`, `needs-evidence` or `invalid`. Changed evidence after review becomes `invalid`. `allTasksApproved` is only a mechanical summary of that exact plan; it does not close backlog rows or authorize deployment.
