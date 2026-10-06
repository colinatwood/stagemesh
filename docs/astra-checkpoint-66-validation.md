# Astra checkpoint 66 validation — protected Windows named-pipe DACL runtime foundation

Checkpoint 66 advances `IPC-033` from a transport/ACL-validation contract to an actual target-Windows listener implementation. It still does **not** claim that the listener has executed on Windows.

## Native Windows listener

`backend/windows_named_pipe.py` adds a stdlib-only Win32 backend around `CreateNamedPipeW`, `ConnectNamedPipe`, `ReadFile` and `WriteFile`. It preserves checkpoint 59's exact bounded length-prefixed UPPF message bytes and authenticated session/capability/HMAC handling.

The pipe DACL is protected (`D:P`) and contains SYSTEM plus explicit configured SID strings. StageMesh rejects broad symbolic principals such as Everyone, Authenticated Users and Builtin Users. Builtin Administrators is not granted by default and must be opted in explicitly. Native startup refuses to construct the listener if no explicit service/operator SID is configured.

`FILE_FLAG_FIRST_PIPE_INSTANCE` is used for the serial listener so a pre-existing same-name pipe cannot silently become the StageMesh endpoint. Per-message receive/write sizes remain bounded to the UPPF maximum and connection teardown flushes, disconnects and closes the Win32 handle.

Injected test listeners retain checkpoint 59's stricter rule: they cannot self-assert ACL safety and still require an explicit validator. The native listener can satisfy that startup check because the DACL is constructed by StageMesh before `CreateNamedPipeW`.

## Qualification boundary

Linux tests validate SID normalization, protected SDDL construction, broad-principal rejection, Administrator opt-in and fail-closed listener selection. A real Windows qualification run must still prove security-descriptor creation, service/operator SID access, unauthorized-client denial, UPPF roundtrip/replay/oversize/disconnect behavior and service integration before `IPC-033` is Done.

## Release gate

- **13 focused Windows named-pipe tests** pass, including the six checkpoint-59 transport/authentication regressions and seven protected-DACL policy regressions.
- The complete Python suite passes **638 tests** when split into deterministic discovery-equivalent chunks against the exact fresh RT-qualified engine.
- Fresh RT native CTest passes **2/2**.
- Automation-performance passes with 4096 points prepared across 8192 reads and 8192 frames inside the existing gate.
- All **130 JSON schemas plus OpenAPI** parse, and all **7 frontend JavaScript files** pass Node syntax checking.

`IPC-033` remains **In Progress**. The remaining evidence is actual Windows execution: security-descriptor creation and inspection, authorized service/operator access, unauthorized-client denial, service lifecycle, and authenticated UPPF client/server behavior on Windows.
