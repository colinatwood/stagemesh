# Astra checkpoint 29 validation

460 Python tests passed on 2026-09-13. Five new tests cover exact monitoring-route
allowlisting, remote/local denial of mutations and unlisted reads, control-token
compatibility, secret-overlap rejection and real HTTP authorization before body read.
The HTTP test substitutes health output but uses the actual handler and boundary.

Optional STAGEMESH_MONITOR_API_TOKEN grants GET /healthz, /api/v1/native and
/api/v1/node only. No secret was provisioned. No deployment or native source
changes; no fresh native build or sanitizer claim. CMake/CTest prerequisites remain
unavailable. Detailed monitoring status is still confidential operational data.

Next: per-user control roles, secret lifecycle and durable actor/action auditing.
Deployed TLS/proxy, real workload policy and hardware qualification remain open.
