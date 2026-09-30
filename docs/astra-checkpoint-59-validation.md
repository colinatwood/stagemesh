# Astra checkpoint 59 validation — Windows UPPF named-pipe transport/security foundation

Checkpoint 59 closes the transport-neutral framing and fail-closed security contract needed by the remaining Windows UPPF named-pipe adapter. It does **not** claim a Windows pipe has been created or that a real Windows ACL has been inspected from this Linux environment.

## Shared bounded framing

The local IPC layer now exposes exact packet helpers around the existing UPPF session frame:

- a four-byte big-endian frame length is retained on both stream and message transports;
- frames smaller than the authenticated UPPF header or larger than the fixed UPPF maximum are rejected before channel decode;
- message transports reject truncated packets, extra trailing bytes and oversized packets rather than relying on the transport to delimit safely;
- Unix-domain socket behavior continues to use the same bytes and the same authenticated `AuthenticatedSessionChannel` contract.

The authenticated request loop is transport-neutral and still enforces a bounded request count. Capability, session identity, key epoch, sequence/replay and HMAC checks remain inside UPPF rather than being delegated to named-pipe semantics.

## Windows named-pipe foundation

`WindowsNamedPipeIpcServer` adds the Windows-side adapter contract:

- pipe names are restricted to `\\.\\pipe\\StageMesh\\<safe-name>`;
- the default listener is Windows `AF_PIPE` only; there is no Unix emulation path masquerading as Windows support;
- startup **requires** an explicit ACL validator and fails closed if that validator is absent or returns anything other than true;
- a failed ACL check closes the listener before any request is accepted;
- named-pipe messages carry the exact same bounded length-prefixed UPPF frame used by the Unix socket path;
- per-connection request count remains bounded and physical outputs are not armed by the transport.

The ACL validator is intentionally not implemented as a Linux guess. A Windows deployment must create/inspect the actual named-pipe security descriptor and prove the intended service/operator principals before the adapter can be considered complete.

## Validation

- **8 focused local-IPC/named-pipe tests pass**, including authenticated message-pipe roundtrip, exact framing, trailing/truncated packet rejection, StageMesh pipe-name scoping, mandatory ACL validation, failed-ACL listener cleanup and bounded request service.
- Broader session/API/infrastructure slice passes **87 tests**.
- Release Python suite passes **610 tests with zero skips**.
- RT native CTest remains **2/2**; native source is unchanged.
- Automation-performance passes.
- All **126 schemas plus OpenAPI** parse.
- All **7 frontend JavaScript files** pass Node syntax checking.

## Remaining

The Windows implementation still needs a real named-pipe listener/security backend that creates or verifies the pipe DACL on Windows and then runs these exact framing/authentication semantics in Windows CI. Windows service identity, install-time ACL policy and real client/server interoperability must be exercised before `IPC-033` can be marked complete.
