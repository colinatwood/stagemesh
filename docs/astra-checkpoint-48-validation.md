# Astra checkpoint 48 validation — strict independent-witness deployment mode

Checkpoint 48 implements the operator-selected independent-witness option as a strict deployment contract rather than treating a comma-separated URL list as evidence of independence.

## Strict topology contract

- `STAGEMESH_WITNESS_TOPOLOGY_FILE` opts a StageMesh node into strict independent-witness mode.
- The topology file is a bounded private regular file: absolute path, effective-UID ownership, no group/other permissions, no symlink following, stable metadata while read, duplicate JSON keys rejected and a 64 KiB cap.
- It declares an explicit majority quorum, bounded clock-skew policy and one entry per witness.
- Every witness entry must have a unique URL, `witnessId`, declared `failureDomain` and pairwise rotating HMAC keyring path.
- Non-loopback witness endpoints require HTTPS. Plain HTTP is accepted only for an explicitly enabled loopback qualification topology.
- Each per-witness keyring is validated at topology load. One quorum operation pins one immutable keyring snapshot per endpoint, so credential rotation cannot mix keys inside a single vote/transfer/recovery operation.

Legacy `STAGEMESH_WITNESS_URLS` plus a shared witness secret/keyring remains supported for compatibility, but it is not reported as independent mode.

## Witness identity and clock fencing

Strict clients accept a vote only when the authenticated response contains the exact configured witness identity and failure domain. A response from the wrong witness/domain does not count even when its other lease facts look valid.

Every strict response also carries signed `serverUnixMs`. StageMesh compares that value with the local wall clock and rejects the vote when the absolute skew exceeds `maxClockSkewMs`. This does not make wall clocks a media clock; it bounds the persisted lease-expiry assumptions used by quorum authority.

`GET /api/v1/witness` status now exposes strict-mode identity/domain/skew configuration and deliberately reports `physicalIndependenceQualified: false`. Configuration cannot self-award physical failure-domain qualification.

## Strict witness service

When `STAGEMESH_WITNESS_INDEPENDENT=1`, a witness service requires:

- `STAGEMESH_WITNESS_ID`;
- `STAGEMESH_WITNESS_FAILURE_DOMAIN`;
- its own explicit `STAGEMESH_WITNESS_KEYRING_FILE`.

It refuses legacy environment/shared-secret fallback. Health reports the configured identity/domain and strict-mode state. Lease responses bind that identity/domain into the authenticated response.

Linux packaging now includes:

- `stagemesh-witness.service`, hardened and loopback-only by default;
- `packaging/stagemesh-witness.env.example`;
- `stagemesh-witness-qualify.py` as an installed reference-qualification helper.

Production deployment should terminate TLS on each independent witness host and expose only the HTTPS endpoint to StageMesh nodes.

## Reference qualification drill

`scripts/stagemesh-witness-qualify.py` launches three independent-mode **processes** on loopback, each with a distinct identity, declared failure domain and keyring. It passed these phases on 2026-09-14:

1. three-witness acquisition: **3 grants; lease valid**;
2. one witness stopped: planned transfer to the named successor: **2 grants; transferred**;
3. successor renewal with one witness still stopped: **2 grants; lease valid**;
4. two witnesses stopped: **1 grant; lease invalid**.

The machine-readable report says `referenceOnly: true` and `physicalIndependenceQualified: false`. Separate loopback processes prove protocol behavior, not independent power, hypervisor, network or physical host failure domains.

## Regression validation

Validated on 2026-09-14:

- fresh Release + `STAGEMESH_RT_QUALIFICATION=ON` native build;
- native CTest: **2/2 passed**;
- full Python suite against that engine: **555 tests passed with zero skips**;
- focused witness/infrastructure/installer group: **71 tests passed**;
- strict-topology tests cover weak quorum, duplicate failure domains/keyrings, unsafe file permissions, plaintext non-loopback endpoints, wrong witness identity, excess clock skew, cross-witness key misuse and one-/two-vote loss;
- automation-performance gate passed: **4096 points / 8192 reads / 8192 frames in 5.665 ms**;
- **123 JSON schemas plus OpenAPI parsed**;
- **7/7 frontend JavaScript files** passed `node --check`;
- the executable 3-process witness reference qualification passed all four phases above.

No native real-time source changed in this checkpoint. Witness configuration, HMAC, HTTP and filesystem work remain control-plane operations.

## Remaining qualification boundary

Checkpoint 48 makes StageMesh **independent-witness deployment capable**; it does not prove the configured witnesses are physically independent.

Before a production failover claim, the remaining operator-selected evidence task is a real multi-host drill using the intended witness machines/failure domains. That drill should capture clock skew, network/power isolation, one- and two-witness loss, primary isolation, standby promotion, planned handoff, persistently fenced-node recovery and physical-output arming state.

The real deployed TLS/proxy/IdP/firewall qualification also remains separate. Community-governance/Public Record expansion stays behind the independent-witness path per operator direction.
