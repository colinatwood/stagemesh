# Astra checkpoint 67 validation — live Windows named-pipe DACL attestation

Checkpoint 67 strengthens the checkpoint-66 Win32 listener by validating the security descriptor that Windows actually attached to the created pipe handle before the client is accepted. It still does **not** claim that these Win32 calls have run in this Linux environment.

## Kernel-handle attestation

After `CreateNamedPipeW`, the native adapter calls `GetSecurityInfo` and inspects the returned DACL. StageMesh requires:

- the DACL to be protected from inherited ACEs;
- a non-null DACL;
- only access-allowed ACE types;
- an exact SID set of LocalSystem plus the explicitly configured service/operator SIDs, with Builtin Administrators present only when configuration opted in;
- an exact Generic All access mask for each expected principal.

Extra principals, missing principals, a null/unprotected DACL, deny/unknown ACEs or mismatched masks close the pipe handle and fail before `ConnectNamedPipe`. The client therefore cannot reach UPPF unless the live kernel object matches the intended policy.

The native listener's startup marker now means **policy enforcement is installed**, not that a future pipe handle has already been validated. Each handle is independently attested before acceptance. Injected test listeners still require the explicit checkpoint-59 ACL validator.

## Qualification boundary

Linux tests validate the fact-comparison policy and fail-closed control flow. Actual Windows qualification still must execute `ConvertStringSecurityDescriptor...`, `CreateNamedPipeW`, `GetSecurityInfo`, authorized and unauthorized clients, service startup and UPPF request/replay/oversize/disconnect behavior.

## Release gate

- **20 focused Windows named-pipe tests** pass across bounded UPPF transport, explicit-SID policy and live-DACL fact attestation.
- The complete Python suite passes **645 tests** in deterministic discovery-equivalent chunks against the exact fresh RT-qualified engine.
- Fresh RT native CTest passes **2/2**.
- Automation-performance passes.
- All **130 JSON schemas plus OpenAPI** parse, and all **7 frontend JavaScript files** pass Node syntax checking.

`IPC-033` remains **In Progress** only because the Win32 implementation has not yet executed on Windows. Its remaining evidence is target-OS execution, DACL inspection, authorized/unauthorized client behavior and service integration.
