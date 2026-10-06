# Recovered software backlog history (through Checkpoint 69)

This recovered document is historical. Current acceptance statuses are in
`backlog/StageMesh-Master-Backlog-Checkpoint-83.xlsx`; consolidation findings
are in `consolidation-checkpoint-84.md`. In particular, later hosted IPC and
native binder evidence supersedes historical statements below, but does not
prove full-engine integration or licensed plugin compatibility.

Updated 2026-09-14. Prioritized from explicit remaining work in the current source
documentation; this is not a fresh audit of every historical task. Physical
hardware qualification is deferred at the user's request, not marked complete.

## Completed latest

- **Checkpoint 68:** an installed service-identity device-permission qualifier now checks explicit non-symlink character-device nodes as the actual requested service user and reports read/write access without changing host permissions. This gives `PKG-034` a fail-closed clean-host tool while leaving real ALSA/MIDI/UWB permission evidence open.
- **Checkpoint 67:** every native Windows pipe instance now attests the kernel-applied security descriptor before client acceptance. The DACL must be protected/non-null and contain exactly SYSTEM plus configured explicit principals, with no extra/deny/unknown ACEs and exact access masks. This removes trust in requested SDDL alone; real Windows execution remains required.
- **Checkpoint 66:** the Windows UPPF adapter now has a real target-OS listener implementation using `CreateNamedPipeW` with a protected explicit-SID DACL. SYSTEM is always present, broad principals are rejected, Administrators are opt-in, native startup requires configured service/operator SIDs, and the connection reuses the existing bounded authenticated UPPF framing. Linux-side contract tests pass; real Windows DACL creation/denial/client-server execution remains open.
- **Checkpoint 65:** exact-build external qualification submissions can now be ingested as a status set. Evidence is re-hashed at intake, authenticated reviews are re-verified, and each task reports pending/awaiting-review/approved/rejected/needs-evidence/invalid without changing backlog state automatically.
- **Checkpoint 64:** external qualification results now require task-specific evidence artifacts, and an installed reviewer hashes the real evidence files, verifies exact plan/build/result binding and emits an owner-private HMAC-authenticated approve/reject/needs-evidence envelope. Approval is only eligible for backlog review; it never mutates backlog state automatically.
- **Checkpoint 63:** external qualification is now driven by an exact-build machine-readable plan covering witness, LAN, clean-host packaging, Windows, macOS, assistive technology, licensed plugins and stage hardware. Results must match the exact source/engine hashes, hashed runner identity and every required task claim before they can pass.
- **Checkpoint 62:** the real Chromium qualification now inspects the browser accessibility tree and enforces landmarks, names, roles, focusability, bounded BPM semantics and polite live regions. The reference passes with no unnamed interactive or ignored-focusable nodes; actual screen-reader/switch/voice interaction remains open.
- **Checkpoint 61:** installed isolated-rootfs packaging qualification now runs the real installer/reinstaller, systemd sysusers/tmpfiles provisioning, unit verification, state-preserving uninstall and explicit purge checks. It deliberately reports clean-host and hardware-permission qualification as false; those real-host gates remain open.
- **Checkpoint 60:** Windows/macOS plugin manifests now require platform-native launch attestations (Windows Authenticode publisher + file identity; macOS Team ID + code-directory hash), platform evidence is fail-closed, and non-Linux external launch refuses the old path-digest fallback. Real native binders and licensed product runs remain open.
- **Checkpoint 59:** local UPPF framing is now transport-neutral across stream/message transports and the Windows named-pipe adapter contract is fail-closed: StageMesh-scoped pipe names, bounded requests and mandatory positive ACL validation before accept. Real Windows DACL creation/inspection and client/server execution remain open.

- **Checkpoint 58:** physical audio state/activation fencing is now backend-neutral. Future WASAPI/CoreAudio execution will use the same active-state, post-start identity revalidation and stop-on-loss rules as ALSA, while null/bridge backends remain non-physical. The ALSA preflight boundary is explicit; real Windows/macOS preflight/configuration and stream adapters remain open.

- **Checkpoint 57:** shared audio/MIDI hotplug reconciliation is now backend-agnostic and fail-closed. Unsafe active audio stops regardless of backend; pinned MIDI identity cannot be overwritten by observation; exact strong identities can rebind across native endpoint-ID churn; duplicates are rejected; disconnect/identity-change detaches happen before rebind; MIDI scans are serialized and publish bounded hotplug evidence. Real Windows/macOS enumeration/change notifications and physical execution remain open.

- **Checkpoint 56:** cross-platform audio/MIDI identity now distinguishes persistence-grade WASAPI/CoreAudio/CoreMIDI identities from installation/snapshot evidence. Only hashed strong identities may auto-reconnect/rebind; raw or weak tokens fail closed. Actual Windows/macOS enumeration/hotplug and stream integration remain open.

- **Checkpoint 55:** Windows diagnostics now expose privacy-preserving AudioEndpoint snapshots plus signed installed MEDIA-driver evidence, and macOS diagnostics expose hashed CoreAudio device evidence without inventing package semantics. These adapters have fixture/integration coverage; real Windows/macOS execution and device qualification remain open.

- **Checkpoint 54:** real Chromium now executes the production operator assets at desktop/tablet/phone reference widths with keyboard workflow checks and zero horizontal overflow after fixing small-viewport grid shrink behavior. Assistive-technology and deployed browser/LAN qualification remain open.

- **Checkpoint 53:** an installed offline driver-catalog audit now reports review-due/stale/unreviewed/invalid records and days to expiry, making periodic re-review proactive without fetching or trusting new internet evidence automatically.

- **Checkpoint 52:** the reviewed driver catalog now adds Focusrite Scarlett Solo/2i2/4i4 4th Gen Windows x64 package metadata with exact USB IDs, current vendor release/download evidence and six-month review expiry. This remains package assistance only, not hardware qualification.

- **Checkpoint 51:** Linux external plugin adapters now hash an `O_NOFOLLOW` opened regular-file descriptor immediately before launch and execute through the inherited `/proc/self/fd` handle, closing manifest-path replacement between verification and execution. Windows/macOS launch binding and real plugin qualification remain open.

- **Checkpoint 50:** trusted auth-proxy identities can now mint short-lived HMAC-signed community sessions bound to a persisted per-account revocation generation. Session-only voting still requires that account's active invitation/current proposal version; magic links are no longer the production account credential.

- **Checkpoint 49:** community proposal versions, invitation windows and privacy-preserving opaque ballots now bind to the signed Public Record. Individual voter identity/choice is excluded; adoption records aggregate totals and exact evidence references, and missing evidence blocks binding until admin reconciliation.

- **Checkpoint 48:** strict independent-witness deployment mode now requires an explicit majority quorum, unique witness identities/failure domains/pairwise keyrings, signed response identity/domain facts and bounded clock skew. Linux packages a loopback-only witness service and a three-process reference drill that passes 3/3 acquire, 2/3 transfer/renewal after one loss, and denial at 1/3. The drill explicitly does **not** claim physical independence.

- **Checkpoint 47:** technology Standard/Core assessment now requires a verified signed Public Record conformance receipt. Fake/missing/stale references fail; grandfathered Standard recognition can survive ecosystem growth when the original evidence digest still matches, while new Core elevation requires a current-scale receipt.

- Astra checkpoint 44: native lighting output now supports explicitly armed unicast Art-Net or sACN/E1.31, with one selected protocol at a time, configurable E1.31 universe base and process-unique CID. Portable fixture/parameter intent can resolve through the committed `lighting.primary` venue patch into bounded DMX execution without rewriting show intent. Multicast/sync discovery and physical console/network qualification remain open.

- Astra checkpoint 43: reviewed driver-catalog package evidence now carries expiry, confidence and multi-source provenance; stale and legacy-unreviewed records cannot masquerade as current exact evidence. Windows/macOS endpoint adapters, broader catalog review and physical qualification remain open.

- Astra checkpoint 42: arbitrary-length arrangement and clip loops now wrap sample-exactly through producer/native boundaries without fixed-block tail silence. Audible real-output qualification remains separate.

- Astra checkpoint 41: finalized recordings and interrupted-recording recovery now fsync file bytes and the containing directory around non-replacing hard-link publication. A failed publication-directory sync rolls the target back and keeps the take retryable; post-publication cleanup sync failure is reported without demoting the durable target. Physical power-cut and audible interface qualification remain separate.

- Astra checkpoint 40: DAW render/import staging, media snapshots and isolated plugin scratch now share a versioned fsynced owner manifest binding exact process generation to exact filesystem device/inode identity. Legacy/malformed/replaced resources fail closed as unknown, cleanup rechecks identity immediately before deletion, and unclean-exit/fsync-failure regressions pass. Recording publication parent-directory durability and physical storage qualification remain separate.

- Astra checkpoint 39: Linux physical PCM execution now realizes the existing explicit conversion contract for `FLOAT_LE`, `S16_LE`, packed `S24_3LE` and `S32_LE`, plus mono and deterministic multichannel matrices. Float/device buffers are preallocated, conversion remains permission-fenced, and a live ALSA-null stdio exercise proved 4-channel integer playback/capture. Conversion quality on named hardware remains open.

- Astra checkpoint 38: repeatable HTTP controller workload/rate-policy qualification. Deterministic model admitted 400/400 representative controller requests while rejecting 802 abusive requests; live local-reference run passed 120/120 normal requests at 22.903 ms p95 and produced 33 explicit 429 throttles during a 320-request abusive burst. Physical controller timing and deployed LAN evidence remain separate.

- Astra checkpoint 37: known expensive HTTP maintenance/discovery/planning/storage/external operations now use non-blocking class and total admission budgets before body execution, preserving ordinary control capacity and reclaiming slots even after route failure. In-flight stateful work is never force-cancelled.

- Astra checkpoint 36: specialized admin-token and adapter-report allow/deny decisions now enter the same fail-closed durable authorization audit, while replication apply and planned-handoff peer readiness emit bounded machine-HMAC authorization evidence after cryptographic verification and before mutation. Human roles still cannot inherit these credentials.

- Astra checkpoint 35: private rotating HMAC keyrings for replication, witness quorum and planned handoff with HMAC-covered key IDs, per-operation snapshot pinning, explicit old/new overlap and no downgrade fallback. Real independent-witness/clock qualification remains open.

- Astra checkpoint 34: bounded segmented authorization-audit retention with a continuous hash chain, fsynced cryptographic retention anchor, ENOSPC-safe pruning order, crash-residue recovery and cached steady-state append head. Specialized admin/adapter/machine audit unification remains open.

- Astra checkpoint 33: opt-in strict `proxy-https` deployment profile plus packaged proxy contract and qualification helper. A live local reference TLS proxy passed certificate verification, TLS 1.3, HSTS/security headers and backend Host/Origin/token denial tests. Real venue-LAN proxy/certificate/IdP/firewall qualification remains open.

- Astra checkpoint 32: optional trusted-proxy per-user control roles separate performer/operator/authority privileges, with per-request rotation and a durable fail-closed hash-linked actor/action authorization audit. Existing machine/admin/adapter credential boundaries remain separate.

- Astra checkpoint 31: file-backed SSE credentials are rechecked during idle waits and before delivery; revoked/malformed credentials close streams and release slots. Already-sent data and in-flight backend mutations are not revoked.

- Astra checkpoint 30: private bounded HTTP credential-file snapshots support atomic rotation for subsequent requests without runtime restart. In-flight/SSE revocation and witness/replication rotation remain open.

- Astra checkpoint 29: optional exact-route monitoring credential for health/native/node GETs; all other access denied, including hardware mutations. Per-user control roles remain open.

- Astra checkpoint 28: authenticated remote/proxy health and strict command identity handling, with a no-mutation API regression.

- Astra checkpoint 27: proxy mode removes implicit localhost admin/adapter privileges; scheme-aware origin validation, strict authority syntax, invalid-token denial and untruncated identity validation. Deployment TLS, fine-grained roles and secret lifecycle remain open.

- Astra checkpoint 26: bounded per-address and aggregate request-rate buckets, 429 retry responses and forwarded-address bypass regression. Rate-policy workload qualification and proxy/TLS/authorization review remain open.

- Astra checkpoint 25: monotonic total header/body receive deadline with real trickle-traffic tests. Rate bounds, proxy/TLS trust and authorization remain open under priority 2.

- Astra checkpoint 24: separate eight-stream SSE admission within the 32-worker pool, retry responses, unconditional slot release and saturated-stream/control coexistence regression. Total deadlines and request-rate bounds remain open.

- Astra checkpoint 23: pre-thread connection cap and socket inactivity timeout, with admission, failure-reclamation and stalled-header tests. Total deadlines, SSE budgets and rate limits remain open under priority 2.

- Astra checkpoint 22: strict request framing and connection-close-on-error, with raw-socket pipeline regressions. Network security priority 2 remains open for proxy/TLS trust, resource bounds and authorization review.

- USB discovery/driver diagnosis UI, API and CLI with OS-specific online lookup links.
- Explicit Linux audio constraint preflight with distinct unavailable/busy/unsupported results.
- Request-bound witness response authentication; 334 Python tests passed without skips.
- Shared DAW media-snapshot crash cleanup and configurable cross-process quota.
- Exact ALSA constraint preflight enforced immediately before physical activation.
- Serial-backed MIDI reconnect identity with conservative explicit rebind for topology-only devices.
- Driver evidence classification and exact curated catalog matching foundation.
- Explicit audio stream recovery with configured native parameter reporting.
- External plugin adapter OS/architecture/protocol/digest compatibility gate.
- HTTP Host/origin/JSON-content boundary and authenticated remote API access.
- Serial-backed Linux audio identity and bounded continuous hotplug observation.
- **Checkpoint 45:** generalized authority leasing now supports typed patch/department/runtime-resource scopes, exact-resource precedence, venue-vs-runtime lifecycle contexts, durable grant/revoke audit metadata and fail-closed clearance on authority loss.
- **Checkpoint 46:** adaptation and operational-authority receipts now enter a signed append-only Public Record; separately authenticated external witnesses can attest exact record hashes into a second hash-linked ledger with explicit quorum coverage.

## Active priorities

| Priority | Job | Completion evidence |
| --- | --- | --- |
| 1 | Authorized recovery of persistently fenced nodes | **Software protocol + strict independent-witness deployment mode complete:** exact transfer/fence identity is authenticated by quorum, recovery remains standby/disarmed, and checkpoint 48 enforces unique witness identities/failure domains/pairwise credentials plus signed clock-skew bounds. Remaining: the real multi-host recovery/failure-domain drill on independently hosted witnesses |
| 2 | Network security review before LAN operation | **Software hardening through checkpoint 48:** prior HTTP/auth/resource controls remain complete; strict witness topology now fences witness identity/domain, per-endpoint credentials and clock skew. Remaining: real deployed LAN proxy/certificate/IdP/firewall qualification and measured multi-host witness clock/network/failure-domain evidence |
| 3 | DAW durability and recovery | **Checkpoints 40–42 software durability/playback complete:** temporary resources use fsynced inode-bound owner manifests, recording/recovery publication fsyncs the parent directory around hard-link publication and cleanup, and arbitrary-length arrangement/clip loops wrap sample-exactly in software without block-tail silence. Remaining: physical storage/power-cut and audible interface/loop qualification |
| 4 | Audio negotiation integration | **Linux execution + shared backend-neutral fencing complete through checkpoint 58:** exact ALSA preflight/conversion remains complete, and the common runtime now recognizes any explicit physical backend, revalidates identity after start and stops on loss while keeping null execution non-physical. Remaining: Windows/macOS exact preflight/configuration, physical stream adapters and conversion-quality measurement |
| 5 | Persistent device identity and hotplug | **Shared lifecycle complete through checkpoint 57:** Linux retains serial-backed recovery; cross-platform audio stops unsafe active streams without backend assumptions; strong MIDI identities can rebind across native-ID churn while duplicates/identity replacement fail closed; MIDI scans are serialized and expose hotplug evidence. Remaining: actual Windows/macOS enumeration/change notifications, physical audio/MIDI stream integration and qualification |
| 6 | Driver compatibility assistance | **Software evidence adapters complete through checkpoint 55:** reviewed package metadata remains separate from Windows installed-driver evidence; Windows AudioEndpoint/PnP identifiers are privacy-preserving, while macOS CoreAudio evidence avoids Windows-style package claims. Remaining: actual Windows/macOS host runs, broader vendor/model reviews and physical qualification |
| 7 | Live audio feature completion | **Software polyphonic streaming complete:** bank triggers prebuffer and feed 16 independent native voices from service threads, with exact-generation cancellation/reclamation, bounded backpressure, shutdown cleanup and native starvation/stale/discontinuity evidence. No disk I/O occurs in the callback. Remaining: physical/audible soak and real-plugin qualification |
| 8 | Browser workflow acceptance | **Rendered/accessibility-reference path complete through checkpoint 62:** real Chromium desktop/tablet/phone rendering, keyboard workflow, zero-overflow responsive checks and AX-tree landmark/name/role/focus/live-region semantics pass. Remaining: actual screen-reader/switch/voice assistive-technology exercise and deployed browser-to-LAN/TLS/IdP qualification; managed Chromium still uses the real-handler fetch bridge |
| 9 | Packaging and release readiness | **Reference packaging qualification advanced through checkpoint 61 and cross-platform desktop candidate binding:** staged Linux install/reinstall/uninstall/purge, real sysusers/tmpfiles provisioning, unit verification, per-platform desktop manifests and one exact-candidate index pass. Every desktop bundle includes fail-closed Windows/macOS/Linux clean-host collectors and a reviewer that binds all five installer tracks to that candidate. Remaining: target-host execution and owner review, Linux service/device permissions, signing, accessibility and owner license decision |
| 10 | Cross-platform and plugin coverage | **Shared portability/security contracts advanced through checkpoint 67:** Linux verified plugin launch is bound to the exact inode; Windows/macOS manifests require native signing/file-identity attestations and refuse unbound launch; Windows named-pipe UPPF now has bounded framing, an explicit-SID protected `CreateNamedPipeW` listener and pre-accept kernel-DACL attestation. Remaining: real Windows/macOS plugin launch binders, Windows DACL/client denial execution, actual platform runs, licensed plugin fixtures and product matrices |
| 11 | Portable lighting execution | **Checkpoint 44 software path complete:** bounded native DMX state can transmit through explicitly armed unicast Art-Net or sACN, and committed venue patches can resolve semantic fixture/parameter intent to venue-local universe/channel/value coordinates. Remaining: multicast/synchronization features only if required by product scope, real console/network interoperability and stage timing qualification |
| 12 | Operational authority and Public Record | **Checkpoints 45–50 software protocol complete:** typed operational leases, signed adaptation/authority records, external exact-hash attestations, signed technology conformance receipts, strict independent-witness topology, privacy-preserving community-governance Public Record binding and trusted-proxy account sessions are implemented. Remaining: physical independent-witness qualification and production IdP/LAN deployment evidence |

## Deferred equipment-dependent work

Audio latency/dropout/soak tests; physical recording and audible loop correctness;
controller timing/reconnect measurements; LE Audio/UWB RF and clock validation;
independent multi-host timing/failover and witness failure-domain measurements. These do not block software
development but still block claims of stage-qualified or universal hardware support.

## Source notes

See `witness-response-authentication.md`, `independent-witness-deployment.md`, `http-api-security.md`, `planned-handoff-peer-readiness.md`,
`audio-preflight.md`, `hardware-pnp.md`, `plugin-adapter-compatibility.md` and
`developer-alpha-release.md`.
Historical release notes contain superseded items: Core 5.10.5 completed the fresh
CMake/CTest and ASan/UBSan gates, and partial WAV recording recovery is implemented.
Those are not listed again as unimplemented features. Physical timing and browser
workflow qualification are separate from those software checks.
