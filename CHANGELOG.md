# Changelog

## StageMesh identity migration — 2026-10-06

- Remove the retired product name from source, native namespaces and include
  paths, build targets, scripts, services, environment variables, HTTP headers,
  fixtures, documentation, and backlog workbooks.
- Standardize the only supported runtime and deployment contracts on
  `StageMesh`, `stagemesh`, and `STAGEMESH` forms. This is an intentional
  developer-alpha breaking change; retired aliases are not retained.
- Add a repository-wide regression that scans path names, UTF-8 text, and XML
  inside tracked workbooks so the retired identity cannot be reintroduced.

This migration changes software identifiers only. It does not establish
signing, clean-host, accessibility, physical hardware, or external product
qualification.

## Desktop release hardening — 2026-10-05

- PR #84 adds a self-contained `verify-download.py` to every Windows, macOS,
  and Linux desktop bundle. It checks manifest consistency, exact file bytes and
  SHA-256 values, safe paths, unexpected files, and signing-report binding. It
  is an integrity and consistency check, not publisher authentication.
- PR #85 adds an authenticated loopback-only desktop shutdown route. The Tauri
  supervisor requests graceful sidecar cleanup, waits for a bounded interval,
  and retains a force-termination fallback when the sidecar is unresponsive.
- Hosted CI builds and packages all three desktop variants and runs the
  complete-bundle verifier. The current local Python suite passes 731 tests
  with 24 expected skips.
- PR #86 refreshes `PROJECT_MASTER.md` with the current baseline, workflow
  evidence, exact next action, and unresolved signing, legal, clean-host,
  hardware, and audible-quality boundaries.

These entries document software evidence only. They do not establish signing,
notarization, legal approval, clean-host installation, accessibility
qualification, physical audio/MIDI support, or audible/recording quality.

## Astra backlog checkpoint 68 — explicit service-identity device-permission qualification helper

- Add an installed `stagemesh-device-permissions.py` helper that must run as the requested StageMesh service identity and evaluates explicit named device nodes.
- Require absolute non-symlink character-device paths with bounded `r`, `w` or `rw` access requests; missing, regular-file and symlink targets fail closed.
- Report device major/minor, ownership/mode and effective access without changing permissions, groups, udev policy or physical-output authority.
- Package the helper and include it in the isolated-rootfs installation manifest so real clean-host qualification uses the same installed tool.
- Keep hardware permission qualification external: `/dev/null` reference coverage proves helper semantics, not ALSA/MIDI/UWB access.

## Astra backlog checkpoint 67 — live Windows named-pipe DACL attestation

- Inspect the kernel security descriptor on each `CreateNamedPipeW` handle before accepting a client instead of trusting the requested SDDL alone.
- Require a protected, non-null DACL whose allow-ACE SID set exactly matches SYSTEM plus configured service/operator SIDs (and Administrators only when explicitly opted in).
- Reject extra principals, missing principals, deny/unknown ACE types and access masks that differ from the configured Generic All policy.
- Keep injected listeners on the explicit validator path while the native listener advertises only policy enforcement; actual DACL attestation happens on the created kernel handle before `ConnectNamedPipe`.
- Preserve checkpoint-59 bounded authenticated UPPF framing and checkpoint-66 explicit-SID construction.
- Linux contract tests cover accepted/rejected ACL facts; actual Win32 `GetSecurityInfo` execution remains target-OS qualification.

## Astra backlog checkpoint 66 — protected Windows named-pipe DACL runtime foundation

- Add a stdlib-only Win32 named-pipe listener using `CreateNamedPipeW` in message mode with the same bounded UPPF transport bytes as checkpoint 59.
- Build a protected DACL from SYSTEM plus explicit configured SID strings; broad symbolic principals such as Everyone, Authenticated Users and Builtin Users are rejected.
- Keep Administrators opt-in rather than silently granting them named-pipe access.
- Configure the native listener to fail closed when no explicit service/operator SID is supplied; injected/test listeners still require an explicit ACL validator.
- Add bounded Win32 read/write handling, first-pipe-instance protection and cleanup/disconnect behavior without changing UPPF capability/session/HMAC semantics.
- Linux-side tests validate DACL construction and native-listener policy; actual Windows DACL creation/client denial/runtime execution remains required before `IPC-033` can close.

## Astra backlog checkpoint 65 — external qualification intake/status aggregation

- Add an installed `stagemesh-qualification-status.py` helper that scans exact-build task submissions and reports pending, awaiting-review, approved, rejected, needs-evidence or invalid.
- Re-hash every referenced artifact during intake and compare it with the authenticated review, so evidence modified after approval becomes invalid rather than silently remaining approved.
- Keep status summaries build-bound to the exact qualification plan and expose only hashed reviewer identity/result digests.
- Add JSON Schema coverage for the aggregate status document and package/install the status helper with the other qualification tools.
- Preserve manual backlog governance: aggregate `approved` status is evidence readiness, not an automatic Done transition or physical-output authority.
- Release Python suite passes 631 tests; RT native CTest passes 2/2. Automation-performance, all 130 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 64 — authenticated external qualification evidence review

- Require passing external qualification results to carry task-specific evidence artifact classes, safe relative paths, byte counts and SHA-256 digests.
- Add an installed `stagemesh-qualification-review.py` helper that verifies exact plan/build/result binding and hashes the actual evidence files before review.
- Add private reviewer-key files with owner-only permissions and HMAC-authenticated approve/reject/needs-evidence review envelopes.
- Bind review decisions to a canonical result digest, reviewer identity hash, task/backlog IDs, verified artifacts and `physicalOutputsArmed=false`.
- Keep backlog mutation manual: an approved review is only `eligibleForBacklogReview`, never an automatic Done transition.
- Add JSON Schema coverage for review envelopes and extend plan/result schemas with required artifact classes and file metadata.
- Release Python suite passes 627 tests; RT native CTest passes 2/2. Automation-performance, all 129 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 63 — exact-build external qualification bundle

- Add a deterministic external qualification plan bound to a SHA-256 source fingerprint and exact native-engine SHA-256.
- Enumerate eight external gates: independent witness, LAN security, clean Linux packaging, Windows, macOS, assistive technology, licensed plugin matrix and named stage hardware.
- Add per-task required boolean claims, backlog IDs, environment descriptions and existing qualification commands where available.
- Add bounded result envelopes that require exact plan/build matching, hashed runner identity, all required claims for a passing result, bounded SHA-256 artifact references and `physicalOutputsArmed=false`.
- Install `stagemesh-qualification-plan.py` and include it in the isolated-rootfs packaging qualification.
- Add JSON Schemas for external qualification plans/results.
- Release Python suite passes 621 tests; RT native CTest passes 2/2. Automation-performance, all 128 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 62 — Chromium accessibility-tree reference qualification

- Extend the real-Chromium operator qualification with a full Chromium accessibility-tree inspection at the desktop reference viewport.
- Require a main landmark, focusable skip link, named/focusable launcher controls, bounded BPM spinbutton semantics, key combobox semantics, four named player buttons and multiple polite live regions.
- Fail qualification on unnamed exposed interactive controls or ignored nodes that remain focusable.
- Reference run exposes 781 accessibility nodes, 86 interactive nodes and four polite live regions with zero unnamed interactive controls and zero ignored-focusable nodes.
- Keep `assistiveTechnologyQualified=false`; Chromium AX-tree semantics do not replace NVDA/VoiceOver/switch/voice-control exercises.
- Release Python suite passes 618 tests; RT native CTest passes 2/2. Automation-performance, all 126 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 61 — isolated Linux rootfs packaging qualification

- Add an installed `stagemesh-package-qualify.py` helper that exercises the real Linux installer inside a fresh staged rootfs.
- Provision the staged `stagemesh` account with `systemd-sysusers` and the state directory with `systemd-tmpfiles`; verify numeric ownership and mode `0750`.
- Verify both packaged systemd units with `systemd-analyze verify` and assert the installer never enables services automatically.
- Prove reinstall preserves persistent state, ordinary uninstall preserves state while removing program files, and explicit `--purge-data` removes state.
- Emit an explicit machine-readable report with `cleanHostQualified=false` and `hardwarePermissionsQualified=false`; isolated-rootfs evidence does not replace a real host/device exercise.
- Release Python suite passes 616 tests; RT native CTest passes 2/2. Automation-performance, all 126 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 60 — fail-closed Windows/macOS plugin launch attestation contract

- Remove the remaining non-Linux path-digest launch fallback for external plugin adapters.
- Require Windows manifests to declare an exact Authenticode publisher-certificate SHA-256 plus runtime file-identity binding.
- Require macOS manifests to declare an exact Team ID plus exact code-directory hash.
- Add bounded platform launch-evidence validation for adapter digest, signing identity and runtime file identity.
- Refuse Windows/macOS external adapter launch until a native platform binder proves the launched process is the same verified object.
- Keep Linux `/proc/self/fd` SHA-256/inode launch binding unchanged.
- Release Python suite passes 614 tests; fresh RT native CTest passes 2/2. Automation-performance, all 126 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.
- Real Windows/macOS binder implementation and licensed plugin qualification remain open.

## Astra backlog checkpoint 59 — Windows UPPF named-pipe transport/security foundation

- Factor exact bounded length-prefixed UPPF transport packets so stream and message transports carry identical authenticated channel bytes.
- Reject truncated, oversized and trailing-byte message packets before UPPF decode.
- Factor the bounded authenticated request loop so Unix sockets and future Windows named pipes share capability/session/sequence/HMAC handling.
- Add a StageMesh-scoped Windows named-pipe server contract using `AF_PIPE` only on Windows.
- Require a positive explicit ACL validator before named-pipe startup; missing/failed validation is fail-closed and closes the listener before accepting requests.
- Keep pipe names inside `\\.\pipe\StageMesh\<safe-name>` and bound per-connection request counts.
- Release Python suite passes 610 tests with zero skips; RT native CTest remains 2/2. Automation-performance, all 126 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.
- Real Windows DACL creation/inspection, service identity integration and Windows client/server execution remain open before `IPC-033` can be completed.

## Astra backlog checkpoint 58 — backend-neutral physical audio execution fencing

- Remove remaining shared-runtime assumptions that a physical audio stream must report `execution=alsa`.
- Treat future WASAPI/CoreAudio and other explicit non-null execution backends as physical while keeping `none`, `bridge-only` and null backends non-physical.
- Revalidate endpoint identity immediately after any physical output/input starts and stop the just-started stream if the desired endpoint disappeared or no longer resolves.
- Mark post-promotion physical audio only after the output survives that identity fence.
- Make audio status use the same backend-neutral physical classification so future platform streams are not falsely reported inactive.
- Keep the ALSA preflight explicitly ALSA-only: an explicit non-ALSA device fails with a platform-preflight-adapter error rather than being forced through a fake `hw:X,Y` contract.
- Preserve legacy/fixture calls without backend metadata by treating them as ALSA preflight requests.
- Release Python suite passes 604 tests with zero skips; RT native CTest remains 2/2. Automation-performance, all 126 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.
- Real Windows/macOS preflight/configuration, stream execution and hardware qualification remain open.

## Astra backlog checkpoint 57 — cross-platform device lifecycle reconciliation

- Generalize unsafe audio endpoint disconnect/identity-change handling so active streams stop regardless of execution backend instead of only when the backend string is `alsa`.
- Make MIDI identity observation non-authoritative: an already pinned native token cannot silently adopt a different persistent identity.
- Add exact-unique persistent MIDI identity resolution across native endpoint-ID churn while preserving the original logical show binding.
- Reject duplicate persistent MIDI identity matches rather than guessing which endpoint should inherit a binding.
- Detach disappeared or identity-replaced MIDI inputs before any rebind attempt and publish bounded MIDI hotplug generation/change evidence.
- Serialize MIDI scans/reconciliation just like audio scans so concurrent polling/control paths cannot race attachment decisions.
- Keep replacement selection separate from activation; no hotplug path automatically arms audio or other physical outputs.
- Fresh RT CTest passes 2/2; the release Python suite passes 600 tests with zero skips. Automation-performance, all 126 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.
- Real Windows/macOS enumeration/change notifications, physical audio/MIDI execution and platform qualification remain open.

## Astra backlog checkpoint 56 — cross-platform persistence-grade audio/MIDI identity contract

- Extend the audio identity layer with explicit WASAPI and CoreAudio identity-strength contracts for future platform adapters.
- Allow automatic WASAPI reconnect only from a SHA-256-hashed persistence-grade StableId; ordinary installation-scoped endpoint hashes remain explicit-recovery-only.
- Allow automatic CoreAudio reconnect only from a hashed device UID; raw private identifiers are rejected.
- Extend MIDI identity with hashed CoreMIDI unique/connection IDs and a Windows MIDI contract that requires the platform adapter to explicitly attest persistence-grade identity.
- Keep weak/snapshot/raw identifiers fail-closed as volatile or explicit-rebind-only, preserving the existing ambiguity rejection in the identity stores.
- Add six cross-platform identity-strength regressions without changing Linux ALSA behavior.
- The release Python suite passes 584 tests with zero skips; RT native CTest remains 2/2. Automation-performance, all 126 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.
- Real Windows/macOS enumeration, hotplug callbacks, stream stops/reselection and hardware qualification remain open.

## Astra backlog checkpoint 55 — Windows/macOS audio endpoint and installed-driver evidence adapters

- Add a fixed read-only Windows AudioEndpoint and signed MEDIA-class PnP driver probe alongside the existing USB inventory.
- Hash opaque Windows endpoint/PnP instance identifiers before export; retain only exact USB VID/PID when safely derivable.
- Keep installed Windows driver provider/version/INF/signature evidence separate from the reviewed package catalog and from hardware qualification.
- Add a macOS `SPAudioDataType` CoreAudio evidence adapter that hashes reported device UIDs and records manufacturer/transport/channel hints without inventing Windows-style package semantics.
- Keep endpoint-probe failures isolated from the existing USB inventory so partial diagnostics remain useful and explicitly report the missing evidence.
- Fresh RT CTest passes 2/2; the release Python suite passes 578 tests with zero skips. Automation-performance, all 126 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.
- Windows/macOS execution on real hosts, persistent device/hotplug behavior, audio negotiation and named-hardware qualification remain separate.

## Astra backlog checkpoint 54 — rendered browser and responsive operator acceptance

- Add a repeatable real-Chromium operator qualification helper covering desktop, tablet and phone reference viewports.
- Execute the production HTML/CSS/JavaScript and bridge client fetches to the real StageMesh loopback handler when managed Chromium blocks direct loopback navigation.
- Verify keyboard skip navigation, rendered player controls, launcher visibility and a safe show-state edit without arming physical outputs.
- Fix a 390 px viewport overflow by allowing grid children and paired form controls to shrink instead of forcing min-content width.
- Keep assistive-technology and deployed browser/LAN qualification explicitly open; the report sets both related claims false.
- Fresh RT CTest passes 2/2 and the release Python suite passes 573 tests with zero skips. Automation-performance, all 126 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 53 — proactive driver-catalog review audit

- Add an offline `stagemesh-driver-catalog-audit.py` utility with deterministic `--as-of` and configurable review-warning horizon.
- Report current, review-due, stale, unreviewed and invalid package counts plus per-record days to expiry.
- Keep catalog usability fail-closed for invalid/stale/unreviewed records while allowing current-but-soon-expiring records to raise review attention before expiry.
- Add `org.upp.driver-catalog-audit-report` schema and install the audit tool with the Linux qualification utilities.
- Bundled checkpoint-52 catalog reports 5/5 current records and no review attention at a 30-day horizon on 2026-09-14.
- Release Python suite passes 572 tests on rerun; native RT CTest remains 2/2. Automation-performance, all 126 schemas/OpenAPI/catalog JSON and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 52 — reviewed Focusrite Scarlett 4th Gen driver metadata

- Expand the reviewed driver catalog with Windows 10/11 AMD64 package-metadata records for Focusrite Scarlett Solo, 2i2 and 4i4 4th Gen.
- Bind the entries to exact USB identities `1235:8218`, `1235:8219` and `1235:821A` using independent hardware-ID evidence.
- Record Focusrite Control 2 1.1108.0 / Windows driver 4.150.0.432 from the current vendor release notes and product download pages.
- Keep review confidence moderate, expire the review on 2027-03-14 and deliberately add no Windows ARM64 claim.
- Preserve `package-metadata-only`, `automaticInstallAllowed: false` and `hardware-tests-required`; no device-support claim changes.
- Release Python suite passes 569 tests; native RT CTest remains 2/2. Automation-performance, all 125 schemas/OpenAPI/catalog JSON and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 51 — Linux verified plugin-adapter launch binding

- Close the Linux external-adapter digest-to-launch race by hashing an `O_NOFOLLOW` opened regular-file descriptor immediately before process creation.
- Launch external adapters through the inherited `/proc/self/fd/<fd>` handle so manifest-path replacement after verification cannot change the executed bytes.
- Keep Python adapter support by passing the inherited verified descriptor to the Python interpreter.
- Reject symlink adapters on Linux and preserve absolute-path, executable, host-system, architecture, protocol and SHA-256 manifest gates.
- Expose the Linux launch binding plus verified filesystem identity in plugin-host status without changing plugin authority or physical-output state.
- Add an adversarial path-replacement regression proving the verified inode executes even after the manifest path is atomically replaced before `Popen`.
- Fresh RT CTest passes 2/2 and the release Python suite passes 568 tests. Automation-performance, all 125 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 50 — trusted account-auth community sessions

- Add short-lived HMAC-signed community account sessions issued only from the trusted auth-proxy identity boundary.
- Bind sessions to persisted per-account `authGeneration`; explicit revocation plus email/active-state changes invalidate every older session.
- Lazily migrate pre-checkpoint accounts to auth generation 1 without invalidating stored governance state.
- Allow account-session voting by `sessionToken` + `proposalId` while still requiring exactly one active invitation for that account/current proposal version.
- Keep email invitations as immutable voting-window/notification evidence rather than the production account credential.
- Reject mixed magic-token/session authentication, signature tampering, expiry, future issuance, inactive accounts and revoked generations before vote mutation.
- Add trusted-proxy session issue/revoke HTTP surfaces and a community-session schema.
- Fresh RT CTest passes 2/2 and the release Python suite passes 566 tests. Automation-performance, all 125 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 49 — privacy-preserving community governance Public Record

- Bind each current proposal version to a signed `community-proposal-version` Public Record entry.
- Record vote invitations without publishing recipient account/email/token information.
- Give each ballot a random public id and salted SHA-256 choice commitment; the Public Record never contains the account identity, actual choice or private salt.
- Publish aggregate `community-ratification` evidence at adoption, referencing the exact proposal/invitation/ballot records without creating a voter-to-choice map.
- Fail binding closed when any current-version governance evidence is missing from the Public Record.
- Add admin-authorized Public Record reconciliation for interrupted publication; governance progression cannot silently skip pending evidence.
- Extend community proposal/invitation schemas and add a privacy-preserving public-ballot schema.
- Fresh RT CTest passes 2/2 and the release Python suite passes 559 tests. Automation-performance, all 124 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 48 — strict independent witness deployment

- Add a private `STAGEMESH_WITNESS_TOPOLOGY_FILE` contract with an explicit majority quorum, unique witness identities, unique declared failure domains, unique per-witness keyrings, bounded clock skew and HTTPS outside explicit loopback qualification.
- Pin one immutable HMAC key snapshot per witness for each quorum operation so independent credential rotation cannot mix keys mid-operation.
- Bind witness identity, declared failure domain and server wall clock into authenticated responses; wrong identity/domain and excess skew do not count toward quorum.
- Keep legacy shared-secret/shared-keyring witness configuration for compatibility but report strict independent mode separately and never infer physical independence from configuration.
- Harden independent witness startup: require identity/domain and an explicit witness keyring, forbid shared replication/witness secret fallback, and expose strict configuration health.
- Package a loopback-only `stagemesh-witness.service`, witness env example and installed reference qualification helper.
- Add a three-process reference drill: 3/3 acquire, 2/3 transfer and successor renewal after one witness loss, and quorum denial after two losses; the report explicitly states `physicalIndependenceQualified: false`.
- Add independent-witness topology/reference-report schemas, deployment documentation and strict topology/key/identity/skew regression coverage.
- Fresh RT CTest passes 2/2 and the release Python suite passes 555 tests with zero skips. Automation-performance, all 123 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 47 — signed technology conformance receipts

- Add stable `upp-public-record:<recordId>:<recordHash>` resolution that verifies the signed Public Record chain before accepting an exact record reference.
- Add bounded technology evidence digests covering only evidence fields understood by this core; unknown future metadata remains preserved but is not silently treated as trusted maturity evidence.
- Add an admin-authorized `POST /api/v1/technology/conformance-receipt` surface that publishes a signed `technology-conformance` Public Record entry only when current evidence is eligible.
- Require runtime Standard recognition to bind a verified receipt; fake, missing or evidence-stale references fail assessment.
- Preserve grandfathered Standard recognition after ecosystem growth when the original signed evidence remains intact, while continuing to report scale revalidation needs.
- Require Core-elevation receipts to match the current scale tier and Core-group threshold; old lower-scale receipts cannot authorize new Core elevation.
- Add conformance-receipt schema/OpenAPI coverage and specialized-route authorization coverage.
- Fresh RT CTest passes 2/2 and the release Python suite passes 548 tests with zero skips. Automation-performance, all 121 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 46 — signed operational Public Record and external witness attestations

- Add an append-only SHA-256-linked Public Record with node-identity HMAC signatures for adaptation and operational-authority evidence.
- Persist a stable Public Record reference onto committed Venue Patch Layer receipts before post-commit runtime evidence is emitted.
- Record authority lease grants and revocations; failed grant-record persistence revokes the new lease fail-safe, while failed revocation recording never restores authority.
- Add a separately configured external-witness policy with strict private-file handling and exact-record-hash HMAC attestations.
- Persist accepted external attestations in an independent hash-linked witness ledger and make exact witness/record replay idempotent.
- Add `GET /api/v1/public-record` verification status and `POST /api/v1/public-record/witness`; witness submissions use their separate machine credential rather than human control roles.
- Add Public Record reference/witness schemas and bind adaptation/authority receipt schemas to the reference contract.
- Release Python suite passes 545 tests; native RT CTest remains 2/2. Automation-performance, all 120 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 45 — generalized department/resource authority leases

- Generalize the Venue Patch Layer lease primitive into explicit `patch`, `department` and `resource` scope kinds without weakening cluster-primary/witness authority.
- Resolve exact resource ownership before department ownership, with known-resource/known-department validation and fail-closed rejection of typos or invented scopes.
- Separate scope type from lifecycle context: legacy venue patch/domain leases are cleared on venue remap while explicit runtime resource/department leases survive venue changes.
- Clear all ephemeral operational authority leases whenever node authority is fenced/lost; promotion never restores leases or physical output automatically.
- Preserve legacy `/api/v1/venue/authority` request compatibility while enriching status/audit evidence with `scopeKind`, `context` and active-by-kind views.
- Keep venue reconciliation exact-patch/domain semantics unchanged and prevent resource leases from masquerading as venue patch keys.
- Release Python suite passes 540 tests; focused authority/reconciliation tests pass 15/15; native RT CTest remains 2/2. Automation-performance, all 118 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 44 — sACN and semantic venue fixture mapping

- Add full 512-slot E1.31 data-packet encoding and an explicitly armed unicast sACN UDP adapter beside the existing Art-Net path.
- Select exactly one lighting network protocol at a time; reconfiguration disarms both transports and restart/demotion semantics remain non-authoritative.
- Add process-unique sACN CID, per-universe sequence counters and configurable E1.31 `universeBase` for the bounded 16-universe native DMX domain.
- Resolve portable `fixtureId` + semantic parameter + normalized value through the committed `lighting.primary` venue patch into bounded universe/channel/value execution.
- Reject missing fixture/parameter mappings, invalid normalized values and channel overflow rather than guessing venue wiring.
- Mark the sACN adapter implemented, make show compatibility protocol-aware, persist `universeBase`, add the fixture-map schema and expose Art-Net/sACN selection in the operator UI.
- Preserve raw DMX scheduling and Art-Net compatibility; venue patch activation still never arms physical output.
- Fresh RT CTest passes 2/2 and the release Python suite passes 533 tests with zero skips. Automation-performance, all 118 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 43 — reviewed driver-catalog evidence

- Advance the bundled driver catalog to schema v2 with explicit product/package identity, release and review dates, review expiry, confidence, claim scope and multi-source HTTPS provenance.
- Seed two architecture-specific reviewed package records for RME Babyface Pro FS proprietary USB mode on Windows, using RME's official driver listing plus separate exact USB-ID evidence.
- Keep catalog claims deliberately narrow: package metadata only, automatic installation disabled and hardware qualification still required.
- Preserve v1 catalog readability, but legacy/unreviewed matches now report `curated-match-unreviewed` instead of current reviewed evidence.
- Expired records remain visible as `curated-match-review-stale` and require re-review rather than silently disappearing or remaining trusted forever.
- Require exact hardware ID, OS, OS release and architecture before any current curated match.
- Add review/freshness/provenance regressions; fresh RT CTest passes 2/2 and the release Python suite passes 531 tests. Automation-performance, all 117 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.

## Astra backlog checkpoint 42 — sample-exact arbitrary arrangement loops

- Remove the 256-frame loop-length restriction from arrangement and clip playback while retaining fixed-size native producer submissions.
- Build each looping producer block from exact source slices and wrap inside the block as many times as required, eliminating block-tail silence at non-aligned loop boundaries.
- Keep clip loops at their exact clip length rather than rounding the loop end to the next producer block.
- Advance the native DAW playback playhead modulo the exact loop span and count every wrap when a callback crosses a short loop more than once.
- Preserve fixed-capacity/no-allocation native rendering and exact start-frame discontinuity fencing.
- Add Python/runtime/native regressions for 3-frame multi-wrap blocks, a 257-frame clip, a 300-frame live loop replacement and native multiple-wrap accounting.
- Fresh RT CTest passes 2/2 and the release Python suite passes 529 tests; automation-performance, all 117 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass. Physical/audible loop qualification remains open.

## Astra backlog checkpoint 41 — durable recording publication directories

- Add shared hard-link publication helpers that fsync the parent directory before publication is reported successful.
- Finalized recordings now fsync file bytes, publish by non-replacing hard link, fsync the directory, remove the partial path and fsync the directory again.
- Roll back a newly linked target best-effort when the first directory sync fails and retain the sealed partial for retry; no durability failure is reported as success.
- Preserve an already durable target when later partial cleanup or cleanup-directory sync fails and report `partialCleanupPending`.
- Apply the same publication boundary to recovered interrupted recordings and expose `directoryDurable` evidence.
- Add parent-directory fsync/rollback/degraded-cleanup regressions; fresh RT CTest passes 2/2 and the release Python suite passes 527 tests with zero skips. Automation-performance, all 117 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.
- Physical storage power-cut and audible hardware qualification remain open.

## Astra backlog checkpoint 40 — durable inode-bound temporary-resource ownership

- Add one version-2 owner-manifest contract shared by render/import staging, media snapshots and isolated plugin scratch.
- Bind exact process generation to exact filesystem object identity (device/inode/kind); missing, malformed, legacy or replaced evidence is unknown and never auto-reclaimed.
- Publish owner manifests atomically with file and directory fsyncs, including containing-store durability for directory-backed resources.
- Revalidate owner liveness and resource identity immediately before deletion so stale manifests cannot authorize cleanup of replacement objects.
- Clean newly-created resources when manifest/store durability publication fails before normal operation begins.
- Add unclean-process-exit, legacy, replacement, fsync-failure and exact-dead-owner regressions across staging, snapshots and plugin scratch.
- Fresh RT CTest passes 2/2 and the release Python suite passes 524 tests with zero skips; automation-performance, all 117 schemas/OpenAPI and all seven frontend JavaScript syntax checks pass.
- Recording parent-directory durability and physical storage/power-cut qualification remain open.

## Astra backlog checkpoint 39 — Linux integer/multichannel physical PCM adapters

- Carry explicit device PCM format/channel intent through activation preflight, conversion planning, Python→native stdio and the Linux ALSA stream adapters while preserving the legacy float-stereo command shape.
- Add dependency-free runtime ALSA format resolution for `FLOAT_LE`, `S16_LE`, packed `S24_3LE` and `S32_LE`; configured format must match the exact requested format.
- Preallocate float and device-PCM buffers before stream start, then encode playback and decode capture without allocation in the ALSA I/O loops.
- Make v1 channel conversion deterministic: mono playback averages L/R, mono capture duplicates, and multichannel uses device channels 0/1 for canonical L/R while extra playback channels are silent and extra capture channels are ignored.
- Keep rate/channel/sample-format execution separately permissioned by the existing explicit conversion flags; no silent fallback or format substitution is introduced.
- Prove the extended native path with 48 kHz 4-channel `S16_LE` playback and 4-channel packed `S24_3LE` capture against the ALSA null PCM.
- Add focused native/Python regressions; fresh RT native CTest passes 2/2 and the release Python suite passes 516 tests. Automation-performance passes, all 117 schemas/OpenAPI parse, and all seven frontend JavaScript files pass syntax checks. Conversion-quality and named-hardware qualification remain open.

## Astra backlog checkpoint 38 — controller HTTP workload and rate-policy qualification

- Add a repeatable local-reference HTTP workload harness that measures normal control responsiveness separately from abusive-rate containment.
- Replay a deterministic five-second policy model with four 20 rps controllers beside one 300 rps abusive peer; default policy admitted 400/400 controller requests and rejected 802 abusive requests.
- Run the real loopback StageMesh bridge under a mixed 120-request normal controller burst and a 320-request abusive burst; the reference run passed 120/120 normal requests at 22.903 ms p95 and returned 33 explicit 429 throttles with no unexpected statuses.
- Store the reference result under `qualification/http-workload-reference.json` and label it explicitly as neither physical-controller nor deployed-LAN qualification.
- Add three deterministic workload-helper regressions; release Python suite passes 513 tests with zero skips, native CTest passes 2/2, automation-performance passes, all 117 schemas/OpenAPI parse and all seven frontend JavaScript files pass syntax checks.

## Astra backlog checkpoint 37 — bounded expensive HTTP operations

- Add explicit non-blocking admission classes for known expensive maintenance, discovery, planning, storage and external-I/O HTTP operations.
- Bound total expensive work to four concurrent requests inside the existing 32-worker HTTP pool, with tighter class caps (maintenance 1, discovery 2, planning 3, storage 2, external 2).
- Reject saturated expensive work with 503/Retry-After before request-body execution while leaving ordinary health/control routes outside the expensive budget.
- Release cost slots in the handler `finally` path so route exceptions cannot leak capacity; injected-crash regression verifies recovery.
- Keep in-flight mutation semantics intact: StageMesh rejects excess admission rather than force-cancelling already-started stateful work.
- Add four operation-cost regressions; release Python suite passes 510 tests with zero skips, native CTest passes 2/2, automation-performance passes, all 117 schemas/OpenAPI parse and all seven frontend JavaScript files pass syntax checks.

## Astra backlog checkpoint 36 — specialized authorization audit unification

- Extend the existing durable authorization audit to the separate admin-token and adapter-report credential boundaries without granting those privileges to human roles.
- Record specialized allow/deny decisions before protected route execution using bounded action metadata only; credentials, request bodies, raw URLs and query strings are never copied.
- Add post-verification/pre-mutation audit hooks for authenticated replication apply and planned-handoff peer-readiness HMAC operations, including only bounded source/key identity after successful verification.
- Fail admin/adapter mutations closed when the durable audit cannot be appended; machine mutation hooks likewise run before the authenticated state change.
- Preserve direct private-helper compatibility by emitting request audit only when an actual HTTP request context exists.
- Add six specialized authorization regressions; the release Python suite passes 506 tests with zero skips, native RT CTest passes 2/2, automation-performance passes, all 117 schemas/OpenAPI parse, and all seven frontend JavaScript files pass Node syntax checks.

## Astra backlog checkpoint 35 — rotating witness/replication HMAC keyrings

- Add private owner-only replication and witness HMAC keyring files with bounded key IDs/secrets and atomic reload on the next control-plane operation.
- Carry an HMAC-covered `keyId` on replication envelopes, witness requests/responses and planned-handoff offers/readiness receipts when keyring mode is active.
- Pin one immutable key snapshot across each witness quorum operation so an atomic rotation cannot mix authentication keys mid-quorum.
- Require planned-handoff readiness to use the offer key, preserving transaction identity across active-key switches and failing closed if that key is removed too early.
- Reject missing/unknown key IDs in keyring mode; legacy single-secret environment variables remain compatibility mode only and are never a downgrade fallback.
- Preserve witness epoch/quorum fencing and explicit physical-output disarming; key rotation changes authentication, not authority.
- Add eight key-lifecycle regressions including a live production witness rotation; combined release Python suite passes 500 tests and native CTest remains 2/2.

## Astra backlog checkpoint 34 — bounded authorization-audit retention

- Segment the fsynced per-user authorization audit before its configurable byte threshold and keep one continuous SHA-256 chain across active and rotated files.
- Bound retained rotated segments and commit an atomic fsynced retention anchor containing the exact pruned-prefix head and record/segment counts before deleting old bytes.
- Make ENOSPC before anchor publication prune nothing; tolerate and report crash residue after anchor publication without reintroducing old records into the retained chain.
- Cache the verified audit head for steady-state appends while checking active/segment/anchor file identities, avoiding a full-history scan on every control mutation.
- Expand admin verification with retained/pruned counts, byte bounds, retention anchor and crash-residue diagnostics without returning actor history.
- Add five rotation/durability regressions; combined Python suite passes 492 tests and native CTest remains 2/2.

## Astra backlog checkpoint 33 — strict proxy-HTTPS deployment profile

- Add opt-in `STAGEMESH_DEPLOYMENT_PROFILE=proxy-https` with fail-closed startup requirements for loopback backend binding, private credential-file authentication, exact HTTPS origins and per-user trusted-proxy authorization.
- Keep forwarded peer headers explicitly untrusted; TLS, firewall and human authentication remain edge-proxy responsibilities.
- Add a packaged reverse-proxy contract, non-secret systemd environment example and optional `/etc/stagemesh/stagemesh.env` service settings file.
- Add `stagemesh-http-qualify.py` to exercise backend Host/Origin/token rejection separately from certificate-verified TLS 1.2/1.3, HSTS and browser-security-header edge checks.
- Pass a live local reference deployment using the real StageMesh process behind a temporary trusted TLS proxy; this is software deployment evidence, not venue-LAN qualification.
- Add six deployment regressions and packaging checks.

## Astra backlog checkpoint 32 — per-user control roles and durable authorization audit

- Add optional private per-user HTTP authorization policy with fixed observer, performer, operator, authority and admin roles.
- Restrict performer mutations to explicitly assigned player monitor/MIDI/notation routes and separate ordinary operator control from authority-transfer/fencing control.
- Preserve existing narrower admin, adapter-report, community-vote and machine replication authorization boundaries rather than widening them through human roles.
- Persist every role-controlled allow/deny decision before route execution in a separate fsynced SHA-256 hash-linked authorization audit without request bodies, credentials or raw URLs.
- Add admin-protected audit-chain verification and atomic per-request policy rotation.
- Add eleven authorization regressions; full Python suite passes at 481 tests and native CTest passes 2/2.

## Astra backlog checkpoint 31 — file-backed event-stream revocation

- Revalidate stream credentials before/after bounded event waits and before delivery.
- Close revoked streams without a second HTTP response and return stream capacity.
- Test rotation during batch fetch, malformed idle credentials and normal delivery.

## Astra backlog checkpoint 30 — HTTP credential-file rotation

- Add private, owner-checked, bounded JSON credential loading with distinct roles.
- Pin credentials within a request; load atomic replacements for subsequent requests.
- Force API authentication in file mode and remove environment-token fallback.
- Deny invalid replacements without retaining old secrets; leave audio runtime untouched.
- Test rotation, malformed updates, permissions, symlinks, role overlap and duplicate keys.

## Astra backlog checkpoint 29 — scoped monitoring credential

- Add an optional monitoring token restricted to three exact operational GET routes.
- Deny all mutations, unlisted reads and path extensions, including on loopback.
- Fail closed if monitor/control credentials overlap.
- Test the real HTTP guard rejects hardware activation before reading its body.

## Astra backlog checkpoint 28 — health and command identity boundaries

- Require API authentication for remote/proxy detailed health requests.
- Reject overlength and duplicate command IDs instead of silently aliasing them.
- Test local health compatibility, protected health and rejected-command state preservation.

## Astra backlog checkpoint 27 — proxy privilege separation

- Disable localhost admin and adapter-report exemptions when API-token mode is enabled.
- Require explicit HTTPS proxy origins; reject URL components in Host/Origin.
- Deny non-ASCII credentials safely and reject overlength proxy identities.
- Add regression coverage for privilege separation, origins, credentials and identity collisions.
- Remove raw request targets and interpolated diagnostics from access logs to protect invitation tokens and prevent log-line injection.

## Astra backlog checkpoint 26 — bounded request-rate admission

- Add per-direct-address and aggregate token buckets before route dispatch.
- Bound identity tracking at 1,024 entries without evicting depleted buckets.
- Return 429 with retry guidance and close unread throttled requests.
- Test refill, aggregate limits, identity capacity and forwarded-header non-bypass.

## Astra backlog checkpoint 25 — request receive deadlines

- Enforce a monotonic 15-second combined header/body budget in the CLI bridge.
- Apply remaining time before every socket read; restore response inactivity timeout.
- Keep SSE and backend execution outside the receive deadline.
- Test continuously trickled headers and bodies with real sockets.

## Astra backlog checkpoint 24 — separate SSE capacity

- Cap CLI event streams at eight, retaining worker capacity for other traffic.
- Reject excess streams with 503 and a five-second retry hint.
- Release stream slots on all exits and close ended streaming connections.
- Test saturated-stream/control coexistence and normal/error slot reclamation.

## Astra backlog checkpoint 23 — bounded HTTP workers

- Limit CLI bridge worker connections to 32 before creating handler threads.
- Return capacity on normal completion, handler failure and thread-start failure.
- Apply ten-second socket inactivity timeouts and handle stalled SSE writes.
- Add capacity and stalled-header regressions; keep total deadlines and SSE budgets open.

## Astra backlog checkpoint 22 — HTTP request framing

- Reject ambiguous body framing and duplicate/missing Host before route dispatch.
- Close JSON error responses so unread bodies cannot become subsequent requests.
- Reject unsupported chunked/Expect traffic and nonempty GET bodies explicitly.
- Reject truncated JSON before mutation; preserve valid GET keep-alive pipelines.
- Add six raw-socket regressions; retain the broader LAN security review as open.

## Sol backlog checkpoint 21 — served UI and keyboard acceptance

- Add a keyboard skip path to the primary stage controls and a high-visibility focus ring across links, controls, summaries and programmatic focus targets.
- Announce launcher state and keyboard-command failures through a polite status region instead of silently discarding transport errors.
- Add static accessibility contracts for unique IDs, explicit non-submitting buttons, live operator feedback and durable keyboard affordances.
- Exercise the real loopback HTTP handler for the page, stylesheet, JavaScript and read-only state API, including content types and browser hardening headers.
- Keep rendered browser workflow and visual review open: the managed browser rejected loopback navigation before page content loaded.

## Sol backlog checkpoint 20 — authorized fenced-node recovery

- Add authenticated, request-bound witness recovery authorization tied to the exact durable transfer transaction and current target lease.
- Require quorum approval of cluster, source/target nodes, epochs, transaction, recovery ID and fence SHA-256 identity.
- Persist and sync a recovery receipt before removing the acquisition fence; re-check the opened file's inode and digest immediately before unlink.
- Leave quorum failures, malformed evidence, path swaps and durability failures fenced.
- Force runtime recovery to fence physical outputs and remain standby with no cached lease or automatic promotion.
- Add witness server, runtime API, OpenAPI and public schema contracts plus unit and loopback regressions.

## Sol backlog checkpoint 19 — end-to-end polyphonic streaming banks

- Migrate streaming-bank triggers from the shared arrangement queue to independent native voice slots.
- Prebuffer up to four 256-frame blocks before activation and continue decoding on one service thread per voice.
- Fence start, feed, stop and reclamation by exact slot generation; expose native per-slot generation/active status.
- Bound feed backpressure to 250 ms per block, record retries/failures and release failed prebuffer reservations.
- Cancel and join all feeder threads during runtime shutdown before issuing native stop-all.
- Add exact-generation stop API and service-thread lifecycle, reclamation, cancellation and timeout regressions.

## Sol backlog checkpoint 18 — native polyphonic streaming foundation

- Add a fixed-capacity 16-voice streaming engine with one bounded SPSC block feed and independent cursor, gain, loop and terminal state per voice.
- Fence every block by voice generation and sequence; expose stale blocks, discontinuities, starvation, completion, overflow and active-mask evidence.
- Mix streaming voices into native output zero without disk access, decoding, allocation, locks or I/O in the audio callback.
- Add bounded native start/block/stop/status protocol commands and Python client methods for 256-frame stereo feeds.
- Project native voice status through the existing streaming-bank status surface and add a public JSON schema.
- Retain the shared bank producer until service-thread per-voice feeders and lifecycle reclamation are complete.

## Sol backlog checkpoint 17 — operator-confirmed overload preparation

- Add an authenticated overload preparation workflow that recomputes the current deterministic plan under the mutation lock.
- Require exact agreement with the operator-reviewed action and ordered effect IDs so stale reviews fail closed.
- Verify every selected effect is optional, uses latency-preserving bypass and declares identical active/bypass latency.
- Prepare the atomic effect/delay generation without activating it; retain a separate Show-Time activation step and disarmed physical outputs.
- Add HTTP, OpenAPI and public schema contracts plus success, stale-review, latency-mismatch and authority-denial regressions.

## Sol backlog checkpoint 16 — live atomic effect/delay integration

- Wrap the real native output callback with a split transaction guard that pins one generation before graph/effect processing and releases it after matching delay compensation.
- Preserve the established effect-before-limiter processing order while preventing mid-block bank recycling.
- Route legacy delay preparation through the combined transaction and expose transaction connection, change and rollback evidence.
- Add native `FXPDC_PREPARE` and `FXPDC_ROLLBACK` commands plus authenticated runtime prepare/activate/rollback actions.
- Require every effect mutation to carry optional and latency-preserving classifications; keep overload plans non-applying and physical outputs disarmed.
- Extend native protocol, runtime safety, OpenAPI and schema regression coverage.

## Sol backlog checkpoint 15 — atomic effect/delay transaction foundation

- Add a fixed-capacity native transaction that publishes effect bypass decisions and matching output-delay compensation under one generation.
- Pin active readers so control-thread preparation cannot overwrite a delay bank still used by an audio callback.
- Capture prior bypass state and prepare deterministic generation-based rollback without allocating or locking in the process path.
- Reject stale generations, duplicate or unavailable effect targets, excess capacity and an occupied preparation slot.
- Prove pre-boundary continuity, boundary commit, matching delay selection and rollback in native tests; engine protocol/render integration remains explicit backlog work.

## Sol backlog checkpoint 14 — live delay alignment and safe overload planning

- Wire the generation-swapped native delay graph after every live output effect chain, bound by output slot, with processed-frame and graph-connection evidence.
- Constrain runtime delay preparation to four contiguous live output slots while preserving deterministic latency planning.
- Add deterministic overload shedding plans that only select effects explicitly classified as optional and latency-preserving; essential and unsafe effects remain blocked.
- Keep plans advisory and output-disarmed until bypass and delay compensation can be applied as one atomic, reversible transition.
- Add authenticated HTTP, OpenAPI and JSON-schema contracts plus native, runtime and safety regressions.

## Sol backlog checkpoint 13 — plugin-host lifecycle

- Give every isolated effect adapter a private, service-owned scratch directory with exact parent process identity and an opaque lifecycle identifier.
- Immediately reap adapters after timeout, malformed output or handshake mismatch; remove scratch on every normal/error close and retain bypass.
- Route stderr to a non-blocking sink so an unread diagnostic pipe cannot stall the protocol.
- Add bounded host lifecycle audit, shared scratch admission threshold, aggregate temporary-resource schema 3, proven-dead cleanup and API/schema contracts.

## Sol backlog checkpoint 12 — render/import staging recovery

- Wrap content-addressed media imports and offline-render publication in owner-described staging resources.
- Remove ownership evidence on successful atomic publication and clean ordinary failures without residue.
- Upgrade DAW temporary-resource status to aggregate schema 2 with media-snapshot, import-staging and render-staging counts and opaque path-free resource IDs.
- Extend acknowledged cleanup to exact dead-owner staging evidence while retaining live, unowned and malformed resources.

## Sol backlog checkpoint 11 — DAW temporary-resource observability

- Add bounded, path-free cross-process media-snapshot status with configured quota, reserved/observed bytes, owner liveness classification, age and operation purpose.
- Add acknowledged cleanup that reclaims only resources whose exact boot/process-start owner is proven dead; live and unverifiable resources remain untouched.
- Integrate temporary-resource pressure into the coherent DAW Production projection and browser controls.
- Add HTTP, OpenAPI and public JSON-schema contracts plus lifecycle, privacy and conservative-cleanup regressions.

## Sol backlog checkpoint 10 — explicit audio identity replacement

- Detect a persistent audio identity change even when ALSA reuses the same native endpoint ID, emit a bounded `identity-changed` observation, and stop affected active input/output streams.
- Add an acknowledged identity-replacement store operation, runtime workflow, HTTP API, OpenAPI contract and operator UI action.
- Require all streams in the affected direction to be stopped; replacement may restore selection but never activates streams or arms physical output.
- Persist explicit topology trust against the exact unique persistent identity without weakening ordinary topology auto-reconnect policy.

## Driver-configured audio parameters and conversion policy

- Query ALSA's current hardware parameters after configuration and report requested and configured rate, period, channels and format separately.
- Fail before stream start when configured parameters cannot be queried or exceed bounded engine support.
- Require explicit rate, integer-format and channel conversion choices and carry bounded native conversion flags into activation.
- Preserve the 192 kHz FLOAT_LE stereo graph contract and state that upscaling cannot restore missing bandwidth.

## Audio hotplug lifecycle serialization

- Serialize audio discovery, selection, activation, recovery, deactivation and authority fencing through one reentrant control boundary.
- Stop active playback/capture slots when their selected endpoint disappears before selecting any serial-matched replacement.
- Add stopped slot evidence to bounded hotplug observations and deterministic concurrency/disconnect regressions.

## Audio identity reuse fix

- Preserve the initial native-ID identity across scans and restarts.
- Reject mismatched or ambiguous serial identities even at the original endpoint ID.
- Reject malformed ALSA identity addresses and avoid repeated unchanged identity writes.


## Audio identity and hotplug increment

- Derive privacy-preserving Linux audio endpoint identity from resolvable ALSA/sysfs USB evidence without storing raw serials.
- Permit selection-layer reconnect only for one exact serial-backed identity; topology and alias identities require explicit recovery.
- Continuously rescan native audio endpoints and expose bounded generation-filtered connect/disconnect observations.
- Preserve the physical safety boundary: scanning and identity matches never activate streams or arm outputs.

## HTTP API boundary hardening increment

- Validate request Host headers against loopback and explicit allowed hosts to contain DNS rebinding.
- Reject foreign/opaque browser origins and require JSON content types for API mutations.
- Require a dedicated header token for every remote API read or mutation while preserving narrower subsystem credentials.
- Add restrictive browser response headers, server-level failure tests and deployment/review documentation.

## Plugin adapter compatibility increment

- Require external plugin manifests to declare the current OS and architecture, adapter protocol 1, and a pinned executable SHA-256 digest.
- Verify the adapter digest before process launch and retain the existing fail-closed identity/format/capability handshake.
- Apply the same compatibility validation during catalog scans; incompatible entries are quarantined instead of advertised as usable.
- Publish the manifest schema and document the remaining verification-to-launch race and unperformed real-plugin/cross-platform qualification.

## Explicit audio recovery increment

- Add separately acknowledged output/input recovery endpoints and UI controls.
- Rerun constraint preflight and rescan after physical activation; stop a stream whose endpoint disappears during activation.
- Report configured native sample rate, period frames and channel count in stream status.
- Keep recovery manual and preserve all existing physical route acknowledgments.

## Linux packaging preparation increment

- Add systemd sysusers/tmpfiles definitions and tighten the service sandbox without hiding required hardware namespaces.
- Add a safe uninstall path that preserves state by default and requires explicit `--purge-data` for removal.
- Extend staged install/reinstall/uninstall coverage; keep service activation manual.
- Add setup/removal guidance, a disarmed demo session, dependency inventory, known issues and an explicit license blocker.

## MIDI identity and driver matching increment

- Persist privacy-preserving MIDI hardware identities; automatically rebind only exact serial-backed matches.
- Keep topology-only/volatile reconnects detached until an explicit user rebind, while preserving desired ownership.
- Report native MIDI attachment state through scans so rescans retain live handles accurately.
- Separate OS class-driver evidence, exact curated package matches and unverified search links; prohibit automatic install.

## Audio activation preflight increment

- Require a successful exact FLOAT_LE constraint query immediately before physical ALSA playback or capture activation.
- Block busy, unavailable, unsupported, and plugin-only endpoints without selecting or starting them; preserve virtual null output for software workflows.
- Return the activation preflight receipt and retain its latest result in output status.
- Do not apply automatic format/rate fallbacks.

## DAW shared snapshot recovery increment

- Move operation-owned media copies into a configurable shared store with a file-locked cross-process quota.
- Persist boot ID, PID and process-start identity; reclaim only snapshots whose exact owner is proven dead.
- Preserve malformed or unverifiable owners and charge their observed bytes to quota.
- Add strict maximum/reserve byte configuration and focused lifecycle/quota tests.

## Witness response authentication increment

- Sign acquisition/transfer replies using the existing secret and a domain-separated HMAC.
- Bind replies to the exact request including nonce and operation; reject unsigned, altered or replayed replies before counting grants.
- Exercise the production witness HTTP handler and retain fencing/expiry regressions.
- Document server-first upgrade order and shared-secret limits in `docs/witness-response-authentication.md`.
- Defer physical hardware qualification; authorized fenced-node recovery remains unfinished.

## Audio constraint preflight increment

- Add opt-in Linux hardware PCM preflight to Compatibility and POST `/api/v1/hardware/audio-preflight`.
- Test a combined format/channel/rate/period constraint set without applying it or starting audio.
- Distinguish unsupported constraints from busy, permission-denied, missing-device and unavailable-runtime outcomes.
- Validate addresses and numeric request fields before accessing ALSA; close handles on failed queries.
- Document the separation between preflight, actual negotiation and activation in `docs/audio-preflight.md`.

## PnP preparation increment (after Core 5.10.5)

- Add read-only USB inventory adapters for Linux sysfs, Windows CIM and macOS system_profiler, with explicit unknown/unavailable states.
- Expose hardware diagnostics through the Compatibility panel, GET `/api/v1/hardware/diagnostics`, and the installed hardware-doctor CLI.
- Add hardware-ID online lookup links to official OS guidance and Microsoft Update Catalog; omit serial-number fields from reports/searches.
- Add fixture and HTTP coverage, public diagnostic schema, and an explicit remaining PnP roadmap in `docs/hardware-pnp.md`.
- No native ABI change, automatic driver installation, hardware qualification, or full Windows/macOS platform support is claimed.

## Core 5.10.5 - full software gate restored

- Restore the pinned CMake/CTest toolchain and complete a fresh qualification-enabled Release build across the accumulated handoff fixes.
- Require `realtimeQualification=1` in release-mode native protocol tests while retaining ordinary-build support outside the release gate.
- Pass both native CTest targets, all 316 Python tests without skips, parsing of 104 public schemas, frontend syntax checks and the deterministic automation budget.
- Pass the separate native Debug ASan/UBSan gate with leak detection disabled. Record tool versions and limits in `docs/core-5.10.5-validation.md`.
- Native ABI 1.67 and handshake 5.0 remain unchanged. No deployment, installer or hardware qualification is claimed.

## Core 5.10.4 - witness response validation

- Reject duplicate witness URLs (including trailing-slash variants) instead of counting one endpoint repeatedly or silently shrinking the quorum configuration.
- Require actual JSON booleans and positive integer fencing values; validate cluster, holder and transfer transaction identity before counting a grant.
- Contain malformed responses as denied witness results rather than letting parsing exceptions terminate the renewal loop.
- Recheck lease expiry after network collection, including transfer acknowledgements. Native ABI 1.67 and handshake 5.0 remain unchanged.

## Core 5.10.3 - persistent handoff acquisition fence

- Persist a local fence marker and sync both file and parent directory before contacting witnesses for transfer; a persistence failure prevents transfer.
- Honor marker presence, unreadable paths and incomplete contents at startup, before native bindings and background loops begin.
- Start fenced nodes as standby even without witness URLs; reject manual/automatic promotion and ordinary force overrides while fenced.
- Add restart, disk-sync failure, corrupted-marker and normal-startup regression coverage. Explicit recovery remains pending; native ABI 1.67 and handshake 5.0 are unchanged.

## Core 5.10.2 - post-transfer authority reacquisition fence

- Suspend witness acquisition for the client lifetime before any transfer request, including partial and exceptional outcomes.
- Serialize the background witness tick and planned authority release with the runtime mutation lock, preventing stale renewal results from racing release demotion.
- Expose `acquisitionSuspended` in witness status and add post-transfer/auto-failover regression coverage.
- Native ABI 1.67 and engine handshake 5.0 are unchanged. This is a process-lifetime safeguard, not durable restart fencing.

## Core 5.10.1 - qualification evidence hardening

- Count actual plugin serialization contention through failed nonblocking acquisition, with counter updates protected by the acquired lock.
- Allow native protocol tests to validate ordinary and instrumented builds; require handshake/status mode agreement.
- Reject unsupported qualification platforms at CMake configuration time and test nested scope restoration plus thread-local isolation.
- Native ABI 1.67 and engine handshake 5.0 remain unchanged. Hardware qualification is still outstanding.

## Core 5.10 - real-time qualification instrumentation

- Added a qualification-only thread scope around native render callbacks that counts C++ allocation requests, requested bytes and pthread mutex acquisition attempts with atomic-only reporting.
- Added a CMake `STAGEMESH_RT_QUALIFICATION` switch; ordinary builds default it off while the software release gate explicitly compiles it on and tests both detectors.
- Extended isolated plugin-host audits with qualification mode, serialization lock attempts/contention/wait, and bounded request/response payload byte totals.
- Exposed qualification state and counters through native stdio, backend/API projections and schemas without arming hardware or claiming real hardware qualification.
- Advanced engine handshake to 5.0 and public C ABI to 1.67; the append-only `org.upp.core.realtime-audit/1` status now carries qualification counters.

## Developer alpha - atomic planned-handoff witness transfer

- Added authenticated, transaction-bound witness lease transfer from the exact live source holder/epoch directly to the offer's named standby at the exact next epoch.
- Removed the unowned-lease race: there is deliberately no generic release operation, and exact retries are idempotent without extending the target lease.
- Serialize witness renewal and transfer operations; clear cached source authority and demote/fence the old primary before any irreversible transfer request.
- Report quorum success as `authority-released` and partial transfer as `release-indeterminate`; both states leave the old primary demoted and physical outputs disarmed.
- Added `/api/v1/handoff/planned/release-authority`, `/api/v1/lease/transfer`, OpenAPI coverage, `witness-transfer-request.schema.json`, and quorum/fail-closed regressions. Native ABI 1.66 and handshake 4.9 are unchanged.

## Developer alpha - authenticated handoff readiness delivery

- Deliver target readiness from standby to primary over the configured peer transport after execution-backed pre-roll acknowledgement.
- Bind the HMAC-SHA-256 receipt to transaction, nodes, epochs, Show-Time boundary, offer issue time and the explicit program-readiness result.
- Reject malformed booleans, tampering, wrong-primary delivery, stale-offer receipts and fencing mismatches; accept exact re-delivery idempotently and reject conflicting readiness.
- Publish the peer route in OpenAPI, add transport delivery telemetry and add `planned-handoff-ready-receipt.schema.json`.
- Physical outputs remain disarmed; coordinated old-primary witness lease release remains a separate fail-closed backlog item. Native ABI 1.66 and handshake 4.9 are unchanged.

## Developer alpha - isolated plugin-host audit hardening

- Serialized host pipe requests and added lifecycle, request, block, sample, timeout, disconnect, host-error, invalid-response and maximum-duration telemetry.
- Kill and reap timed-out processes immediately; reject malformed, wrong-sized or non-finite plugin output and fail the host to bypass.
- Project live host instances through the authenticated real-time audit endpoint using lifetime-safe weak registration.
- Extended plugin-host and aggregate audit schemas plus timeout and malformed-response regression coverage. Native ABI 1.66 and handshake 4.9 are unchanged.
- Execute declared external-format adapters directly without a shell only after absolute-path, regular-file and executable checks; retain watchdog timeout and fail-to-bypass semantics.
- Require plugin adapter protocol 1 activation identity, format, process capability and bounded latency; correlate every response to its request ID and reject stale or mismatched replies.

## Core 5.9 - Lighting ingress audit

- Added fixed atomic lighting handoff counters for accepted events, bounded-queue rejection, drain calls, drained events and maximum drain duration.
- Extended native, backend, HTTP and schema projections without enabling Art-Net or physical lighting output.
- Advanced the engine handshake to 4.9 and public C ABI to 1.66 with lighting status appended to `org.upp.core.ingress-audit/1`.

## Core 5.8 - Capture ingress audit and containment

- Added fixed atomic per-input capture counters for callbacks, frames, recording blocks, queue rejection, non-finite samples and maximum callback duration.
- Contain NaN and infinity as silence before captured audio reaches monitor fan-out or recording queues.
- Extended native, backend, HTTP and schema projections for four capture slots without activating hardware.
- Advanced the engine handshake to 4.8 and public C ABI to 1.65 with capture status appended to `org.upp.core.ingress-audit/1`.
- Made parsing every public JSON schema a permanent release-gate requirement.

## Core 5.7 - MIDI ingress audit

- Added fixed atomic MIDI ingress counters for polls, bytes, accepted messages, injection, queue drops and maximum poll duration; the input path performs no reporting I/O.
- Exposed authenticated native, backend and HTTP projection status without arming physical outputs.
- Advanced the engine handshake to 4.7 and public C ABI to 1.64 with `org.upp.core.ingress-audit/1`; extended the real-time audit schema and current ABI smoke target.

## Developer alpha - prepared automation lanes

- Prepare immutable volume-automation curves once per playback or offline-render operation, removing repeated point conversion and sorting from every audio block.
- Enter each prepared block through a binary frame-index search instead of rescanning lane history, while preserving duplicate-frame interpolation semantics.
- Add a deterministic automation work-budget and equivalence gate to the release check, with machine timing reported for observation only.
- Publish the machine-readable automation performance report schema and prevent playback curve caches from being reused with another render plan.

## Developer alpha - block automation evaluation

- Prepare volume points once per block in playback and WAV export, instead of
  rebuilding and sorting the full lane for every sample.
- Preserve scalar interpolation arithmetic and block-boundary results.
- Add exact-value equivalence and deterministic point-read budget tests.

## Developer alpha - precise automation selection

- Preserve exact canonical frames and full gain precision on select/save.
- Clear point selection when switching tracks, including reused point IDs.
- Add an explicit new-point action and reject blank numeric fields.
- Add regression coverage for precision, track switching, and new-point state.

## Developer alpha - automation request recovery

- Surface rejected automation edits and restore controls after failure.
- Block overlapping automation mutations and use the current render callback.
- Cover asynchronous failure, retry readiness, and duplicate submission in the DOM harness.

## Developer alpha - pointer selection lifecycle

- Avoid timeline rerenders during pointer capture on unselected clips.
- Preserve modifier selection through complete pointer-down/up/click sequences.
- Ignore non-primary-button drag starts and reset stale click suppression.
- Add event-sequence regression coverage; real-browser qualification remains open.

## Developer alpha - workflow and sanitizer gates

- Added an HTTP DAW workflow spanning session save, markers, volume automation,
  clip movement, render planning, WAV export, and native queue start/stop.
- Added opt-in CMake ASan/UBSan instrumentation plus a clean-tree sanitizer gate;
  leak detection is separately enabled for untraced qualification hosts.

## Developer alpha - volume automation lanes

- Added bounded normalized volume points with stable IDs, unique positions,
  finite 0–2 gain values, and deterministic linear interpolation.
- Added revision-safe upsert/delete operations, a visual point editor with pointer
  movement, OpenAPI/schema documentation, and renderer/playback/DOM tests.

## Developer alpha - portable timeline markers

- Added normalized section/cue/note markers with revision-safe, undoable add,
  snapped move, and confirmed delete operations.
- Added a visual marker rail, locate behavior, API/schema/OpenAPI documentation,
  and backend plus DOM workflow tests.

## Developer alpha - atomic multi-clip movement

- Added persistent modifier-key multi-selection with group drag previews and
  keyboard movement.
- Added bounded `moveMany` transactions with deterministic anchor snapping,
  complete preflight validation, one revision increment, and one undo snapshot.

## Developer alpha - graphical clip edge trimming

- Added revision-safe, snap-aware trim resizing with one undo entry per gesture.
- Added live pointer resize previews, visible edge handles, bracket-key trimming,
  source/fade offset preservation, and extension/collapse rejection tests.

## Developer alpha - graphical arrangement movement

- Added undo-safe, revision-checked clip movement with deterministic snapping and
  compatible cross-track transfer.
- Added pointer drag previews, beat-grid selection, keyboard nudging, accessible
  clip labels, and DOM/backend regression coverage.

## Developer alpha - DAW control surface contract

- Extracted stateful, accessible production transport/capture controls from the
  main browser bundle and repaired the shared API boundary used by page modules.
- Added coherent `GET /api/v1/daw/production` status and an OpenAPI 3.1 contract.
- Added strict frame validation, abort confirmation, DOM/API coverage, and
  release-gate syntax checks for every frontend script.

## Developer-alpha nondestructive split fades checkpoint

- Split clips retain the original fade span and their offset within it, instead
  of creating new fades at the split. Repeated splits preserve this relationship.
- Validate fade spans; explicit fade edits reset the envelope to the edited clip.
- Added byte-identical export comparisons after splits inside fade-in, sustain
  and fade-out, including save/reopen checks.

## Developer-alpha recording collision checkpoint

- Publish recordings without replacing existing filenames. Collisions retain the
  pending take and return an actionable error.
- Finish accepts an optional WAV basename for retry; the DAW exposes a matching field.
- Report partialCleanupPending if publication succeeds but partial unlink fails.
- Added capture collision/retry coverage and updated publication failure tests.

## Developer-alpha recording finalization retry checkpoint

- Sync completed WAV bytes before publication and retain sealed partial takes when
  file sync or rename fails, allowing finish to retry without re-recording.
- Prevent a new spool from replacing a take awaiting finalization; header-close
  failures cannot be retried as successful recordings.
- Capture reports finalization-pending errors through the existing JSON error path.
- Added fault-injection tests for file sync, rename and header-close failures.

## Developer-alpha fade curve checkpoint

- Apply linear and equal-power fade selections through one envelope helper shared
  by arrangement playback and offline export. Equal-power uses a sine envelope.
- Reject unknown fade curves during session normalization.
- Added curve midpoint, sustain, offset and unsupported-curve tests.
- Audible behavior changes for equal-power sessions previously rendered linearly.

## Developer-alpha clip fade range checkpoint

- Preserve original clip offset and length in render-plan regions so partial
  playback/export ranges do not restart fades or move fade-outs earlier.
- Updated arrangement and offline mixing to use original clip-relative fade timing.
- Added sample/PCM comparisons for partial ranges inside fade-in, sustain and
  fade-out, including a nonzero clip start and source offset.
- Stateful effect/limiter range equivalence and fade-curve semantics remain open.

## Developer-alpha resampling continuity checkpoint

- Removed rounded block-local sample offsets from file conversion. Source positions
  now derive from integer canonical-frame coordinates with an explicit source origin.
- Added exact stereo sample comparisons between continuous and unevenly partitioned
  reads at 32, 44.1, 48, 88.2, 96 and 192 kHz, including reads beyond source end.
- Linear interpolation remains unchanged; anti-alias filtering and audio-quality
  qualification remain open.

## Developer-alpha snapshot budget checkpoint

- Added a shared 2 GiB in-process snapshot budget and conservative free-space
  checks with a 64 MiB reserve before copying audio.
- Reject growth beyond reserved source sizes; release reservations on cleanup
  and preparation failure. Repeated source/hash pairs share one copy.
- Fixed repeated region references changing snapshot lookup keys.
- Added budget exhaustion/reuse, low-disk and failed-hash tests.

## Developer-alpha media snapshot checkpoint

- Playback and export now copy plan audio sources into operation-owned temporary
  storage and verify the copied bytes against declared hashes before use.
- Reads use those copies throughout the operation; export receipts include hashes
  calculated for legacy unhashed sources too. Copies are removed on completion,
  startup failure or cancellation after the playback worker exits.
- Added source-replacement tests proving stable export output and playback samples.
- Whole-file snapshots add startup time and temporary disk usage; hardware and
  visual browser qualification remain open.

## Developer-alpha playback/export integrity checkpoint

- Verify declared audio content hashes before arrangement start or offline export,
  using bounded reads and checking each source/hash pair once per plan.
- Changed media fails before stopping playback or replacing an existing export.
- Extended native-backed restart coverage for changed-media playback/export rejection.
- Visual browser validation was blocked by local-URL access in the available browser.

## Developer-alpha recovery HTTP checkpoint

- Added a live local HTTP acceptance test for discovery, recovery, preserved source
  bytes, WAV output, invalid paths and serving the recovery panel script.
- Fixed missing partial files closing the HTTP connection: recovery now returns
  a JSON validation error prompting a list refresh.
- Visual browser and hardware qualification remain open.

## Developer-alpha recovery panel checkpoint

- Added interrupted-recording discovery and a recover-copy panel in the DAW.
- Candidate scans exclude symlinks, stop at 1,000 directory entries and report
  truncation; pending capture blocks discovery and recovery.
- Panel displays completion/errors and prevents duplicate in-flight requests.
- Added candidate-list and JavaScript DOM-harness workflow tests. Full visual
  browser qualification remains open.

## Developer-alpha partial recording recovery checkpoint

- Added Linux recovery for fixed-header stereo 32-bit PCM / 192 kHz partial spools.
  Copies complete on-disk frames into a separate WAV without replacing the source.
- Recovery reports trailing-byte truncation and unverified continuity; refuses
  unsupported headers, symlinks, non-regular files and pending runtime capture.
- Exposed recover through the existing capture API without requiring a native engine.
- Added stale-header, source-preservation, path and pending-capture tests.

## Developer-alpha native recording fence checkpoint

- Added an atomic recording writer gate. Disarm closes admission and waits on the
  control thread for an admitted submit to publish before returning.
- Submit never waits for the gate; arm waits for disarm before resetting queue
  indices and advancing the recording generation.
- Added 100 concurrent disarm/rearm test rounds checking stable submission counts,
  drained tail contents and old-generation rejection.
- Physical input shutdown latency and partial-file recovery remain unqualified.

## Developer-alpha capture tail checkpoint

- Finish now disarms and drains available queued/in-flight blocks before finalizing;
  abort continues to cancel immediately. Empty-queue observation is reported as
  queueDrained. Drain work is bounded to 65 blocks after finish is requested.
- Added deterministic queued-tail coverage and updated stalled-finish recovery tests.
- Native callback/disarm fencing and partial-file recovery remain open.

## Developer-alpha capture failure checkpoint

- Capture worker exceptions now produce a failed state, preserve error evidence,
  request disarming, and prevent finalization as a successful take.
- Only native empty-queue responses are retryable; other input errors terminate
  capture. Disarm failures are reported separately without claiming disarm success.
- Validate finite samples, channel lengths and PCM byte/frame consistency.
- Added injected disk, native-input and malformed-data regression coverage.

## Developer-alpha capture shutdown checkpoint

- Serialize capture start/finish/abort and require pending takes, including
  completed punch takes, to be finalized or aborted before starting another.
- Disarm capture before waiting for the worker. On timeout, retain worker and spool,
  report the failure, and block take publication/deletion until the worker exits.
- Discard blocks returned after cancellation; continue native runtime cleanup
  before reporting capture shutdown errors.
- Added stalled finish/abort, completed punch preservation and cleanup tests.

## Developer-alpha producer shutdown checkpoint

- Serialize arrangement start/stop operations and retain stalled workers on join
  timeout. Restart remains blocked until the old worker exits.
- Recheck cancellation after media reads and native status calls, and stop native
  playback when a cancelled worker exits.
- Runtime close completes native cleanup before reporting a producer stop error.
- Added stalled-reader recovery and runtime-cleanup regression tests.

## Developer-alpha loop production checkpoint

- Routed runtime loop control through the arrangement producer so it supplies
  repeated blocks instead of merely setting the native loop range.
- Loop control restarts at the requested beginning. Loop lengths must be multiples
  of 256 canonical frames; invalid ranges are rejected before stopping playback.
- Added native-backed acceptance coverage for repeated production, invalid-range
  preservation and stopping/joining the producer. Audible loop timing remains unqualified.

## Developer-alpha managed import checkpoint

- Fixed the native protocol test's automation wait to observe the requested
  parameter, rather than an unrelated parameter registered by an earlier test step.
- Reject corrupted existing managed objects during deduplicated import.
- Verify copied bytes before publication; reject source changes during copying
  and remove incomplete temporary objects.
- Extended runtime acceptance through managed import, original-file removal,
  reopen, native arrangement queue submission and non-silent 32-bit PCM export
  at 192 kHz. This does not qualify physical playback or live recording.

## Developer-alpha session restart checkpoint

- Added runtime acceptance coverage for save, native MIDI Learn, close/reopen,
  restored sampler preload, render planning and native sample submission.
- Added changed-media restart coverage: retain the mapping without promoting an
  invalid sample into native execution. Physical outputs remain disarmed.
- Browser import, audible playback, looping and recording qualification remain open.

## Developer-alpha packaging checkpoint

- Fixed installed qualification-helper backend discovery.
- Added custom build-directory selection and fail-before-write checks for unsupported prefixes, relative staging paths and missing engines.
- Added staged installation/reinstallation checks for helper execution, frontend presence, loopback service configuration and user-data preservation. No services are enabled by installation.

## Core 5.6.2 — Delay Graph Control Contract Hardening

- Mark delay-graph status as a control-thread prototype with no connected audio graph or verified live alignment; normalize native numeric and boolean status fields for JSON clients.
- Serialize HTTP-side control and enforce primary/witness authority, reject pending-plan overwrite, enforce native 16-path capacity, and reject ambiguous IDs or non-integer latencies.
- Derive activation time from platform transport rather than a client-supplied future timestamp. This is still explicit control-thread activation, not scheduled callback activation.
- Concurrent native bank reclamation, block-wide snapshots and actual processing-path integration remain unfinished. ABI and engine handshake are unchanged.

## Core 5.6.1 — Preserve Essential Effects Under Overload

- Removed automatic whole-chain bypass from the output callback. Effects have no optional-work classification or latency-preserving transition contract, so they must not be silently removed under load.
- Kept deadline, non-finite sample and queue-pressure telemetry. Exposed advisory-only overload policy and disabled automatic effect shedding in runtime status.
- Added source-level integration regression guards. Selective shedding, hardware qualification and debug allocator/lock probes remain incomplete; ABI 1.63 and handshake 4.6 are unchanged.

## Core 5.6 — Real-Time Audit & Overload Shedding

- Added allocation-free per-output callback auditing for duration/deadline misses, consecutive misses, maximum duration, non-finite samples, input-ring pressure, optional-work shedding and recovery.
- Sanitized non-finite callback output to silence with explicit evidence instead of allowing invalid samples downstream.
- Added deterministic overload policy: optional effect processing sheds after three consecutive misses, escalates after ten and resumes after 128 on-time callbacks. Audio routing, transport, sampler and playback remain protected.
- Added native/Python/HTTP status surfaces. Engine handshake is 4.6 and public C ABI is 1.63 with `org.upp.core.realtime-audit/1`; added one schema. Auditing never arms output.

## Core 5.5 — Atomic Plugin Delay Graph Generations

- Added double-buffered native plugin delay graphs for up to 16 dry, send and parallel paths with 65,536 frames of bounded compensation.
- Latency/topology changes prepare completely in the inactive bank and publish atomically at an explicit Show-Time boundary; callbacks cannot observe partial alignment.
- Added stale-generation rejection plus active/prepared generation, maximum latency, swap and rejection telemetry.
- Added authenticated native/Python/HTTP controls. Engine handshake is 4.5 and public C ABI is 1.62 with `org.upp.audio.plugin-delay-graph/1`; added one schema. No operation arms output.

## Core 5.4 — Replaceable Streaming Sample Banks

- Added 16 replaceable banks of up to 64 long audio-file entries, removing the 65,536-frame native preload ceiling for performance clips.
- Reused the generation-fenced 256-frame arrangement producer and native playback queue; hashing, file access, decoding and conversion remain outside the audio callback.
- Bank replacement advances a generation and preserves stable clip-based mappings. Registration and every trigger verify media content identity, so missing or changed media fails closed until relink/replacement.
- Added a bounded 256-action replay window so retried triggers cannot restart or double-fire a long clip.
- Advanced public C ABI to 1.61 with `org.upp.audio.streaming-sample-bank/1`; added one schema. Physical output arming remains separate.

## Core 5.3 — Core-Authoritative Stage Launcher

- Added a responsive stage launcher projection over authoritative transport, native sampler preload, capture/dropout and native MIDI execution state.
- Added large low-error Play/Pause, Stop and eight bounded sample-pad controls with shared touch, keyboard and MIDI telemetry. Space, Escape and keys 1–8 cover the critical keyboard flow without precision gestures.
- Launcher actions carry bounded replay-safe action IDs. Repeated delivery returns current state without toggling transport or retriggering a sample.
- Sample pads expose only verified preloaded native assets and dispatch into the native sampler Show Event path. The browser does not own playback timing or sample voices.
- The launcher cannot arm a physical output. Capture arming remains outside this surface and continues to require explicit acknowledgement.
- Advanced the public C ABI to 1.60 with `org.upp.stage.launcher-projection/1`; added one schema. Native engine handshake remains 4.4 because the launcher is a replaceable client projection.

## Core 5.2.1 — Generation-Fenced Punch & Loop Capture

- Added bounded punch, pre-roll, latency-correction and multi-pass loop selection to the background native capture drainer while keeping file conversion and finalization outside the real-time callback.
- Every input callback block now carries the recording-arm generation. Re-arm clears queued residue, advances the generation and rejects blocks from an earlier take with explicit stale telemetry.
- Punch completion disarms physical input automatically. Starting still requires explicit physical-input acknowledgement, restart/demotion remains disarmed, and capture never arms physical output.
- Preserved native sequence-gap evidence and crash-safe atomic 32-bit WAV finalization. Loop selections split exactly at pass boundaries and are bounded to 128 passes.
- Declared the current positions as capture-adapter frames; non-192 kHz adapters must convert before claiming canonical Show-Time alignment.
- Advanced engine handshake to 4.4 and public C ABI to 1.59 with `org.upp.daw.punch-loop-capture/1`; added one schema.

## Core 5.2 — Disciplined Transport & MIDI Clock

- Added an authority-fenced transport discipline controller that accepts monotonic paired-clock and source Show-Time evidence with advancing sequences and the active authority epoch.
- Converted drift plus phase error into a bounded rate slew instead of seeking the timeline. Phase recovery is limited by an explicit correction ceiling/window; source loss enters holdover without an abrupt transport jump.
- Added a deterministic 24-PPQN MIDI Clock engine with fenced configure/start/stop/tempo/observe operations, bounded pulse emission into the existing MIDI scheduler and measured maximum input jitter.
- Tempo changes publish a new exact Show-Time pulse boundary without resetting transport position. MIDI Start, Clock and Stop remain scheduled messages and do not directly arm a MIDI device.
- Added authenticated native commands, Python client and primary-only HTTP controls/status for transport discipline and MIDI Clock.
- Advanced engine handshake to 4.3 and public C ABI to 1.58 with `org.upp.timing.transport-discipline/1` and `org.upp.midi.clock-24ppqn/1`; added two schemas.

## Core 5.1.2 — Verified DAW Sampler Preload

- Added a control-thread sampler preload registry that resolves DAW audio clips, verifies declared SHA-256 media identity, decodes supported PCM WAV input and resamples the selected slice into canonical stereo float32/192 kHz before native registration.
- Baked track gain, equal-power pan and clip fades into bounded sampler assets without putting file access, decoding or allocation in the audio callback.
- Fenced every published asset with session revision, source hash, source offset, length and playback mode. Changed generations receive distinct native resource IDs; stale generations cannot be selected by newly compiled mappings.
- Promoted sample trigger and loop mappings to native Core only after their referenced asset is registered. Missing, mismatched, non-audio and clips longer than 65,536 canonical frames remain on the existing arrangement bridge path.
- Added sampler preload status/control endpoints, automatic startup restoration for eligible persisted mappings, two focused preload tests and a native end-to-end persisted-mapping regression.
- Added `sampler-preload-status.schema.json`; engine handshake remains 4.2 and public C ABI remains 1.57.

## Core 5.1.1 — Native Polyphonic Sampler Foundation

- Added a fixed-capacity 64-voice native sampler with immutable external sample memory, allocation-free callback rendering, bounded SPSC commands and finite-value velocity clamping.
- Added deterministic oldest-voice stealing, choke groups, short click-resistant attack/release envelopes and equal-power loop crossfades.
- Routed sampler trigger/stop actions through authoritative typed Show Events and the CoreJournal; the sampler is source 22 in the primary canonical float32/192 kHz audio graph.
- Extended native MIDI mapping with stable sampler resource IDs and sample trigger, loop toggle and loop clear actions. Mapped gestures retain beat quantization and master-key correction before reaching the voice engine.
- Added authenticated bounded PCM staging for development adapters, Python client controls and complete sampler telemetry. Staging is capped at 65,536 canonical frames; larger/streamed banks remain an explicit provider task.
- Advanced engine handshake to 4.2 and public C ABI to 1.57 with `org.upp.audio.sampler-voice-engine/1`; added one schema. Physical outputs remain disarmed.

## Core 5.1 — Native MIDI Performance Path

- Moved eligible learned controller execution for transport and continuous automation into native Core. Captured MIDI is matched, scaled, quantized and converted to authoritative typed Show Events without Python resubmitting the mapped action.
- Added `MidiMappedActionDispatcher`, which gives repeated gestures unique replay-safe event IDs and preserves the `ShowExecutionLoop` as the sole timeline/dispatch owner.
- Added native mapping compilation/status commands and bridge migration logic. The bridge loads persisted mappings into Core, records/observes captured MIDI, and suppresses duplicate execution for mappings already accepted by the native engine.
- Kept sample, loop and key-synchronized instrument mappings on the existing bridge path until the allocation-free polyphonic sample voice engine exists; the arrangement playback queue is not mislabeled as that engine.
- Native MIDI mapping and dispatch remain incapable of arming physical outputs. Restart clears compiled native mappings, and standby attachment remains blocked by the existing authority fence.
- Advanced engine handshake to 4.1 and public C ABI to 1.56 with `org.upp.midi.native-performance/1`; added one schema.

## Core 5.0 — Fluid MIDI Learn & Master Musical Sync

- Added a portable, crash-safe MIDI mapping store and one-action Learn mode: choose a musical target, touch the next meaningful pad/knob/slider, and the source device, channel, message type and control number are captured automatically.
- Added approachable target presets for sample triggering, loop toggle/clear, transport, filter cutoff/resonance, oscillator pitch, track volume/pan, tempo and key-synchronized instrument notes. Relearning the same physical control replaces its old assignment instead of creating an ambiguous duplicate.
- Added immediate, trigger, gate and toggle behaviors; linear and logarithmic continuous scaling; and bounded pending/execution telemetry. Note-off and unrelated devices cannot accidentally complete Learn mode.
- Added master beat quantization from quarter through thirty-second notes against authoritative BPM and Show Time. When transport is stopped, actions remain immediate instead of becoming stranded behind a clock that is not moving.
- Added master-key/scale correction metadata for mapped note and sample/synth actions while preserving the player's original MIDI event and notation record.
- Added runtime/HTTP execution into transport, tempo and native automation seams; sampler and looper mappings bind a concrete selected DAW clip to generation-fenced native playback, including loop-clear state when switching back to ordinary arrangement playback. Mappings never arm physical outputs.
- Added a browser MIDI Learn panel with target descriptions, beat/key options, live waiting feedback, human-readable learned controls and one-click removal.
- Added a fixed-capacity native MIDI mapping router with deterministic beat-boundary calculation, key-note correction, source replacement and bounded action queues.
- Advanced engine handshake to 4.0 and public C ABI to 1.55 with MIDI Learn and master-musical-sync extensions; added two schemas.

## Core 4.9 — Capture Finalization, Delay Compensation & DAW Mix Surface

- Added authenticated native recording-queue drain commands that transfer bounded 256-frame float32 capture blocks, preserving sequence and show-frame evidence outside the real-time callback.
- Added a background capture drainer that converts canonical float32 input to 32-bit / 192 kHz WAV, records queue discontinuities, requires explicit physical-input acknowledgement and atomically finalizes or safely aborts a take.
- Added a bounded parallel-path plugin latency planner and fixed-memory native delay compensator. Paths are aligned to the slowest declared latency and plans fail closed beyond the 65,536-frame capacity.
- Added runtime and HTTP capture status/control plus a plugin-delay planning endpoint. Neither feature grants physical-output authority.
- Expanded the browser DAW with track gain, pan, mute and solo controls, timeline zoom, real WAV peak inspection, waveform rendering and explicit capture start/finish controls.
- Advanced engine handshake to 3.9 and public C ABI to 1.54 with capture-drain and plugin-delay-compensation extensions; added two schemas.

## Core 4.8 — Arrangement Producer & Capture Bridge

- Added authenticated transfer of bounded 256-frame interleaved float32 PCM blocks into the native generation-fenced playback queue, including strict hexadecimal payload sizing and non-finite rejection.
- Added a background arrangement producer that resolves real WAV media, source offsets, fades, gain, pan and volume automation outside the audio callback, maintains bounded queue read-ahead and starts only after prefill.
- Producer start performs a native seek and binds every submitted block to the resulting generation, preventing stale media from crossing relocation.
- Connected ALSA capture callbacks to four independent native recording tracks in bounded 256-frame chunks with monotonic sequence and frame positions. Full queues retain dropout evidence rather than blocking capture.
- Playback status now includes producer progress/errors; runtime shutdown stops and joins the producer before closing the engine.
- Advanced engine handshake to 3.8 and public C ABI to 1.53 with arrangement-producer and PCM-block-transfer extensions; added one schema.

## Core 4.7 — Native Arrangement Playback & Capture Queues

- Added a fixed-capacity native arrangement playback queue connected as source 23 in the primary output audio graph.
- Prefetched blocks are fenced by generation, exact playhead frame and frame count. Seek clears queued work and advances generation so stale media can never play after relocation.
- Added explicit start/stop/seek/loop controls, loop wrapping, silence-on-underrun, discontinuity rejection and bounded telemetry. Playback never arms the audio device.
- Added eight independent fixed-capacity native recording queues for callback-to-writer transfer with explicit per-track arming, queue overflow counts and sequence-gap evidence.
- Added authenticated stdio, Python client, HTTP and browser controls for arrangement playback status/control. Capture file I/O remains outside the audio callback.
- Advanced engine handshake to 3.7 and public C ABI to 1.52 with playback-queue and multitrack-capture extensions; added two schemas.

## Core 4.6 — Native Streaming DAW Kernel

- Added fixed-capacity native `DawStreamRenderer` with compile-time block memory and region capacity, provider-owned source reads, sink/effect callbacks, clip intersections, source offsets, fades, gain, equal-power pan, non-finite suppression and stateful limiting.
- Added atomic cancellation, block progress and explicit complete/cancelled/failed telemetry; the renderer owns no hardware authority.
- Reworked the operational WAV exporter into 1,024-frame streaming blocks with bounded memory, atomic temporary-file completion and support for arrangements up to the existing one-hour render-plan bound.
- Added playback prefetch planning with bounded lookahead, explicit silence-and-report missing-media behavior, and a contract prohibiting disk I/O in the audio callback.
- Added crash-safe 32-bit WAV recording spools requiring explicit physical-input acknowledgement, bounded dropout evidence, atomic finalization and recoverable partial files.
- Advanced engine handshake to 3.6 and public C ABI to 1.51 with stream-renderer, playback-prefetch and recording-spool extensions; added two schemas.

## Core 4.5 — DAW Production Services

- Added deterministic stereo WAV export at 192 kHz with 16/24/32-bit encoding, TPDF dither for reduced bit depths, equal-power pan, clip fades, volume automation, peak limiting and SHA-256 render receipts.
- Added content-addressed WAV ingest/deduplication and hash verification with import/media/export path confinement.
- Added tempo/time-signature maps and deterministic beat-to-canonical-frame conversion plus bounded markers, sends, output buses and automation points in portable sessions.
- Added prepared/finalized recording-take contracts with pre-roll, punch boundaries and bounded dropout evidence. Preparing a take never arms physical input; capture remains an external hardware adapter responsibility.
- Added isolated plugin-manifest discovery and persistent crash quarantine. Proprietary plugin binaries remain external adapters and are not silently loaded into Core.
- Added bounded autosave recovery, deterministic render seeds, NaN suppression, limiter protection, disk-space preflight and a 30-second memory bound for the dependency-free reference renderer.
- Added production controls for render, autosave, beat location, take preparation and plugin scans.
- Advanced engine handshake to 3.5 and public C ABI to 1.50 with renderer, recording, tempo-map, media-library, plugin-catalog and recovery extensions; added four schemas.

## Core 4.4 — DAW Media, Waveforms & Edit History

- Added bounded local WAV inspection for PCM 8/16/24/32 sources with SHA-256 identity, source/canonical frame accounting and up to 4,096 min/max waveform buckets per channel.
- Media paths are confined to the configured data media directory, source files remain read-only, and inspection never activates playback.
- Added non-destructive clip trim, playhead split and linear/equal-power fade metadata with validation against clip duration.
- Added persistent bounded 100-step undo/redo history. Restored states receive new monotonically advancing revisions rather than rewinding concurrency identity.
- Added media-inspection and edit APIs plus selectable clips and trim/split/fade/undo/redo controls in the arrangement UI.
- Advanced engine handshake to 3.4 and public C ABI to 1.49 with DAW media and edit-history extensions; added two schemas.

## Core 4.3 — Portable DAW Arrangement

- Added a persistent provider-neutral DAW session with 128 bounded tracks and 4,096 clips across audio, MIDI, auxiliary and master track kinds.
- Added source-referential non-destructive clips, stable frame placement, source offsets, gain, pan, mute and deterministic solo resolution in the canonical float32/192 kHz domain.
- Added bounded one-hour offline render plans that resolve audible clip intersections without loading media or arming playback.
- Added `/api/v1/daw/session` and `/api/v1/daw/render-plan` plus a browser arrangement editor for tracks, source clips and render validation.
- Advanced the engine handshake to 3.3 and public C ABI to 1.48 with `org.upp.daw.session/1` and `org.upp.daw.render-plan/1`; added two schemas.

## Core 4.2 — Operational Process & Hardware Boundary

- Added mode-0600 Unix-domain IPC carrying bounded authenticated UPPF frames, with strict length checks, socket timeouts, capability-scoped dispatch and replay rejection. Windows named pipes remain the declared platform adapter.
- Replaced default ephemeral interoperability secrets with an atomic, mode-0600, tamper-evident local identity store that persists key epochs, revocations and bounded reconnect checkpoints.
- Added a profile editor for density, contrast, reduced motion and control layout plus projection/consent visibility; preference edits preserve unknown fields and never arm outputs.
- Added a watchdog-managed isolated effect-host process. Built-in processing proves the boundary; VST3, CLAP, LV2 and Audio Unit require explicit external adapter executables and fail to bypass.
- Added platform qualification probes and LE Audio/UWB timing-plan validation. Discovery is not qualification, UWB never carries program audio, and hardware remains unqualified until real bench evidence is recorded.
- Added hardened systemd packaging, an explicit UWB udev opt-in rule, a non-activating installer and a qualification CLI.
- Advanced the engine handshake to 3.2 and public C ABI to 1.47 with local IPC, persistent security, isolated plugin-host and platform-qualification extensions. Physical outputs remain disarmed.

## Core 4.1 — Authenticated Framed Session Channel

- Added a fixed 84-byte network-order `UPPF` frame header with 4,096-byte bounded payloads, session identity, key epoch, monotonic sequence, capability scope and HMAC-SHA256 authentication tag.
- Added directional per-epoch key derivation bound to the authenticated Core 4.0 transcript. Send and receive keys are distinct and rotate only to advancing epochs.
- Added strict replay/reordering rejection and capability-scoped authorization before payload dispatch. Negotiating a session does not authorize every capability.
- Added bounded previous-key grace during coordinated rotation and authenticated reconnect checkpoints containing session identity, transcript, key epochs, sequence watermarks and capability scope.
- The channel explicitly reports `confidential=false`: it supplies message integrity and authentication, while confidentiality remains with negotiated TLS/DTLS/EDHOC/OSCORE or another secure transport.
- Added native `SessionChannelGuard`, authenticated Python frame codec, stdio/Python controls, three schemas and channel conformance vectors/runner.
- Advanced the engine handshake to 3.1 and public C ABI to 1.46 with `org.upp.core.session-channel/1`. Physical outputs remain disarmed.

## Core 4.0 — Authenticated Interoperability Sessions

- Bound participant offers, target identity, nonce, expiry, authority epoch, monotonic sequence and authentication metadata into canonical SHA-256 transcripts with dependency-free HMAC-SHA256 development authentication.
- Added replay, expiry, target, identity-fingerprint and protocol-downgrade rejection. The public ABI keeps signature verification provider-neutral for hardware-backed asymmetric implementations.
- Added the native `AuthenticatedInteropSession` lifecycle: offered, authenticated, negotiated, consented, active and expired. Profile, capability-registry, authority or time changes invalidate activation.
- Added digest-bound profile projection previews. Role, venue and session displacement of durable user choices requires consent; user accessibility preferences outrank cosmetic venue choices.
- Added a semantic capability registry carrying namespaced IDs, semantic versions, schema SHA-256 digests, adapter quality and provenance. Only explicit adapters participate in negotiation.
- Added eleven canonical conformance vectors and a standalone runner covering authentication, tampering, expiry, target binding, replay, downgrade, unknown preservation, missing requirements, consent and accessibility priority.
- Added a hardware bench analyzer and report schema for transport latency, jitter, clock offset, loss and soak duration. Loopback reports can never be labeled measured; hardware reports require explicit UWB and LE identities and valid samples.
- Added authenticated HTTP, Python-client, stdio and public C surfaces. Engine handshake is 3.0; public C ABI is 1.45 with four new extensions and five new schemas.
- No radio hardware was attached during this build. The bench interface and deterministic loopback evidence are validated, but BlueZ BAP/QoS, vendor UWB firmware and physical latency qualification remain pending real devices rather than being fabricated.

## Core slice 3.9 — User Profiles + Interoperability Handshake

- Added fixed-capacity native `UserProfileCustomization` with stable namespace/key identities and deterministic base, user, role, venue and session layers.
- Preference updates are revisioned per layer, stale replacements fail closed, and session overrides can be cleared without erasing durable user choices.
- Added local persistent `org.upp.user-profile` documents for display, accessibility, workflow and control-layout preferences while preserving unknown top-level, extension and preference fields.
- Newer profile documents remain forward-readable only when their declared minimum reader permits it; unknown semantics are retained and never guessed.
- Added fixed-capacity native `InteroperabilityHandshake` selecting the highest common protocol/profile schema and classifying direct, explicitly adapted, preserved-unknown and missing-required capabilities.
- Handshakes require explicit adapter mappings, report adapter quality and offline compatibility, and fail closed when required capabilities or safe unknown preservation are absent.
- Added authenticated stdio, Python client and `/api/v1/profile` surfaces. Customization and handshake results always report or imply `physicalOutputsArmed=false` and cannot override authority or safety policy.
- Advanced the native handshake to 2.7 and public C ABI to 1.44 with `org.upp.profile.customization/1` and `org.upp.core.interoperability-handshake/1`; added two schemas.
- Added native, client, persistence and HTTP regressions for layer precedence, stale revisions, explicit translation, unknown preservation, future-reader refusal and output-authority separation.

## Core slice 3.8 — Linux LE ISO + UWB Hardware Bridge

- Added a nonblocking Linux `AF_BLUETOOTH` / `BTPROTO_ISO` socket adapter for established LE isochronous streams. Platform BAP discovery, pairing, codec selection, QoS and authorization remain outside Core.
- Added a nonblocking POSIX serial/VCOM UWB bridge with an 80-byte fixed little-endian frame, version/length checks, CRC-32, fragmented-read handling and garbage resynchronization.
- Kept FiRa UCI and vendor radio commands behind replaceable device adapters. The `SFUW` record is a normalized StageMesh evidence frame, not a claim of FiRa UCI wire compatibility or certification.
- Added a fixed-capacity hardware manager that pumps UWB observations and LE timing sidecars into `LeUwbHub` on the control thread; audio SDUs stay in the audio adapter and no hardware I/O enters the mix callback.
- Derived LE transport latency and jitter from paired node/hub timing evidence, with existing sequence, authority-epoch, authentication, freshness and uncertainty fences still enforced by the hub.
- Added `HUB_HW_*` authenticated local commands and Python client methods for explicit open/close, bounded polling and telemetry. Every result keeps `physicalOutputsArmed=0`.
- Advanced the native handshake to 2.6 and public C ABI to 1.43 with `org.upp.hardware.le-iso/1` and `org.upp.hardware.uwb-bridge/1`; added `le-uwb-hardware.schema.json`.
- Added deterministic stream/seqpacket loopback regressions for frame integrity, fragmentation, resynchronization, nonblocking behavior and end-to-end hub readiness. These are interface tests, not measured radio latency claims.

## Core slice 3.7 — LE-UWB Live Stage Synchronization Hub

- Added fixed-capacity native `LeUwbHub` coordination for up to 64 performer inputs, monitor outputs, stage outputs, lighting endpoints and control endpoints.
- Combined Bluetooth LE isochronous transport evidence with UWB paired-clock/ranging observations without treating UWB ranging as the audio transport or LE pairing as proof of stage-grade timing.
- Added authority-epoch fencing, independent monotonic LE/UWB sequences, authenticated-evidence enforcement, UWB propagation correction, clock discipline, bounded drift, observation freshness and UWB holdover.
- Added group presentation planning in common hub time, device time and StageMesh Show Time. Required nodes must jointly satisfy clock uncertainty, range uncertainty, LE jitter, transport latency and end-to-end lead limits.
- Group plans fail closed for missing/stale/replayed/unauthenticated/wrong-epoch evidence. Optional nodes remain observable without blocking required program membership.
- Physical output authority remains separate: every plan and node surface explicitly reports `physicalOutputsArmed=false`; the hub never pairs radios, installs keys or arms audio/lighting hardware.
- Added native stdio commands, Python client methods and authenticated HTTP adapter-report endpoints for hub configuration, node registration, dual-radio observations, group planning and node inspection.
- Advanced the native handshake to 2.5 and public C ABI to 1.42 with `org.upp.stage.le-uwb-hub/1`; added `le-uwb-hub.schema.json`.
- Added native, stdio-client and HTTP regressions for synchronized presentation targets, dual-radio readiness, UWB holdover, replay rejection, epoch fencing, stale evidence and output-arm separation.

## Core slice 3.6 — Canonical 32-bit Float / 192 kHz Audio Domain

- Standardized graph, automation, monitor and per-output effect processing on planar IEEE float32 at 192 kHz, independent of physical capture and playback rates.
- Added bounded allocation-free 16-tap windowed-sinc conversion at each source and sink edge with persistent fractional-frame accounting for non-integer ratios such as 44.1 → 192 kHz.
- Added independent persisted sample rates for all four input slots; 44.1, 48, 88.2, 96 and other supported rates can run concurrently into the same canonical graph.
- Added integer PCM normalization for signed 16-bit, packed little-endian signed 24-bit and signed 32-bit inputs, including mono-to-stereo normalization.
- Kept drift compensation separate from rate-domain conversion and kept both independent of StageMesh Show Time.
- Added engine handshake 2.4, public C ABI 1.41, `org.upp.audio.canonical-domain/1`, `org.upp.audio.rate-converter/1` and `canonical-audio-profile.schema.json`.
- Added regressions for exact 48 → 192 kHz conversion, long-run 44.1 → 192 kHz frame accounting, PCM normalization and multi-rate input persistence.
- Upsampling standardizes the engine processing domain; it intentionally makes no claim to recreate source bandwidth or detail that was never captured.

## Core slice 3.5 — VST3 + Multi-Format Effect Chain

- Added fixed-capacity native `CoreEffectChain` with ordered in-place processing for VST3, CLAP, LV2, Audio Unit and built-in effect adapters.
- Kept plugin SDKs and licensing outside Core. Format adapters provide activation, real-time process and deactivation callbacks through one provider-neutral contract.
- Activation remains on the control thread; the audio callback performs no allocation, discovery or lifecycle work. Only adapters declaring real-time safety can register.
- Each output owns an independent chain. Effect latency, processed blocks/frames, bypass state and failures are observable.
- A failed processor is atomically bypassed for later blocks so one plugin cannot repeatedly collapse the complete output chain.
- Connected effect-chain processing after route/mix and before final master/limiter protection; retained the existing Core parameter bridge for sample/block automation.
- Added `EFFECT_STATUS`/`EFFECT_BYPASS`, Python client inspection, engine handshake 2.3, public C ABI 1.40 and `audio-effect-chain.schema.json`.
- Added native regression coverage for VST3/CLAP ordering, processing, accumulated latency and failure isolation.

## Core slice 3.4 — Authenticated Planned-Handoff Coordination

- Connected the native planned-handoff transaction to the authenticated replication and witness layers.
- Primaries create target-bound SHA-256/HMAC offers fixing transaction, node, epoch, Show-Time and degraded-program facts; standbys verify the canonical offer and replicated source before native preparation.
- Added explicit execution-backed operator pre-roll acknowledgement. Missing readiness fails closed unless degraded transfer was declared in the signed offer.
- Commit requires the standby to acquire the exact offered witness epoch and reach the Show-Time boundary before native commit and role promotion.
- Physical outputs remain disarmed. Added status/offer/accept/acknowledge/commit/abort HTTP surfaces and tamper/target-binding regressions.
- Added `planned-handoff-offer.schema.json`; public C ABI remains 1.39 and native handshake remains 2.2.

## Core slice 3.3 — Fenced Planned Primary Handoff

- Added native `CorePlannedHandoff`, a single-pending control-plane transaction for graceful primary handoff at an explicit Show-Time boundary.
- Preparation fixes transaction identity, source/target authority epochs, target Show Time and whether an explicitly degraded program handoff is allowed.
- Target acknowledgement is required before commit. Program-not-ready acknowledgement fails closed unless degraded transfer was declared at preparation.
- Commit validates transaction identity, observed source epoch, exact witness target epoch and the Show-Time boundary; stale epochs and early commits are rejected.
- Abort is explicit and preserves conflict/prepare/commit/abort telemetry. Completed authority handoff still reports `physicalOutputsArmed=false`.
- Added native stdio and Python-client surfaces (`HANDOFF_TX_*`), advanced the engine handshake to 2.2, and added end-to-end fencing regressions.
- Advanced the public C ABI to 1.39 with `org.upp.core.planned-handoff/1` and added `planned-handoff-status.schema.json`.

## Core slice 3.2 — Native Deterministic Render Execution

- Added fixed-capacity native `CoreShadowRenderExecutor`, the missing execution seam between deterministic source adapters and verified shadow-prebuffer evidence.
- Renderer adapters register explicit runtime identity, starting Show Time and a block callback; Core advances blocks deterministically to a requested horizon.
- Only successful adapter callbacks publish contiguous evidence into `CoreShadowPrebuffer` and readiness into `CoreShadowRenderPlanner`.
- Renderer failure, stale planner identity, invalid block geometry and show-revision invalidation fail closed and revoke readiness.
- Preserved authority separation: the executor neither arms hardware nor acquires output authority.
- Advanced the public C ABI to 1.38 with `org.upp.core.shadow-render-executor/1` and added `shadow-render-executor-status.schema.json`.
- Added native regressions for ordered stepping, partial final blocks, planner publication and failure revocation.

## Core slice 3.1 — Verified Shadow Prebuffer + Duplicated Feed Evidence

- Added fixed-capacity native `CoreShadowPrebuffer` execution evidence. Deterministic renderer adapters now advance a source horizon only with contiguous rendered blocks matching runtime generation, show revision and content identity; gaps invalidate readiness instead of silently stretching the horizon.
- Added native `SHADOW_BLOCK` stdio ingestion with rendered-frame/block/discontinuity telemetry and automatic publication into `CoreShadowRenderPlanner`. Engine handshake advanced to `2.1`.
- Hardened handoff execution evidence so a reported shadow horizon alone no longer proves `prebufferReady`; reports must carry rendered block bounds and frame counts to become execution-verified.
- Hardened duplicated live-input readiness so health/configuration declarations alone no longer prove program continuity. Fresh feed evidence must include Show-Time bounds, observed frames and a monotonic sequence; discontinuities revoke execution readiness.
- Preserved authority/program separation: failed or missing execution evidence blocks seamless program takeover but does not broaden physical-output authority or auto-arm hardware.
- Advanced the public C ABI to 1.37 with `org.upp.core.shadow-prebuffer/1` and added `shadow-prebuffer-status.schema.json`; handoff execution schema now exposes evidence type, continuity and verification fields.
- Added native/Python regression coverage for contiguous shadow blocks, stale identity, block gaps, health-only live-feed reports and verified duplicated-feed takeover.

## Core slice 3.0 — Native Runtime Execution Stack

- Added fixed-capacity `CoreParameterRegistry` with unit/range/default/timing/safety metadata and explicit endpoint kinds for mixer, monitor, spatial, plugin and lighting control. Registered endpoint defaults now seed native automation baselines so a first ramp begins from the actual current value instead of numeric zero.
- Bound Core automation to real native endpoints: audio-output master, audio route gain, monitor master/channels and DMX values. Audio-master endpoints are block/real-time readers; route-matrix and monitor/lighting writes remain on the Core/control side where publication may wait safely.
- Added a provider-neutral plugin parameter bridge callback seam so CLAP/VST/LV2 adapters can expose native parameters without changing Core automation semantics. No proprietary plugin format is required by the registry.
- Added `CoreCueActionGraph`. A cue can atomically define up to 32 deterministic transport/automation/MIDI/lighting actions; when the cue fires, the sole timeline owner schedules derived actions directly into the same ordered/replay-protected timeline, including future Show-Time offsets.
- Added immutable fixed-capacity `CoreRuntimeShow` snapshots for roles, cues, routes and parameter descriptors. Validated bridge state is compiled into a pending native generation and RCU-published only when its requested Show-Time boundary is reached. Old readers retain the previous generation until release.
- Added `CoreRoutingState` transactions with expected-revision fencing, bounded staging, graph-cycle detection, commit/rollback and metrics.
- Reworked `AudioGraph` routing into double-buffered RCU route matrices. Multi-route commits publish as one generation, so an audio callback cannot observe half of a routing transaction.
- Added `CoreJournal`, a fixed-capacity hash-linked native execution record for transport, cue, automation, MIDI, lighting, routing and runtime-generation events. Core performs no filesystem I/O; the Python persistence service drains these records into the existing durable SHA-256 ledger.
- Added `CoreShadowRenderPlanner` with deterministic-source declaration, generation/show-revision/content-hash matching, buffered-horizon reports, invalidation and readiness planning. It remains a planner/evidence contract, not a fake renderer.
- `NativeEngineClient.sync_state()` now compiles each validated bridge snapshot into a native runtime generation and registers stable parameter bindings for player monitors and audio-output masters. Stable string identities use reproducible FNV-1a 64-bit IDs.
- Standby shadow-prebuffer reports are mirrored into the native planner when possible; handoff status exposes native shadow-plan diagnostics without replacing the existing authority decision contract.
- Added native stdio surfaces for parameter binding/status, cue graph compilation, runtime-show compilation/status, routing transactions, journal inspection and shadow planning. Engine handshake advanced to `2.0`.
- Advanced the public C ABI to 1.36 with `parameter-registry`, `cue-action-graph`, `runtime-show`, `routing-transaction`, `journal`, `shadow-render-planner` and `plugin.parameter-bridge` extension contracts.
- Added seven public schemas for the new Core contracts, bringing the schema set to 51.

## Core slice 2.4 — Native Automation State + Linear Interpolation

- Added fixed-capacity `CoreAutomationState` as native authoritative state for typed automation parameters keyed by `(targetId, parameterId)`.
- Due automation events are now applied directly by the sole `ShowExecutionLoop` writer instead of merely being forwarded to a downstream compatibility queue.
- Added point automation and linear Show-Time ramps. Existing automation events remain points; optional `durationMs` extends the same payload without changing the existing fixed field layout.
- Added parameter-scoped owner semantics: a non-zero event owner claims an unowned parameter, mismatched owners are rejected deterministically, and an explicit owner-release show event relinquishes ownership.
- Added global automation revision plus per-parameter revision, last event, update count, owner, ramp bounds, start/target/current value and owner-conflict/capacity/release telemetry.
- Added double-buffered immutable automation publication slots with reader pins. Audio/render readers can evaluate one parameter or render a fixed block without locks, allocation or bridge calls; any wait remains on the single Core writer.
- Kept `EVENT_NEXT AUTOMATION` as a best-effort compatibility observation queue after native state application; Core state no longer depends on that queue succeeding.
- Added `AUTOMATION_STATUS`, `AUTOMATION_GET` and `AUTOMATION_BLOCK` stdio inspection plus extended `EVENT_SUBMIT AUTOMATION` syntax and `AUTOMATION_RELEASE`.
- Added Python native-client helpers and integration tests for automatic point application, midpoint interpolation, block interpolation and owner release.
- Native engine handshake now advertises `automationState=1`; engine version advanced to 1.4.
- Advanced the public C ABI to 1.29 with `org.upp.core.automation-state/1`, automation parameter/state status structures and read-only block-render contract.
- Added `automation-parameter.schema.json` and `automation-state.schema.json`, bringing the public JSON schema set to 44, and extended the typed show-event schema with `durationMs` and the explicit automation-owner-release flag.

## Core slice 2.3 — Dedicated Show Execution Loop + Native Cue Authority

- Added `ShowExecutionLoop`, a dedicated native Core thread that continuously owns typed timeline ingestion and dispatch against authoritative StageMesh Show Time.
- The loop sleeps/wakes against the next pending Show-Time deadline, wakes on new event or transport/clock changes, and publishes side-effect-free loop telemetry (`cycles`, wakeups, timed waits, dispatch count, compatibility drains/cancels, last Show Time).
- Converted `EVENT_DRAIN` and `EVENT_CANCEL` into synchronous compatibility requests executed by the same owner thread; they no longer create a second timeline owner.
- Added `CoreCueState`: cue transitions now update current/previous cue, last event/time and transition count directly in native Core when due. `CUE_STATUS` is observation-only.
- Added bounded SPSC MIDI and lighting domain handoff queues between the Core timeline thread and the retained legacy domain schedulers, removing the cross-thread scheduler mutation race exposed by automatic dispatch.
- Kept automation point events on their existing bounded Core handoff queue for the next migration slice; no automation-interpolation semantics were invented in this change.
- Added source-domain command identities inside `CoreControlState`, so direct operator command ID `N` and typed show-event ID `N` cannot collide in the deduplication cache.
- Added `EVENT_LOOP_STATUS` and exposed show-loop/cue state through native client health; engine handshake now advertises `showLoop=1 cueState=1` and native engine version is 1.3.
- Added wake notifications after direct transport/snapshot/clock-rate changes so the event owner does not wait for its bounded polling interval when Show-Time progression changes.
- Added `SpscQueue::size_approx()` for observation-only domain-handoff telemetry without changing producer/consumer ownership.
- Advanced the public C ABI to 1.28 with `org.upp.core.show-execution-loop/1` and `org.upp.core.cue-state/1` plus loop/cue status contracts.
- Added `show-execution-loop-status.schema.json` and `cue-state.schema.json`, bringing the public JSON schema set to 42.
- Added native and stdio-client regressions for automatic due-event execution without manual drain, paused-clock compatibility drain, owner-thread cancellation, cue-state transitions, source-domain dedup isolation and loop telemetry.

## Core slice 2.2 — Typed Show Timeline + Deterministic Dispatch

- Added allocation-free typed `ShowEvent` payloads for transport, MIDI, lighting, cue and automation events.
- Added fixed-capacity `ShowTimeline` with deterministic ordering by Show Time, priority, event type and event ID.
- Added `ShowEventDispatcher` with SPSC ingress, single-owner timeline ingestion/dispatch, bounded domain-aware replay protection, late-event/drop-if-late policy, cancellation and overflow/failure metrics.
- Kept event-status observation read-only/atomic; reading metrics never drains ingress or becomes a second timeline consumer.
- Routed legacy native `MIDI_SCHEDULE` and `LIGHT_SCHEDULE` through the shared Core timeline while preserving their existing drain/output protocol behavior.
- Added typed native stdio commands for `EVENT_SUBMIT`, `EVENT_STATUS`, `EVENT_DRAIN`, `EVENT_CANCEL` and cue/automation `EVENT_NEXT`.
- Typed transport events now mutate `CoreControlState` at their due Show Time; cue/automation events route to bounded Core queues for later domain execution.
- Added Core timeline metrics to native health and advertised `showEvents=1` in engine handshake; native engine version advanced to 1.2.
- Added Python native-client helpers and integrated protocol regression coverage for typed cue and transport dispatch.
- Added `show-event.schema.json` and `show-dispatch-status.schema.json`.
- Advanced the public C ABI to 1.27 with `org.upp.core.show-timeline/1` and `org.upp.core.show-dispatch/1` plus fixed typed event/status structures.
- Added native regressions for equal-time priority ordering, same-domain replay rejection, cross-domain legacy ID compatibility, late-event dropping, cancellation and timeline overflow.

## Core slice 2.1 — Native Control State + Real-Time Clock Publication

- Added native `CoreControlState` as the first authoritative Core control primitive for show-critical transport and personal-monitor state.
- Added global Core revision, transport revision and player-monitor revisions plus bounded command-result deduplication and explicit conflict/invalid/busy results.
- Added atomic bridge snapshot transactions (`CORE_SYNC_BEGIN`, staged transport/monitor state, `CORE_SYNC_COMMIT`/abort). One development show revision is no longer mirrored into native execution as a partially visible sequence of BPM/seek/play/monitor mutations.
- Added stale external-snapshot rejection and duplicate snapshot handling.
- Routed legacy native `TRANSPORT`, `SET_BPM`, `SEEK`, and `MONITOR_SET` commands through the Core mutation path so Core metrics/revisions stay coherent while old clients remain compatible.
- Added `CORE_STATUS` and native health fields for Core revision, external revision, snapshot commits, duplicate commands and conflicts.
- Reworked `TransportClock` publication into double-buffered RCU-style snapshots. Audio/render readers pin an immutable slot and do not acquire or wait on the control-writer mutex.
- Added concurrent reader/writer native regression coverage for clock publication.
- Added fixed-capacity `CoreResourcePlanner` with deterministic Full / Reduced / Safe Show / Audio Only policy, priority protection, degradation and suspension behavior.
- Advanced the public C ABI to 1.26 with `org.upp.core.control-state/1` and `org.upp.core.resource-planner/1`.
- Updated the Python native bridge to use Core snapshot transactions for transport/monitor mirroring while retaining existing API compatibility.

## Infrastructure slice 2.0 — Venue Reconciliation + Temporary Authority

- Added `backend/reconciliation.py` with deterministic comparison of the committed Venue Patch Layer against the current venue plan and fresh execution-adapter evidence.
- Reconciliation explicitly distinguishes `no-active-patch`, `unverified`, `realized`, `drift`, and `blocked`; a compatible configuration without execution evidence is no longer mistaken for realized hardware state.
- Added ephemeral authenticated realization reports keyed by logical patch role. Reports carry provider/target/health/authority-holder state and expire by freshness policy rather than becoming persistent truth.
- Added a one-second reconciliation monitor that emits audited events only when meaningful reconciliation state changes; it never enters the real-time audio/MIDI/lighting path.
- Added repair proposal logic: drift/blocked state can stage a new normal Venue Adaptation transaction only when the current venue plan is itself compatible and fully ready; no silent auto-repair or auto-rollback occurs.
- Added `VenueAuthorityLeaseRegistry` for explicit temporary authority handoff by patch key or department. Leases are bounded to 12 hours, one active holder per scope, automatically expire fail-closed, and are cleared whenever the Venue Patch Layer commits or rolls back.
- Reconciliation treats a valid authority lease as the expected temporary owner; an unleased authority-holder mismatch is a blocker.
- Added `/api/v1/venue/reconciliation`, `/evidence`, `/report`, `/repair`, plus venue authority lease inspection/grant/revoke endpoints. Adapter realization reports use the existing localhost-or-token authentication boundary.
- Added browser realization health, repair proposal, and minimal five-minute authority lease/revoke controls while keeping venue/show intent separate.
- Added `venue-reconciliation-report.schema.json`, `venue-realization-evidence.schema.json`, and `venue-authority-lease.schema.json`.
- Advanced the public C ABI to 1.24 with `org.upp.venue.reconciliation/1`, `org.upp.venue.realization-evidence/1`, and `org.upp.venue.authority-lease/1`.
- Expanded compatibility-core capabilities with realization monitoring, repair proposals, and authority leasing.
- Added reconciliation, authority precedence/expiry, runtime evidence, and HTTP API regression coverage.

## Infrastructure slice 1.9 — Transactional Venue Adaptation

- Added a persistent `VenueAdaptationManager` that converts a deterministic venue-compatibility plan into a reversible environment transaction without rewriting show intent.
- Transactions fingerprint both current show requirements and the full venue execution plan; validation re-runs before commit and rejects stale show requirements, changed discovery/provider evidence, timing changes, blockers or unresolved required patches.
- Added a separate atomic active Venue Patch Layer containing logical patch key → provider/target/capability/timing resolution mappings. The layer is environment state and is excluded from show-critical primary→standby snapshots.
- Added current→proposed transaction diffs and preserved previous active patch state for rollback.
- Added `immediate`, `next-bar` and named `cue` commit modes. `next-bar` schedules against current StageMesh show time/BPM; cue commits require an explicit cue trigger.
- Added a single-pending-commit fence so two future venue transactions cannot race at the same musical/cue boundary.
- Added a separate optimistic adaptation revision so stale production-control clients receive explicit conflicts instead of last-write-wins behavior.
- Added atomic rollback for the currently active transaction and cancellation rollback for pending transactions.
- Added adaptation receipts to the existing append-only hash-linked event record. Receipts preserve transaction ID, exact change list, commit boundary and previous/new patch revisions; adaptation never auto-arms physical audio or lighting.
- Added explicit execution mapping support: a committed patch can provide venue-local audio endpoint IDs or lighting network execution details without rewriting portable show-state device intent; live discovery IDs can satisfy the same seam. Physical execution still requires the existing explicit arm acknowledgements.
- Added `/api/v1/venue/adaptations`, `/active`, proposal/validate/commit/rollback routes and named-cue trigger surface.
- Added browser controls for proposal, validation, immediate/next-bar commit, current patch visibility and rollback.
- Added `scripts/stagemesh-venue-adapt.py` for offline transaction preview using the same migration/requirements/venue resolver/transaction builder as the live runtime.
- Added `venue-adaptation-transaction.schema.json` and `venue-patch-layer.schema.json`.
- Advanced the public C ABI to 1.23 with `org.upp.venue.adaptation/1` and `org.upp.venue.patch-layer/1`.
- Expanded compatibility adapter capabilities with venue transaction/patch/boundary/rollback semantics.
- Added unit/API regressions for atomic commit, musical-boundary scheduling, cue commit, rollback, stale-plan invalidation and pending-transaction fencing.

## Infrastructure slice 1.8 — Venue Compatibility + Pre-Arrival Planning

- Added `backend/venue.py` with lossless UPP venue-profile normalization, stable logical device identity and separate node-local venue-profile persistence.
- Added expected-vs-discovered device evidence; an omitted discovery set means pre-arrival profile planning, while an explicit scan can mark missing expected devices offline.
- Added `matchIds` so a stable venue device can match platform-specific ALSA/MIDI/backend discovery identifiers without changing logical patch identity.
- Added forward-readable venue schema metadata (`minimumReaderSchemaVersion`) with unknown-field preservation and hard refusal when a future venue profile requires a newer reader.
- Added venue capability aggregation across devices, profiled humans and explicit adapters; human-assisted fallbacks remain visible as human participation rather than being flattened into device capability.
- Added per-requirement timing-envelope checks for fixed latency, jitter and timestamp support.
- Added logical patch readiness (`ready`, `needs-patch`, `blocked`) separately from capability quality.
- Added department-level compatibility summaries plus deterministic arrival actions (`verify-adapter`, `confirm-human`, `patch`, `timing`, `discovery`, `blocker`).
- Added `/api/v1/venue/profile`, `/api/v1/venue/profile/inspect`, and `/api/v1/venue/plan`.
- Added `scripts/stagemesh-venue-check.py` for offline show + venue preflight using the same resolver as the runtime.
- Added frontend venue profile preflight and explicit live-discovery verification controls.
- Added `venue-profile.schema.json`, `venue-compatibility-plan.schema.json`, and an example venue profile.
- Advanced the public C ABI to 1.22 with `org.upp.venue.profile/1` and `org.upp.venue.compatibility/1`.

## Infrastructure slice 1.7 — Compatibility-First Evolution

- Added `backend/compatibility.py` with explicit API/schema/capability participant normalization and negotiation.
- Added lossless forward-compatible show-state overlays: a newer document can be read by API 1 only when `minimumReaderApiVersion <= 1`, and unknown nested fields survive load/edit/checkpoint/re-export.
- Added hard refusal for documents that require a newer reader rather than silently dropping unsupported semantics.
- Added explicit early API-v0 migration mappings without semantic guessing and a standalone `scripts/stagemesh-convert.py` inspector/migrator.
- Added `compatibility` metadata to show-state snapshots plus `X-UPP-API-Version` / `X-UPP-Minimum-Reader-Version` response headers.
- Added `/api/v1/compatibility`, `/show-state`, `/negotiate`, `/show-plan`, `/inspect-show-state`, and `/migrate-show-state` surfaces.
- Added show-specific requirement resolution with direct/equivalent/acceptable/degraded/blocked quality and declared fallbacks.
- Added advertised legacy API aliases so old slot-0 audio clients can coexist with current multi-slot routes.
- Added `compatibility-core` resource adapter; it remains outside real-time execution.
- Added public UPP C ABI 1.21 contracts for compatibility negotiation, schema migration, and unknown-field preservation.
- Added compatibility participant/report/show-plan/show-state schemas and expanded show-state schema for forward-readable API versions.
- Added frontend compatibility health/status panel.

## Infrastructure slice 0.3

- Added dependency-free native `AudioDevice` abstraction and `NullAudioDevice`.
- Added atomic, player-scoped `MonitorBus` state and fixed registry.
- Added allocation-free `MonitorMixer` block primitive.
- Added fixed-capacity timestamped `MidiScheduler`.
- Added latency/jitter/lookahead `LatencyResolver`.
- Added native `stagemesh_engine` stdio execution process.
- Added optional Python-to-native execution follower integration.
- Added `/api/v1/native` status endpoint.
- Added `/api/v1/timing/plan` latency planning endpoint and schema.
- Added global audit revisions plus resource-scoped revisions for multi-control-point concurrency.
- Serialized mutation/persistence/native-sync ordering.
- Advanced the public C extension ABI to 1.2 with audio/monitor/timing/MIDI extension identifiers.
- Added native integration, timing, and resource-concurrency tests.
- Added `scripts/build-native.sh`.

## Infrastructure slice 0.4 — Auto Notation

- Added player-scoped automatic notation capture derived from note on/off events.
- Raw performance timing is preserved separately from the quantized notation view.
- Added selectable 1/4, 1/8, 1/16 and 1/32 notation grids.
- Added deterministic project-key-aware sharp/flat pitch spelling.
- Added persisted notation parts and independent `notation:{player}` resource revisions.
- Added notation capture/settings/clear HTTP endpoints.
- Added player MIDI input observer endpoint so note events feed notation automatically.
- Added MusicXML 4.0 partwise export for notation interoperability.
- Added lightweight SVG staff + textual frontend notation preview and development capture probe.
- Added `notation-core` adapter resource profile with capture-only degradation.
- Added native `NotationQuantizer` primitive and stdio quantization command.
- Advanced public C ABI to 1.3 with `org.upp.notation.capture/1`.
- Added notation schema, API tests, persistence tests and native quantizer tests.

## Infrastructure slice 0.5 — MIDI Discovery + Clock Holdover

- Added native allocation-free MIDI byte-stream parser with running-status, realtime-byte, one/two-data-byte and SysEx-skip handling.
- Added dependency-free Linux raw-MIDI discovery/open/read support through `/dev/snd/midiC*D*`; other platforms remain replaceable backend seams.
- Added native hot-plug rescans, bounded captured-input queue and player/device attachment state.
- Added native MIDI input stdio commands for scan, device inspection, attach/detach, polling and test injection.
- Added backend MIDI desired-state bindings that persist even when hardware is absent and automatically reattach when matching endpoints reappear.
- Added bounded MIDI activity journal and independent `midi:<player>` concurrency revisions; notation remains an observer rather than owner of MIDI input.
- Added background native MIDI pump so hardware input can flow into authoritative state/notation without browser polling.
- Added `/api/v1/midi/devices` and scan/attach/detach routes plus a lightweight frontend MIDI input panel.
- Added `midi-device-profile.schema.json` and expanded MIDI adapter capabilities for discovery/hot-plug/binding.
- Added native `ClockDiscipline` primitive with soft phase correction, drift estimation and holdover state.
- Added `/api/v1/clock`, clock source/observation routes and frontend LOCKED/HOLDOVER/LOCAL visibility.
- Kept transport authority explicit and separate from clock-source authority.
- Advanced the public C ABI to 1.5 with MIDI input and clock-discipline extension interfaces.
- Expanded regression coverage to MIDI parsing, persisted desired mappings, MIDI/notation resource isolation, native input injection and clock holdover.

## Infrastructure slice 0.6 — Native Audio Routing + Device Desired State

- Added fixed-capacity, allocation-free native `AudioGraph` with 32 source slots, 16 output slots and atomic route/master controls.
- Added per-output peak protection with configurable dBFS ceiling and gain-reduction metering.
- Added dependency-light `AudioDeviceManager` with permanent null endpoint plus runtime-loaded ALSA PCM discovery on Linux through `libasound.so.2` when present.
- Kept hardware discovery/desired selection separate from actual execution; the starter still identifies `null-audio` as its execution backend until a platform stream adapter is installed.
- Added persisted, resource-scoped audio desired state: device ID, sample rate, buffer frames and limiter ceiling.
- Added `/api/v1/audio/devices`, `/api/v1/audio/scan` and `/api/v1/audio` control surfaces plus frontend audio discovery/selection.
- Added native audio scan/select/routing/output commands to the development execution protocol.
- Fed external clock drift rate into `TransportClock` without discontinuously jumping transport position.
- Expanded the public C ABI with audio-device and audio-routing extension interfaces.

## Infrastructure slice 0.7 — Show-Time Lighting Scheduler

- Added fixed-capacity native lighting scheduler and per-universe 512-slot DMX state.
- Added allocation-free ArtDMX packet construction for Art-Net protocol version 14.
- Added latency-aware lighting scheduling that converts artistic target show time into an earlier dispatch time using endpoint latency, jitter margin and lookahead.
- Added a development lighting dispatch pump driven by StageMesh show time.
- Kept packet construction/state execution separate from physical UDP transmission; this slice does not silently control venue fixtures.
- Added `/api/v1/lighting/schedule` and `/api/v1/lighting/universe/{n}` inspection endpoints.
- Split lighting capability reporting into a healthy local scheduler/encoder and a deliberately unavailable network-output adapter.
- Added `lighting-endpoint-profile.schema.json` for protocol/timing/authority metadata.
- Advanced the public C ABI to 1.7 with `org.upp.lighting.output/1`.

## Infrastructure slice 0.8 — Explicit Physical Execution + Hot Standby

- Release-build native tests now use always-on checks rather than `assert`, so optimized verification cannot silently disable the test conditions.

- Added runtime-loaded Linux ALSA 32-bit-float playback with a dedicated render thread, preallocated buffers, callback counters, xrun recovery/accounting and safe null-backend fallback.
- Kept desired audio endpoint selection separate from physical stream activation; hardware output requires explicit acknowledgement and never auto-arms after restart.
- Added `MonitorGraphRouter`, mapping personal MonitorBus controls into the fixed native graph with dedicated per-player self stems and shared vocal/band/click/talkback/ambient stems.
- Added explicitly armed unicast Art-Net UDP transmission. Configuration alone cannot send; restart, reconfiguration, demotion and shutdown disarm physical output.
- Added frontend controls/status for physical audio execution and Art-Net arming.
- Added random per-spawn authentication tokens to the development stdio IPC bridge; native commands are rejected until `AUTH` succeeds when a token is configured.
- Added primary/standby node authority fencing. Standby nodes are read-only, do not ingest mapped MIDI, and cannot arm physical audio or lighting.
- Added canonical SHA-256 replication envelopes with optional HMAC-SHA256 authentication, epoch/sequence replay fencing and full recoverable show snapshots.
- Added explicit authority handoff; promotion never automatically restores physical output authority.
- Added node/replication HTTP surfaces and frontend primary/standby visibility.
- Added node-authority and replication-envelope schemas.
- Split implemented Art-Net network capability from not-yet-implemented sACN capability reporting.
- Advanced the public C ABI to 1.9 with audio-stream, lighting-network, authority and replication extension contracts.
- Expanded regression coverage for ALSA runtime streaming, monitor graph mapping, explicit Art-Net arming, IPC authentication, replication tamper/replay detection and standby fencing.

## Infrastructure slice 0.9 — Automatic Replication + Native Audio Input

- Added automatic primary-to-standby HTTP replication transport for the existing canonical/HMAC envelopes.
- Primary nodes send on state revision changes plus periodic heartbeats; automatic LAN replication is disabled unless a replication secret is configured.
- Added transport health counters, peer status, heartbeat age and failure-detection surfaces.
- Added standby failure states: `waiting`, `healthy`, `suspect`, and `eligible`.
- Added controlled failover promotion endpoint. Ordinary standby-to-primary promotion is now fenced unless the failure threshold is satisfied or an explicit administrative `forceAuthorityOverride=true` is supplied.
- Promotion still never re-arms physical audio, audio input, MIDI authority, or lighting output.
- Increased replication apply request capacity for full recoverable show snapshots.
- Added runtime-loaded Linux ALSA float capture with a dedicated capture thread, xrun recovery and explicit activation/deactivation.
- Added fixed-capacity lock-free stereo `AudioInputRing` between capture and render threads.
- Added persistent desired audio-input endpoint, logical player-source assignment and explicit FOH route gain/output state.
- Physical input activation requires `acknowledgePhysicalInput=true`; a persisted nonzero route additionally requires `acknowledgeSignalRoute=true`.
- Audio input assigned to a player resolves onto that player's native self-source bus, allowing the same captured signal to feed personal monitoring and an explicit FOH graph route.
- Added input callback/xrun/queued/drop/underrun health reporting and frontend capture controls.
- Added `audio-input` and `replication-core` capability/resource profiles.
- Advanced the public C ABI to 1.10 with audio-input-stream, replication-transport and failover contracts.
- Added `replication-peer.schema.json` and expanded show-state audio schema.
- Expanded regression coverage for automatic signed heartbeat delivery, failover eligibility, explicit capture arming, desired input persistence, capture-to-monitor routing and native input buffering.

## Infrastructure slice 1.0 — Witness Quorum + Multi-Input Capture

- Added an external persistent witness lease service (`scripts/run-witness.sh`) with authenticated HMAC lease requests.
- Added multi-witness quorum client support through `STAGEMESH_WITNESS_URLS`; a majority must grant an unexpired lease before the node is authoritative.
- Primary nodes configured for witness mode self-fence and demote after quorum lease expiry. Physical audio input/output, lighting and mapped MIDI authority are silenced/detached during fencing.
- Added optional `STAGEMESH_AUTO_FAILOVER=1`: a standby promotes only after the replication heartbeat threshold **and** successful witness quorum lease acquisition.
- Witness authority epochs are adopted by replication ordering so failover ownership and replicated-state fencing share a monotonic authority generation.
- Added `/api/v1/witness` and witness detail to node/failover status and the frontend.
- Added four independent native ALSA capture slots feeding the fixed audio graph concurrently without allocation in the render path.
- Added slot-addressed input select/bind/activate/deactivate/status/route native commands while preserving old single-input commands as slot-0 compatibility aliases.
- Expanded show audio desired state with four portable `inputs[]` mappings: physical device → logical player → FOH route. Existing `inputDeviceId`, `inputPlayerId` and `inputRoute` remain compatibility aliases for slot 0.
- Added `/api/v1/audio/inputs` and `/api/v1/audio/inputs/{slot}` status plus per-slot activation/deactivation routes.
- Added frontend visibility for all four capture slots while retaining the simple slot-0 controls as the default surface.
- Advanced the public C ABI to 1.12 with `org.upp.core.witness-lease/1` and `org.upp.audio.multi-input-stream/1`.
- Added `witness-lease.schema.json` and expanded the show-state schema for multi-input desired state.
- Added witness lease expiry, quorum, automatic failover, multi-input persistence and native multi-slot regression tests.

## Infrastructure slice 1.1 — Multi-Output Audio + Failover Continuity

- Added four independently activatable native physical audio-output slots for FOH, monitor, broadcast/record and auxiliary destinations while preserving the old single-output API as slot-0 compatibility.
- Added fixed-capacity multi-reader `AudioFanoutRing`: one capture producer can feed multiple physical sinks without one output consuming another output's samples.
- Added independent per-output graph binding, including logical player-monitor resolution through `MonitorGraphRouter`.
- Added per-output callback/xrun plus fan-out queued/drop/underrun telemetry.
- Added diagnostic effective sample-rate drift estimation in ppm for each running ALSA sink, establishing the measurement seam for later adaptive resampling.
- Expanded persisted audio desired state with four portable `outputs[]` mappings while retaining `deviceId` and `limiterCeilingDb` as slot-0 aliases.
- Added `/api/v1/audio/outputs`, `/api/v1/audio/outputs/{slot}` and per-slot activation/deactivation routes.
- Added failover-continuity measurement at promotion: warm native-vs-authoritative show-time error is graded independently from the deliberate post-promotion delay before audio/lighting are manually re-armed.
- Added `/api/v1/failover/continuity` and frontend continuity/output health visibility.
- Advanced the public C ABI to 1.14 with `org.upp.audio.multi-output-stream/1` and `org.upp.core.failover-continuity/1`.
- Added audio-output and failover-continuity schemas plus multi-output persistence/API/native and failover-continuity regressions.
- Hardened the ALSA capture lifecycle test so CI environments that expose an unstable null-capture PCM cannot produce a false infrastructure failure after the backend contract has already opened/started successfully.

## Infrastructure slice 1.2 — Adaptive Sink Drift + Output-Gap Telemetry

- Added allocation-free `AdaptiveDriftController` and fixed-state planar linear resampler for independent physical audio sinks.
- Each output combines measured hardware sample-rate ppm with fan-out queue pressure, smooths the requested correction and clamps it to a persisted per-output safety envelope.
- Added per-output desired drift policy: enable/disable, maximum correction ppm and queue-error gain. Drift compensation never changes StageMesh Show Time.
- Added native `AUDIO_DRIFT_CONFIG` control with configuration changes fenced while a physical sink is running.
- Added live sink telemetry for measured ppm, applied correction ppm, source frames consumed per block and number of compensated blocks.
- Added ALSA first/last physical write timestamps, frames-written counters and maximum excess inter-write gap telemetry.
- Failover continuity now distinguishes first physical audio arm from first actual native audio write and reports post-resumption sink stalls separately.
- Frontend output health now exposes raw clock drift, active correction and observed output-gap information.
- Advanced the public C ABI to 1.15 with `org.upp.audio.drift-compensation/1` and expanded multi-output/failover-continuity status.
- Expanded audio-output and failover-continuity schemas and added drift policy persistence/API/native regression coverage.

## Infrastructure slice 1.3 — Signed Cross-Node Program Continuity

- Added per-sink native Show-Time render telemetry: first rendered block, last rendered block and last rendered block end. Machine-local physical write timestamps remain local diagnostics and are never compared across nodes.
- Added replication-envelope protocol v2. When execution telemetry is present it is included inside the canonical SHA-256/HMAC payload; protocol v1 envelopes remain verifiable for compatibility.
- Primary replication now carries a compact signed execution summary containing current Show Time, active physical output program positions and active live-input slots.
- Standbys retain the latest verified execution telemetry separately from the authoritative show model and use it only for failover continuity/readiness analysis.
- Failover continuity now reports `sourceLastProgramShowNs`, `newFirstProgramShowNs`, cross-node program gap/overlap and a continuity grade in the common Show-Time domain.
- Added handoff modes: `state-warm`, `deterministic-prebuffer-eligible` and `live-input-state-warm`. A live input prevents deterministic prebuffer claims unless a duplicated feed is introduced later.
- Added `handoffTargetShowNs` and diagnostic handoff-adjustment distance without advancing authoritative transport merely because an output buffer rendered ahead.
- Added `execution-telemetry.schema.json` and expanded replication/failover schemas.
- Added `/api/v1/failover/readiness` with explicit replica freshness, program cursor, local lag, live-input dependency and prebuffer blockers.
- Added `handoff-readiness.schema.json`.
- Advanced the public C ABI to 1.17 with `org.upp.core.failover-continuity/2`, `org.upp.core.replication-telemetry/1` and `org.upp.core.handoff-readiness/1` while preserving the v1 continuity struct.
- Expanded frontend failover visibility with program gap/overlap and prebuffer eligibility.
- Added signed-telemetry tamper tests, live-input handoff readiness tests, cross-node Show-Time gap tests and native render-position contract checks.

## Infrastructure slice 1.4 — Deterministic Handoff Logic

- Added a pure deterministic handoff decision engine that separates authority-transfer readiness from program-continuity readiness.
- Added persisted `handoff` show intent with an independent resource revision, configurable replica-age/local-lag policy, live-input redundancy declarations and deterministic source inventory.
- Active live inputs can declare `split` or `network` standby feeds; a feed is considered duplication-ready only when its mode, source identity and explicit ready state agree.
- Deterministic sources declare kind, required status, shadow-render capability, local asset availability and optional content hash. Source declarations are normalized and preserved in recoverable show snapshots.
- Added `/api/v1/handoff/decision` plus `PATCH /api/v1/handoff`; the older `/api/v1/failover/readiness` remains a compatibility projection.
- Handoff decisions expose separate authority/program blockers, missing live-input slots, unready deterministic source IDs and an explicit recommended action.
- Added ephemeral handoff execution acknowledgements. Shadow renderers report buffered Show-Time horizon/health/content hash and duplicated live-feed adapters report slot/source/health/latency.
- `readyForProgramTakeover` and `prebufferReady` become true only when fresh execution evidence satisfies the declared policy; declaration-level readiness alone is never promoted into a fake prebuffer claim.
- Execution evidence ages out and is cleared whenever replicated authority source/epoch changes, preventing stale readiness from crossing an authority generation.
- Added localhost-or-token protection for development HTTP execution-report routes through `STAGEMESH_ADAPTER_REPORT_TOKEN`.
- Failover status now exposes the current handoff decision, and the exact decision present at promotion is retained in the continuity report for later diagnosis.
- Added `handoff-policy.schema.json` and `handoff-decision.schema.json`; show state now references the portable policy contract.
- Added `handoff-logic` to the capability/resource planner.
- Advanced the public C ABI to 1.18 with `org.upp.core.handoff-policy/1`, `org.upp.core.handoff-decision/1` and `org.upp.core.handoff-execution/1`.
- Added deterministic logic, persistence, duplicated-live-feed, source-readiness and API regression tests.

## Infrastructure slice 1.5 — Technology Advancement Openness at Scale

- Added a deterministic technology-openness registry and assessment engine separate from show-critical execution.
- Added permissionless `experimental` maturity plus evidence-driven `community`, `candidate` and `standard` maturity levels.
- Experimental technology remains valid at every ecosystem scale without central namespace registration; scale safeguards raise only the evidence threshold for new Standard promotion/revalidation and mandatory-Core elevation.
- Existing recognized Standards are not retroactively de-standardized when the ecosystem grows. Instead, the assessment reports broader-scale revalidation evidence requirements while preserving compatibility status.
- Added scale tiers (`emerging`, `growing`, `large`, `infrastructure`) with configurable independent-implementation thresholds for Standard and mandatory-Core promotion.
- Standard eligibility requires a public specification, independent conforming implementations, interoperability evidence, fallback/backward-compatibility behavior and unknown-extension preservation testing.
- Mandatory vendor, mandatory cloud and mandatory AI dependencies block ordinary Standard promotion under the default openness constitution. `No AI` remains a valid participant mode.
- Added a configurable mandatory-Core extension budget so ecosystem growth favors optional profiles/extensions rather than continuously expanding the universal required core.
- Standard/Core technology records cannot be silently deleted. They may be deprecated/superseded, but a replacement is assessed for migration/compatibility bridging and the prior record remains present.
- Technology extension normalization preserves unknown fields so future concepts can survive older StageMesh/UPP implementations without data loss.
- Added exact capability negotiation: common capabilities execute; unknown local/remote capabilities are preserved and surfaced; the core performs no implicit semantic coercion.
- Added revisioned/persisted `technology` show-state metadata with independent concurrency control and API assessment surfaces.
- Added `GET /api/v1/technology`, `GET /api/v1/technology/assessment`, `PATCH /api/v1/technology` and `POST /api/v1/technology/negotiate`.
- Added frontend technology-openness visibility with scale tier, evidence thresholds, unknown-preservation/no-AI guarantees and per-extension revalidation status.
- Added `technology-openness` to the resource planner as background governance logic that can disappear without affecting show execution.
- Added technology openness policy, extension and assessment JSON schemas; schemas continue allowing unknown properties.
- Advanced the public C ABI to 1.19 with `org.upp.core.technology-registry/1`, `org.upp.core.technology-assessment/1` and `org.upp.core.technology-negotiation/1`.
- Added regression coverage for permissionless experimentation, scaling evidence thresholds, standard grandfathering, vendor/cloud/AI lockout, unknown-field preservation, core budget pressure, migration-safe deprecation, non-deletable standards and lossless capability negotiation.
- Kept routine live show snapshots bounded: they carry technology policy/participant/extension-count summary but not the full extension registry.
- Full technology catalogs remain available through the dedicated technology API and recoverable disk checkpoints.
- Show-critical primary→standby replication snapshots omit technology catalog/resource data entirely; applying such a replica preserves the standby node's local technology catalog. Governance/catalog synchronization can therefore scale independently from failover heartbeat bandwidth.
- Fixed `test_handoff.py` so plain repository-root unittest discovery no longer depends on an external `PYTHONPATH=backend` shell setting.
- Added `adoptionRecordRef` for grandfathered Standard recognition. At larger ecosystem scales, a lower-evidence Standard remains recognized only when it carries an adoption-record reference; simply declaring `maturity=standard` cannot bypass current-scale promotion thresholds.

## Infrastructure slice 1.6 — Community Control + Time-Decayed Hype Voting

- Added a community-governance subsystem isolated from show-critical state, replication, audio and control-point concurrency.
- Added deterministic proposal hype: `1.0` on day 1, linearly decaying to `0.0` on day 365 by default. Hype always contributes exactly zero yes/no/abstain vote units.
- Raw community choice remains one account/one vote. Binding durable units are the common proposal-age complement `1 - hype`, so time can mature consensus without changing the raw approval ratio.
- Added dynamic `/api/v1/community/monitor` and per-proposal tally evaluation; no background poller is required because hype is a pure function of proposal origin and evaluation time.
- Added persistent community user accounts, proposals, invitation windows and votes in a governance-specific checkpoint rather than the live show model.
- Added provider-neutral admin email delivery: local RFC-822 outbox for tests/development plus standard-library SMTP for real delivery.
- Vote invitation `sentAt` is stamped immediately before email delivery handoff, `expiresAt` is calculated at that moment, and both exact timestamps are embedded in the message. `deliveryAcceptedAt` is recorded separately. Opening/clicking the email never moves the deadline.
- Added one-time SHA-256-hashed vote credentials; hashes persist across restart but are redacted from API/admin responses.
- Proposal wording changes increment the proposal version and invalidate ballots issued for an older version.
- Added account-auth binding through trusted proxy headers/tokens; explicit `STAGEMESH_GOVERNANCE_TOKEN_ONLY=1` remains a weaker development mode rather than being misrepresented as forwarding-safe authentication.
- Added admin API fencing: localhost by default or `STAGEMESH_ADMIN_API_TOKEN` when remote administration is required.
- Admins may issue ballots and manage proposals but cannot mark a proposal adopted until deterministic community tally policy says it is binding-ready. Active emailed windows cannot be administratively closed, and adopted proposal text/change payloads become immutable.
- Added canonical proposal change payload/hash records and explicit `/apply` execution for ratified `community-governance-policy` and `technology-openness-policy` changes. Direct policy edits lock once the community process begins.
- Added a dedicated `/vote.html` email landing surface and vote-context endpoint.
- Added `community-governance` to the resource planner as background governance work that cannot interfere with live execution.
- Added community governance policy, account, proposal, invitation and tally JSON schemas.
- Advanced the public C ABI to 1.20 with `org.upp.core.community-governance/1`, `org.upp.core.hype-maturity/1` and `org.upp.core.vote-notification/1`.
- Added unit/API regressions for day-1/day-365 hype, zero hype vote weight, immutable email windows, account matching, version invalidation, restart-safe credentials, token-only development mode and adoption gating.
