# HTTP API security boundary

The bundled HTTP server remains a development and single-host control bridge. It
binds to loopback by default. Do not expose it directly to an untrusted network or
the public internet.

Every request now validates its `Host` header against loopback names plus the
explicit comma-separated `STAGEFORGE_ALLOWED_HOSTS` setting. This blocks a browser
from using an attacker-controlled DNS name to reach a loopback service. Browser
requests carrying `Origin` must be same-origin unless their exact origin is listed
in `STAGEFORGE_ALLOWED_ORIGINS`; opaque (`null`) and foreign origins are rejected.
API mutations also require `Content-Type: application/json`.

Any `/api/` request received from a non-loopback client requires
`STAGEFORGE_API_TOKEN` and the same value in `X-StageForge-API-Token`. The token is
accepted only as a header and compared without ordinary string equality. Existing
admin, trusted-auth-proxy, adapter-report, replication and witness credentials keep
their narrower roles; the API token does not replace them.

Set `STAGEFORGE_REQUIRE_API_TOKEN=1` when a reverse proxy connects from loopback;
otherwise loopback remains the trusted local-development boundary. The bundled
browser UI does not collect or retain this token, so authenticated remote access is
currently intended for a reviewed proxy or API client, not a production browser
login flow.

Example private-LAN configuration:

```bash
export STAGEFORGE_ALLOWED_HOSTS=stage-console.internal
export STAGEFORGE_ALLOWED_ORIGINS=https://stage-console.internal
export STAGEFORGE_API_TOKEN='generate-a-long-random-secret'
python3 backend/dev_server.py --host 10.0.0.20 --port 8787
```

Non-loopback startup is refused unless both the allowed-host list and API token are
configured. Terminate HTTPS at a reviewed reverse proxy, keep the bridge on a protected
interface, restrict ingress by firewall and rotate all secrets through the service
manager. Static frontend files are not granted API authority: remote API requests
still need the token.

Responses add frame denial, restrictive content security policy, no-sniff,
same-origin resource policy, no-referrer and a disabled browser-permissions policy.

## Remaining review

### Astra checkpoint 38: controller workload and rate-policy reference

`scripts/stageforge-http-workload.py --json` now provides repeatable software evidence for the HTTP admission policy. Its deterministic model runs four independent 20 rps controller peers beside one 300 rps abusive peer for five seconds using the actual `RequestRateLimiter` policy. The checkpoint reference admitted 400/400 controller requests and rejected 802 abusive requests, demonstrating that the default 100 rps per-peer cap prevents one peer from consuming the 200 rps aggregate refill needed by the 80 rps controller workload.

The same tool launches the real StageForge loopback bridge and runs a mixed normal burst plus a separate abusive burst. The checkpoint reference passed 120/120 normal requests with 22.903 ms p95 latency. A 320-request abusive burst produced 33 explicit `429` responses and no unexpected status codes. The measured timing is host/load dependent and is preserved as reference evidence rather than a universal performance promise.

The report always marks `physicalControllerQualified=false` and `deployedLanQualified=false`. It does not replace end-to-end controller timing/reconnect measurement, proxy/IdP/firewall deployment qualification, or named-hardware evidence.

### Astra checkpoint 37: bounded expensive operation admission

Known control-plane operations that can perform filesystem, device discovery, compatibility/venue planning, media storage or external delivery work now enter explicit non-blocking admission classes. The default bridge permits at most four expensive operations in flight across the existing 32-worker pool, with class caps of maintenance 1, discovery 2, planning 3, storage 2 and external 2. Ordinary health and show-control requests do not consume these cost slots.

Admission happens only after the ordinary HTTP/auth boundary and role authorization but before request-body execution. Saturated expensive work returns `503` with `Retry-After: 1` and closes the unread request. Slots are released in the per-request `finally` path, including when route code raises. StageForge deliberately does not impose a wall-clock cancellation timer on an already-started mutation: abruptly killing stateful persistence or planning work would create a different correctness problem. Bounding admission and request size is the safe control-plane policy for this bridge.

The initial cost registry covers checkpoints/audit/public-record maintenance; audio/MIDI/hardware discovery; show/venue/technology/interoperability planning; DAW media ingest/verify/render/autosave; temporary-resource cleanup; and community vote-email delivery. New expensive routes must be classified rather than silently relying on the general worker pool. Real controller workload and filesystem/device latency remain deployment qualification work.

### Astra checkpoint 36: specialized authorization audit unification

The separate admin-token and adapter-report credential checks remain separate privilege boundaries from trusted-proxy human roles, but each successful or denied check now appends a bounded `specialized-authorization` decision to the same durable authorization-audit chain before protected route execution. The record contains the credential class, normalized action, allow/deny result and bounded fixed reason; it never stores the credential, request body, raw request target or query string. If the audit cannot be persisted, an otherwise valid admin/adapter mutation fails closed with service-unavailable status.

Machine-authenticated replication apply and planned-handoff peer-readiness checks use a post-verification/pre-mutation hook. A failed HMAC produces a deny event with no untrusted actor/key attribution. A successful verification may record only the bounded authenticated source node and key ID already covered by the HMAC. This does not make a human `admin` role equivalent to a machine, admin-token or adapter credential, and it does not change quorum/authority semantics.

Private authorization helpers used without an actual HTTP request context do not emit synthetic request records. Production HTTP dispatch always supplies the request method/path, preserving fail-closed durable evidence on real specialized requests while keeping focused helper tests and non-HTTP compatibility seams side-effect free. Community-vote authentication remains separate and is not widened by this checkpoint.

### Astra checkpoint 34: bounded authorization-audit retention

The checkpoint-32 role-decision audit now rotates into immutable numbered segments before the active file crosses `STAGEFORGE_AUTH_AUDIT_ROTATE_BYTES` (4 MiB default, 64 KiB–256 MiB accepted). `STAGEFORGE_AUTH_AUDIT_RETAIN_SEGMENTS` bounds rotated history (8 default, 1–256). The active file and every segment continue the same SHA-256 chain.

Pruning commits and fsyncs `authorization-audit-retention.json` before deleting old segments. The anchor records the exact pruned-prefix head, next retained sequence and pruned record/segment counts. Failure to publish that anchor prunes nothing. A crash after anchor publication may leave an already-pruned segment on disk; verification reports the residue but does not reintroduce it into the retained chain. Steady-state decision appends cache the verified head and check file identities, so control traffic does not rescan retained audit history on every mutation.

`GET /api/v1/security/authorization-audit` still requires admin authorization and returns verification/retention metadata only, never actor history. Real filesystem latency and controller workload remain qualification work.

### Astra checkpoint 33: strict HTTPS reverse-proxy deployment profile

Set `STAGEFORGE_DEPLOYMENT_PROFILE=proxy-https` only for a reviewed remote deployment. In this profile StageForge refuses to start unless its backend bind is loopback, private credential-file API authentication is active, allowed hosts are explicit non-loopback hostnames, allowed browser origins are exact HTTPS origins on those hosts, and the per-user authorization policy plus trusted auth-proxy credential are available. The profile is intentionally opt-in; local development behavior is unchanged when it is unset.

StageForge still does not trust `X-Forwarded-For` or other forwarded peer identity. The edge proxy owns TLS, firewall policy and human authentication, strips client-supplied internal StageForge privilege headers, then injects reviewed identity/internal credentials. See `packaging/reverse-proxy/README.md` and `packaging/stagemesh-proxy.env.example`. The optional systemd `/etc/stageforge/stageforge.env` file is intended for non-secret settings and secret-file paths, not raw credentials.

Run `stageforge-http-qualify.py --backend-url http://127.0.0.1:8765 --edge-url https://stage-console.internal` on the deployment host. The backend probe expects success only for the configured Host/Origin/control credential and explicit 403 denial for bad credential, hostile Host and hostile Origin. The edge probe performs ordinary CA/hostname verification, requires TLS 1.2/1.3, HSTS and StageForge browser security headers. Passing the helper is deployment-security evidence, not a substitute for real controller-load, hardware or venue qualification.

### Astra checkpoint 32: per-user control roles and durable authorization audit

`STAGEFORGE_HTTP_AUTHORIZATION_FILE` optionally enables exact per-user control
authorization behind the existing trusted auth-proxy identity boundary. The JSON
file must be an absolute-path regular file owned by the service effective UID,
private to that UID, non-symlink and no larger than 64 KiB. Duplicate JSON keys,
unknown fields, unknown roles, duplicate roles/player assignments and malformed
identities fail closed. It is re-read once per role-controlled request, so an atomic
replacement changes subsequent requests on the same keep-alive connection without
restarting the bridge.

Example:

```json
{
  "version": 1,
  "users": {
    "alex": {"roles": ["performer"], "players": ["alex"]},
    "foh-operator": {"roles": ["operator", "authority"]},
    "read-only-reviewer": {"roles": ["observer"]}
  }
}
```

A role-controlled mutation still passes the ordinary HTTP/API-token boundary first.
The user identity must then be supplied as `X-StageForge-Authenticated-User` and be
authenticated by the distinct `X-StageForge-Auth-Proxy-Token`. The fixed roles are:

- `observer`: no API mutation authority; reads remain governed by the ordinary API boundary.
- `performer`: only assigned player monitor, MIDI-input and notation mutations.
- `operator`: ordinary non-authority API control mutations, including show/audio/lighting/DAW work.
- `authority`: witness recovery, node/failover authority changes, planned handoff control and Venue Patch authority leases.
- `admin`: all ordinary role-controlled mutations. It does **not** replace the separate admin token on routes that already require one.

Roles are additive. `authority` does not imply `operator`, so a user that needs both
must be assigned both. Machine replication apply/peer-ready, execution-adapter
reports, community voting and routes already protected by the separate admin token
retain those existing authorization mechanisms and are not converted into user-role
requests. This prevents human RBAC from accidentally breaking or widening machine
authority.

Every role-controlled allow or deny decision is durably appended **before request
body or route execution** to `authorization-audit.jsonl` under the runtime data
directory. The file has its own fsynced SHA-256 hash chain. Records contain only a
bounded trusted actor identity, fixed roles, HTTP method, normalized action, optional
player target, allow/deny result and fixed reason. Credentials, body data, raw paths
and query strings are not copied into the audit. A failed audit append fails the
role-controlled mutation closed with service-unavailable status.

`GET /api/v1/security/authorization-audit` requires the existing admin authorization
boundary and returns only hash-chain verification/count/head metadata. It does not
return actor history. Audit retention/rotation is implemented by checkpoint 34, and specialized
admin/adapter/machine authorization records are unified by checkpoint 36. Export or
external witnessing remains future work. Because each control-plane decision is
fsynced on the HTTP thread, real controller workload and disk-cost qualification are
still required before LAN release. No real-time audio/MIDI/lighting callback performs
this I/O.

### Astra checkpoint 31: event-stream credential revocation

Open SSE streams re-read their configured HTTP credential file before waiting,
after each event wait and before each event write. Idle waits are bounded to one
second and send keepalive comments while authorized. Rotation removing the stream's
credential, malformed files or missing files cause closure and stream-slot release.
No second HTTP status is written after streaming headers. Events fetched during a
credential change are checked before delivery. An unchanged control credential
continues to authorize its stream even if other roles rotate.

This supersedes checkpoint 30's open-SSE limitation for file-backed credentials.
It is not instantaneous revocation: scheduling, credential reads and an already
in-progress socket write can delay closure; bytes already sent cannot be recalled.
The existing ten-second socket inactivity limit still applies. Environment-only
streams retain their pinned environment snapshot. Other in-flight backend work
is not canceled. Per-user human control roles and their durable decision audit were
open at checkpoint 31 and are addressed by checkpoint 32 above.

### Astra checkpoint 30: private credential-file rotation

Optionally set STAGEFORGE_HTTP_CREDENTIAL_FILE to an absolute path in a trusted,
service-owned directory. The JSON object uses the existing environment key names:
STAGEFORGE_API_TOKEN (required), STAGEFORGE_MONITOR_API_TOKEN,
STAGEFORGE_ADMIN_API_TOKEN, STAGEFORGE_AUTH_PROXY_TOKEN and
STAGEFORGE_ADAPTER_REPORT_TOKEN (optional). No other keys are accepted.
Tokens must be distinct printable non-space ASCII strings of 32–512 characters;
operators must generate cryptographically random secrets rather than passwords.

The Linux file must be regular, owned by the service effective UID, private to its
owner (for example mode 0600), non-symlink, and at most 16 KiB. Duplicate JSON keys,
invalid structure and observable changes while reading are rejected. Keep parent
directories trusted. File mode forces API authentication, including localhost;
omitted role keys remove those privileges rather than falling back to environment.
The file replaces only HTTP bridge credentials, not witness/replication secrets.

For rotation, stage a complete private file in the same directory and atomically
rename it over the configured path. Each guarded HTTP request reads one snapshot
shared by all its credential checks. Subsequent requests—including keep-alive
requests—use the replacement. Missing or invalid files deny access with a generic
error; old credentials are not cached across requests. Restore a valid private file
to recover. Startup also rejects invalid configured files.

Already-authorized requests and open SSE streams retain their original authority;
this is next-request credential rotation, not immediate session revocation. It
does not restart or arm audio. No file was provisioned by this checkpoint. Full
session revocation, durable authorization audit and deployed TLS remain open.

### Astra checkpoint 29: scoped monitoring credential

Optionally configure STAGEFORGE_MONITOR_API_TOKEN, distinct from STAGEFORGE_API_TOKEN.
Send it in X-StageForge-API-Token. It authorizes GET only on /healthz,
/api/v1/native and /api/v1/node. Every other path/method is denied, including
static content, show state, replication exports, mutations and future routes.
This is intentional exact allowlisting, not a general read-only account.
Monitoring exposes detailed operational status; distribute this secret accordingly.

Recognized monitoring credentials remain constrained even on loopback. Ordinary
uncredentialed localhost access remains the trusted development mode; use
STAGEFORGE_REQUIRE_API_TOKEN=1 for a proxy boundary. Identical monitoring/control
credentials fail closed. The monitor credential does not satisfy separate admin,
adapter or proxy identity credentials. Startup still requires a control credential
and host allowlist for non-loopback binding; monitor-only network startup is not
implemented. No token is provisioned or returned by the application.

Per-user control roles, credential rotation/revocation, TLS deployment and durable
actor/action auditing remain open. This monitor scope does not qualify LAN release.

### Astra checkpoint 28: health and command identity boundaries

The detailed /healthz response now requires the same API credential as /api/
for remote clients and token-required proxy mode. Direct localhost development
probes remain available. Configure protected health probes with the API header;
there is no separate public detailed-health exception.

X-StageForge-Command-Id values longer than 128 characters after trimming are
rejected rather than truncated. Duplicate command-ID headers are rejected before
routing. Valid IDs retain existing deduplication semantics. This prevents two long
IDs with the same prefix from silently sharing an idempotency identity. Routes
without the existing mutation/deduplication wrapper do not gain deduplication.

### Astra checkpoint 27: proxy privilege separation and credentials

STAGEFORGE_REQUIRE_API_TOKEN now also disables localhost privilege exemptions
for admin operations and adapter reports. Configure their separate credentials;
the general API token grants neither role. Direct local-development behavior
remains available only with that mode disabled. Forwarded headers grant no role.

The plain HTTP bridge accepts same-origin HTTP requests by host and port. HTTPS
browser origins must be explicitly listed in STAGEFORGE_ALLOWED_ORIGINS for a TLS
proxy. Host and Origin reject URL credentials, paths, query and fragment components.
Token comparison rejects non-ASCII credentials instead of raising TypeError.
Duplicate Origin, Content-Type, API/admin/adapter credentials and proxy identity
headers are rejected before routing to prevent first-value/last-value ambiguity.
Proxy user identities longer than 128 characters are rejected rather than silently
truncated to a potentially different account identity.

These changes do not implement TLS, browser login or fine-grained show-control
roles. A proxy must strip user-supplied identity/privilege headers and inject only
credentials justified by its authenticated authorization policy. Do not inject an
admin token into all proxied requests. Deployment and credential rotation remain
unqualified; the shared general API token still confers broad control access.

Access logs now emit only a bounded method label and response status. They never
include URLs, query strings, peer addresses or credential headers. Base HTTP
diagnostics omit interpolated request material, including malformed request lines.
This prevents invitation-token leakage and log-line injection at the cost of
less request-level diagnostic detail. It is not an authorization audit ledger:
authenticated actor/action attribution, durable retention and rotation remain open.

### Astra checkpoint 26: request-rate admission

The CLI server applies token buckets after framing validation and before routing:
100 requests/second per direct socket address (burst 200), and 200/second total
(burst 400). Static requests, API requests and SSE establishment count; ongoing
SSE events do not. Over-budget requests receive 429, Retry-After: 2 and connection
close before body reads or route mutation. Forwarded headers never select identity.
Proxied clients therefore share their proxy's budget until a reviewed trust design
exists. Loopback clients are also limited.

At most 1,024 identities are retained. When full, only fully refilled buckets may
be forgotten; otherwise new identities are rejected. Updates are locked and use
monotonic time. Restart clears in-memory limits. These conservative software
defaults have not been qualified against real control workloads. Admission does
not bound backend operation cost or guarantee availability against distributed
traffic. Proxy/TLS, authorization, secret lifecycle and audit retention remain open.

### Astra checkpoint 25: total request receive deadline

The CLI bridge applies a monotonic 15-second budget to each request's headers and
JSON body together, starting before the request line (including keep-alive idle
time). Every underlying socket read uses the smaller of the remaining budget and
the ten-second inactivity timeout. Trickle traffic cannot renew this budget.
Completion is checked before route work; response writes restore the inactivity
timeout. SSE streaming is not limited to 15 seconds. Expired reads close the
connection without promising an HTTP error response. Generic server embeddings
do not install this reader. This bounds receiving, not backend execution time.
Per-client rate limiting, proxy/TLS trust and authorization remain open.

### Astra checkpoint 24: separate event-stream admission

The CLI server limits active SSE streams to eight of its 32 worker connections.
Excess streams receive JSON 503, Retry-After: 5 and Connection: close. The stream
slot is released even when header writes or streaming fail. A completed SSE
connection closes rather than resuming HTTP parsing after an unframed response.
Custom smaller servers clamp the stream allowance below the connection limit.
Generic ThreadingHTTPServer embeddings do not implement this admission policy.

The integration test holds the stream pool full and verifies both rejection of
another stream and successful ordinary control traffic. This prevents streams
alone from exhausting workers; it is not reserved priority scheduling or protection
against a flood of ordinary connections. Total request deadlines, per-client rate
limits and proxy/TLS/authorization review remain open.

### Astra checkpoint 23: connection admission and idle I/O

The CLI bridge uses StageForgeHTTPServer with at most 32 accepted worker
connections. Admission occurs before thread creation. Excess connections are
closed without a response, avoiding a blocking write in the accept loop.
Slots are returned after worker completion or thread-start failure. Sockets have
a ten-second inactivity timeout for reads/writes; stalled SSE writes also exit.
This is not a total request deadline: continuously trickled bytes can retain a
slot. SSE currently shares the same pool, so dedicated stream limits, reserved
control capacity, total header/body deadlines and per-client rate limits remain
required before LAN qualification. Idle SSE waits are application waits and do
not consume the socket inactivity timeout.

### Astra checkpoint 22: request framing

The bridge now rejects duplicate/missing Host headers, duplicate or non-decimal
Content-Length, length tokens longer than ten digits, any Transfer-Encoding,
and nonempty GET bodies before routing. Expect: 100-continue receives 417 without
an interim response. Clients must send fixed-length JSON bodies, not chunked bodies.
All JSON error responses close the connection, preventing unread rejected body
bytes from being interpreted as another request. Truncated JSON bodies fail before
mutation. Valid fixed-length requests and GET keep-alive pipelines remain supported.

Raw-socket regression tests cover these boundaries. This is not a complete request
smuggling or denial-of-service qualification: proxy parser agreement, connection
admission limits, slow-client deadlines and SSE resource budgets remain open.

This increment is not a complete production threat model. Astra review remains
appropriate for reverse-proxy trust, TLS termination, secret provisioning and
rotation, rate limiting, audit retention, role/capability authorization, browser
session UX and denial-of-service bounds. The shared witness/replication-key trust
and clock assumptions also remain separate distributed-system review items.
