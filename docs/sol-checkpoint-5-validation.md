# Sol backlog checkpoint 5 validation

Validated 2026-09-11 in the available Linux development environment.

## Completed in this checkpoint

- DNS-rebinding-resistant Host allowlisting on every HTTP request.
- Same-origin enforcement for browser requests with an explicit origin allowlist.
- JSON-only API mutations.
- Dedicated token authentication for all non-loopback API reads and mutations.
- Optional token enforcement for loopback reverse-proxy deployments.
- Refusal to bind outside loopback without an allowed-host list and API token.
- Frame, browser-permission and content-security response headers.
- Deployment limits and remaining security-review documentation.

## Executed checks

- 362 Python unit/integration tests passed without skips when pointed at the fresh
  qualification-enabled native engine.
- `stagemesh_native_tests` and `stagemesh_current_abi_smoke` passed directly.
- All 108 JSON schema files parsed successfully.
- `frontend/app.js` passed the runtime Node syntax check.

The release wrapper correctly reported that CMake and CTest were unavailable in
this session. Its generated native test executables were run directly, so this is
not represented as a CTest runner pass.

## Remaining limits

The bridge is not declared safe for public-Internet exposure. Reverse-proxy/TLS
trust, secret provisioning and rotation, rate limiting, role authorization, audit
retention, denial-of-service analysis and distributed witness trust remain for
Astra-level threat-model review. No physical hardware, real plugin products,
cross-platform host, clean installer host or reachable managed-browser loopback was
available for qualification.
