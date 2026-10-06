# Astra checkpoint 64 validation

Checkpoint 64 turns the checkpoint-63 external qualification plan into a reviewable evidence pipeline instead of a collection of self-asserted booleans.

## Contract changes

- Every external task declares required artifact classes in addition to required claims.
- Passing results must include each required artifact class with a safe relative path, SHA-256 and byte count.
- `stagemesh-qualification-review.py` verifies the result against the exact plan/build and re-hashes every referenced evidence file under a caller-supplied artifact root.
- Review keys must be absolute, owner-only regular files and identify the authorized reviewer only by SHA-256.
- Approve/reject/needs-evidence envelopes are HMAC-authenticated and bind the canonical result digest, exact build, reviewer, task/backlog IDs, claims and verified artifacts.
- Approval only sets `eligibleForBacklogReview=true`; no code path mutates backlog state or arms physical output.

## Safety boundaries

The review key authenticates a StageMesh release-review decision; it does not prove that an external runner, witness host, LAN, plugin license, assistive-technology exercise or named hardware is genuinely independent. Those facts remain properties of the reviewed evidence. Raw large artifacts remain outside the review envelope and are referenced by bounded path/digest/size metadata.

## Validation

Focused qualification-bundle/review/installer/package tests pass. The full release Python suite passes **627 tests with zero skips**; fresh RT native CTest passes **2/2**. Automation-performance passes, all **129 JSON schemas plus OpenAPI** parse, and all **7 frontend JavaScript files** pass syntax checking. An end-to-end reviewer self-test generated an exact-build independent-witness template, hashed real evidence files, authenticated an approval and verified the review signature/result digest.
