# Plugin adapter compatibility

StageMesh treats VST3, CLAP, LV2 and Audio Unit support as an external adapter
contract. Listing a format does not mean that Core contains or certifies a native
loader for that format.

Before an external adapter process can start, its manifest must provide:

- an absolute executable path;
- the supported host systems (`Linux`, `Windows`, or `Darwin`);
- the supported machine architecture names;
- adapter protocol version `1`; and
- a `sha256:` digest of the executable.

The current system and architecture must be explicitly listed. On Linux, StageMesh
opens the adapter as a non-symlink regular file, hashes that exact descriptor and
launches through the inherited `/proc/self/fd/<fd>` handle. Replacing the manifest
path after verification therefore cannot substitute different bytes for that launch.
Plugin-host status reports the launch binding and verified filesystem identity.
Windows and macOS no longer fall back to path-digest-only launch. Their manifests must
carry platform-native launch attestations before they are considered compatible:

- Windows requires `windows-authenticode-fileid-v1`, an exact SHA-256 fingerprint of the
  expected publisher certificate and an explicit requirement that runtime file identity be
  bound to launch.
- macOS requires `macos-codesign-cdhash-v1`, an exact Team ID and exact code-directory
  hash.

The host validates these manifest requirements and can validate bounded platform evidence
objects, but external adapter launch on Windows/macOS remains fail-closed until a native
platform binder can prove the launched process image is the same verified file/code object.
There is no legacy path-digest fallback. The adapter must then complete
the existing identity, format, protocol, processing-capability and bounded-latency
handshake. Any failure leaves the effect bypassed and immediately reaps the failed
adapter process.

Each launched adapter receives a private per-instance directory through
`STAGEMESH_PLUGIN_INSTANCE_SCRATCH_DIR`. The parent records exact boot/process-start
ownership, removes the directory on normal close and reports crash residue through
`GET /api/v1/daw/plugin-hosts/lifecycle` and the aggregate DAW temporary-resource
status. Acknowledged cleanup removes only scratch owned by a process proven dead.
Malformed or unverifiable ownership is retained. `STAGEMESH_PLUGIN_SCRATCH_DIR`
selects a private service-owned root and `STAGEMESH_PLUGIN_SCRATCH_MAX_BYTES`
sets the shared admission threshold (512 MiB by default, minimum 1 MiB).

The host discards adapter stderr so an unread diagnostic pipe cannot deadlock audio
processing. Protocol errors remain bounded in the host audit. Timeout, close and
forced-kill counters are exposed; adapters never restart automatically.

The plugin catalog applies the same manifest compatibility rules. Invalid or
incompatible entries are reported as quarantined rather than advertised as usable.
Builtin effects do not need the external-adapter fields, but still execute through
the isolated host boundary.

## Limits

Linux binds verification and execution to the same opened file descriptor. Windows and
macOS manifests now require explicit native-signing/file-identity attestations and the host
refuses unbound launch, but the OS-native binder itself still must be implemented and
exercised on those platforms before StageMesh can claim verification-to-launch parity.

No third-party plugin binaries are bundled. Actual VST3, CLAP, LV2 and Audio Unit
products still require licensed test fixtures and runs on each claimed operating
system and architecture. Audio Unit qualification in particular requires macOS.
The scratch threshold is admission/observability policy, not an OS disk quota; a
hostile adapter can exceed it until OS sandbox/resource-limit integration exists.
