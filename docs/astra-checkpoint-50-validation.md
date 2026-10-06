# Astra checkpoint 50 validation — trusted account-auth community sessions

Checkpoint 50 removes production community voting's dependence on a forwarded email magic-link credential by adapting the existing trusted authentication-proxy identity into a short-lived StageMesh community account session.

## Account session contract

- `POST /api/v1/community/session` requires a valid `X-StageMesh-Authenticated-User` identity injected with the configured trusted `X-StageMesh-Auth-Proxy-Token`.
- The identified user must already be an active StageMesh community account.
- StageMesh returns a bounded HMAC-SHA256 signed bearer session containing only account id, persisted auth generation, random session id, issue time and expiry.
- `STAGEMESH_COMMUNITY_SESSION_TTL_SECONDS` defaults to 900 seconds and is bounded to 60–86400 seconds.
- Session tokens are purpose-domain-separated and are never persisted or copied into the Public Record.
- Session verification rejects malformed tokens, signature tampering, future-issued credentials and expiry.

## Revocation and migration

Community accounts now persist `authGeneration`.

- Pre-checkpoint accounts migrate lazily to generation 1.
- `POST /api/v1/community/session/revoke` requires the same trusted proxy identity and increments that account's generation, invalidating every previously issued session.
- Changing an account email or active state also increments the generation.
- Display-name-only edits do not revoke otherwise valid sessions.
- A session whose signed generation differs from the current active account is rejected before any vote mutation.

## Voting behavior

`POST /api/v1/community/vote` now accepts either the existing one-time invitation token or a `sessionToken` plus `proposalId`, never both.

Account-session voting still requires exactly one active emailed invitation for that account and the proposal's current version. The invitation continues to define the immutable voting window and provides notification evidence; it is no longer the account authentication credential.

The existing one-account/one-vote ID, proposal-version fencing, Public Record ballot commitment and aggregate ratification rules remain unchanged. Account-session votes are marked privately with `authMethod: account-session`; that field is not added to the privacy-preserving public ballot payload.

Development token-only voting remains an explicit opt-in escape hatch through `STAGEMESH_GOVERNANCE_TOKEN_ONLY=1` and is not the production recommendation.

## Validation

Validated on 2026-09-14:

- fresh Release + `STAGEMESH_RT_QUALIFICATION=ON` native build;
- native CTest: **2/2 passed**;
- full Python suite against that engine: **566 tests passed**;
- focused community/account-auth coverage passes session signature/tamper/expiry, TTL bounds, legacy-account migration, generation revocation, email/active revocation, invitation requirements and no-magic-link session voting;
- real HTTP regression proves trusted-proxy session issuance, session-only voting, explicit revocation and subsequent denial;
- automation-performance gate passed: **4096 points / 8192 reads / 8192 frames in 6.407 ms**;
- **125 JSON schemas plus OpenAPI parsed**;
- **7/7 frontend JavaScript files** passed `node --check`.

No native real-time source changed in this checkpoint. Session issuance/verification and governance voting remain control-plane work.

## Remaining boundary

Checkpoint 50 completes the local community-governance/account-auth software path using StageMesh's reviewed trusted-proxy boundary. It does not itself deploy or certify an external identity provider. Real venue/control-LAN IdP, proxy, certificate and firewall qualification remains a separate deployment gate.

The remaining high-priority backlog is now dominated by evidence or platform work that cannot honestly be closed in this Linux/container environment: real multi-host independent-witness drills, deployed LAN qualification, clean-host service/device permission exercises, Windows/macOS implementations and runs, licensed plugin matrices, rendered browser/assistive-technology acceptance and named-hardware stage qualification.
