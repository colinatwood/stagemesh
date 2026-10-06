# Astra checkpoint 32 validation

481 Python tests passed on 2026-09-13. Eleven new authorization tests cover
private role-policy loading, invalid permissions/schema/roles, performer player
assignment, operator-versus-authority separation, unknown-user denial, specialized
machine-route exemption, real HTTP allow/deny behavior, same-connection policy
rotation, durable hash-linked audit records and tamper detection.

The optional `STAGEMESH_HTTP_AUTHORIZATION_FILE` is re-read per role-controlled
request and maps exact trusted-proxy user identities to fixed roles. `performer`
can mutate only assigned player monitor/MIDI/notation routes; `operator` controls
ordinary API mutations; `authority` controls witness/node/failover/planned-handoff
and venue-authority mutations; `admin` grants all ordinary role-controlled
mutations. `observer` grants no mutation. Existing admin, adapter-report,
community-vote and machine replication/peer-ready authorization remain separate
and are not silently widened by these roles.

Every role-controlled allow/deny decision is appended before route/body execution
to a separate fsynced SHA-256 hash-linked `authorization-audit.jsonl`. Records are
bounded metadata only: actor, roles, method, normalized action, optional player
target, decision and reason; request bodies, credentials, raw URLs and query strings
are not copied. If the audit write fails, a role-controlled mutation fails closed.
The admin-protected `/api/v1/security/authorization-audit` endpoint verifies only
the record count/head/hash chain, not the individual actor history.

Native source was unchanged. A fresh CMake build and both CTest targets passed in
this environment. The full Python suite was run with `/usr/bin/python3` and
`/usr/bin` first in `PATH`; the tool environment's virtualenv Python takes longer
than the existing 250 ms plugin-host startup watchdog and otherwise creates
environment-only watchdog timeouts. No watchdog threshold was changed.

No live authorization file, proxy, credentials, service deployment or physical
hardware was changed. Audit retention/rotation, deployed TLS/proxy qualification,
specialized admin/adapter authorization-audit unification, real controller workload
qualification and witness shared-key/clock review remain open.
