# Astra checkpoint 63 validation — exact-build external qualification bundle

Checkpoint 63 does not mark any external qualification gate complete. It defines the machine-readable handoff that those environments must use so evidence cannot accidentally be applied to a different StageMesh build.

## Build binding

`backend/qualification_bundle.py` computes:

- a deterministic SHA-256 fingerprint across backend, frontend, native, schema, script and packaging inputs;
- the exact built native-engine SHA-256;
- a `planId` derived from the canonical qualification-plan content.

The plan currently contains eight tasks: independent witness, LAN security, Linux clean-host packaging, Windows platform, macOS platform, assistive technology, licensed plugin matrix and named stage hardware. Each task carries the relevant backlog IDs, required environment, existing helper command where one exists, and a fixed list of required pass/fail claims.

## Result envelope

A qualification result must match the exact plan ID and build digests. It also requires:

- a hashed runner identity rather than a raw hostname/account identity;
- a platform description;
- a boolean value for every required task claim;
- every required claim set true before `passed=true` is accepted;
- at most 64 artifact references with exact SHA-256 digests;
- `physicalOutputsArmed=false`.

The validator rejects foreign/tampered plan IDs, foreign build hashes, unknown tasks, raw runner identities, missing/non-boolean claims, passing results with any false claim and malformed artifact digests.

## Installed tooling

`stagemesh-qualification-plan.py` is installed with the other qualification helpers and is checked by checkpoint 61's isolated-rootfs packaging qualifier. JSON Schemas define both plan and result envelopes.

## Reference plan

The checkpoint run generated an exact plan with **8 tasks**. The retained external report contains its `planId`, source fingerprint and native-engine hash so later host runs can prove they used this exact build.

## Full gate

- Qualification-bundle/package focused tests pass **9/9**.
- Release Python suite passes **621 tests**.
- RT native CTest passes **2/2**; native source is unchanged.
- Automation-performance passes.
- All **128 schemas plus OpenAPI** parse.
- All **7 frontend JavaScript files** pass Node syntax checking.

## Remaining

Every task in the generated plan remains an external evidence gate until it is actually run in the required environment. A passing envelope is evidence input, not an automatic support claim or backlog mutation.
