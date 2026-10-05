# Astra checkpoint 47 validation — signed technology conformance receipts

Checkpoint 47 replaces string-shaped maturity credentials with signed Public Record evidence for technology Standard recognition and Core-elevation assessment.

## Evidence binding

- `POST /api/v1/technology/conformance-receipt` is an admin-authorized evidence-publication surface. It does not grant show authority or arm outputs.
- The receipt binds a SHA-256 digest of the normalized evidence fields this core actually understands: declared maturity, independent implementations/groups, conformance/interoperability claims, fallback/backward-compatibility, unknown preservation, production count and vendor/cloud/AI dependency constraints.
- The receipt reference itself and unknown future extension metadata are excluded from the digest. Unknown metadata still round-trips, but an older core cannot accidentally sign evidence semantics it does not understand.
- The signed record is stored as Public Record type `technology-conformance` and is addressed as `upp-public-record:<recordId>:<recordHash>`.
- Resolution verifies the entire signed Public Record chain before matching the exact record id/hash and expected record type.

## Assessment rules

- A declared `standard` is not accepted by the runtime assessment merely because the extension contains a plausible-looking `adoptionRecordRef`. A verified signed conformance receipt is required.
- Changing any covered evidence field after receipt publication makes the receipt stale and the Standard declaration invalid until new eligible evidence is published.
- A previously signed Standard can remain recognized when ecosystem scale later increases, while `scaleRevalidationNeeded` records that current-scale evidence is broader than the adoption-time evidence.
- Core elevation is stricter: the receipt must have been issued when the evidence was Core-eligible under the current scale tier and current Core-group threshold. An older lower-scale receipt cannot authorize a new Core elevation.
- Receipt publication itself requires the current evidence to be eligible. A node cannot manufacture a new Standard/Core receipt for evidence that fails the applicable current-scale rules.

## Authorization and real-time boundary

- Conformance receipt publication stays on the existing specialized admin credential boundary rather than inheriting ordinary human operator roles.
- Admin allow/deny decisions continue to enter the checkpoint-36 durable authorization audit.
- Public Record lookup/digest verification is control-plane work only. No audio/MIDI/lighting callback performs this I/O or hashing.

## Validation

Validated on 2026-09-14:

- fresh Release + `STAGEMESH_RT_QUALIFICATION=ON` native build;
- native CTest: **2/2 passed**;
- full Python suite against that fresh engine: **548 tests passed with zero test skips**;
- focused technology/Public Record/authorization tests passed, including missing receipt, fake reference, stale evidence, grandfathered Standard recognition and current-scale Core receipt fencing;
- automation-performance report passed;
- **121 JSON schemas plus OpenAPI parsed**;
- **7/7 frontend JavaScript files** passed `node --check`.

The release wrapper's own clean build was represented by the explicit equivalent bounded steps above; no native source changed in this checkpoint.

## Remaining risk

A node signature proves that StageForge recorded and assessed the stated evidence; it is not by itself proof that the independent implementations or interoperability tests happened in independently controlled infrastructure. Production-independent witness deployment and witness clock/failure-domain qualification remain separate evidence work.

Per operator direction, the next checkpoint prioritizes the **independent witness option** before community-governance/Public Record expansion.
