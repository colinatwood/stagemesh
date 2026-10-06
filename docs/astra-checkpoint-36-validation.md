# Astra checkpoint 36 validation

Updated 2026-09-13. This checkpoint unifies durable authorization evidence for the existing specialized admin, adapter-report and selected machine-HMAC boundaries without changing which credential grants each privilege.

## Scope

- Admin-token and adapter-report allow/deny checks append bounded `specialized-authorization` events before protected route execution.
- Human `admin` role does not substitute for the separate adapter/admin machine credentials.
- Replication apply and planned-handoff peer-readiness emit machine-HMAC decisions after cryptographic verification and before authenticated mutation.
- Successful machine records contain only bounded authenticated actor/key IDs; denied verification does not trust or copy unverified identity metadata.
- Credential values, raw request targets, query strings and request bodies are excluded from audit records.
- Durable audit failure blocks specialized HTTP mutation.
- Direct private helper calls without a real HTTP request context remain side-effect free for compatibility.

## Focused regression

`python3 -m unittest -v tests.test_specialized_authorization_audit tests.test_proxy_privileges tests.test_http_authorization`

Result: 22 tests passed after the synthetic-handler compatibility patch. Six tests are new for checkpoint 36.

## Release validation

A fresh Release native build with `STAGEMESH_RT_QUALIFICATION=ON` passed both CTest targets (`stagemesh_native_tests` and `stagemesh_current_abi_smoke`). The combined release Python suite then ran against that fresh engine with system Python first on `PATH`: **506 tests passed with zero skips**. The external adapter fixture uses `/usr/bin/env python3`; placing the preinstalled virtualenv first on `PATH` can exceed its existing 250 ms startup watchdog in this loaded environment, so validation pinned `/usr/bin` first without changing production watchdog values.

Additional gates passed:

- `scripts/automation-performance.py --json`: passed, exact prepared-read work bound and probe equivalence satisfied.
- `frontend/openapi.json` parsed successfully.
- All **117** public JSON schemas parsed successfully.
- All **7** frontend JavaScript files passed `node --check`.
- Native CTest: **2/2** passed.

## Remaining boundary

This checkpoint is software authorization/audit evidence only. It does not qualify controller workload, filesystem latency, deployed proxy/IdP/firewall behavior, independent witness/clock assumptions, or hardware/stage readiness. The next software security item is backend operation-cost bounds, followed by controller workload/rate-policy qualification.
