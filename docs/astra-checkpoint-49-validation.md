# Astra checkpoint 49 validation — community governance Public Record binding

Checkpoint 49 binds community-governance evidence into the signed/witnessable Public Record without publishing voter identities or individual choices.

## Evidence model

- Every proposal version created or materially edited in a runtime with Public Record enabled receives a `community-proposal-version` record.
- Vote invitations receive `community-vote-invitation` records containing proposal/version, invitation id, delivery status and immutable voting-window timestamps.
- Invitation Public Record payloads deliberately exclude `userId`, email address, token hashes and message contents.
- Each cast ballot receives a random public ballot id plus a salted SHA-256 choice commitment in a `community-ballot` record.
- Ballot Public Record payloads deliberately exclude account identity, email address, the actual yes/no/abstain choice and the private commitment salt.
- The private governance store retains the actual vote for tallying and the commitment salt for selective audit disclosure; the API detail view redacts the salt.
- Adoption publishes one `community-ratification` record with aggregate yes/no/abstain counts, approval/durable totals and exact references to the proposal, invitation and ballot evidence. It contains no voter-to-choice map.

## Fail-closed binding

When Public Record integration is active, `bindingChangeReady` is false if the current proposal version, any current invitation or any current ballot is missing signed Public Record evidence.

If Public Record publication is interrupted after governance state is already durable, the affected object is marked pending and further proposal mutation/adoption is fenced until reconciliation. `POST /api/v1/community/public-record/reconcile` is admin-authorized and republishes missing current-version proposal/invitation/ballot evidence. It never reconstructs or publishes voter identity/choice data.

This keeps email delivery realistic: an already-sent email is not pretended away merely because the evidence ledger was temporarily unavailable, but that proposal cannot become binding until evidence is repaired.

## Validation

Validated on 2026-09-14:

- fresh Release + `STAGEMESH_RT_QUALIFICATION=ON` native build;
- native CTest: **2/2 passed**;
- full Python suite against that engine: **559 tests passed**;
- focused community-governance suite: **18 tests passed**;
- new regressions cover recipient/choice redaction, salted ballot commitments, aggregate ratification records, pending-evidence fencing/reconciliation and real Public Record integration;
- automation-performance gate passed: **4096 points / 8192 reads / 8192 frames in 7.545 ms**;
- **124 JSON schemas plus OpenAPI parsed**;
- **7/7 frontend JavaScript files** passed `node --check`.

No native real-time source changed in this checkpoint. Governance and Public Record work remains control-plane filesystem/administrative activity.

## Remaining boundary

Checkpoint 49 makes governance history independently auditable at the proposal/version/invitation/opaque-ballot/aggregate-ratification level without exposing individual choices. It does not replace account authentication. Production voting still depends on the trusted proxy identity plus the emailed one-time invitation credential; the next local software backlog slice is a real account-auth voting adapter that can bind an authenticated account session without treating a forwarded magic link as the primary account credential.
