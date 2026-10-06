# Astra checkpoint 60 validation — fail-closed Windows/macOS plugin launch attestation contract

Checkpoint 60 removes the last StageMesh behavior that could treat a non-Linux external plugin path plus SHA-256 digest as sufficient verification-to-launch binding. It does **not** claim Windows/macOS process launch is implemented or qualified from Linux.

## Manifest contract

External adapters still require an exact `adapterSha256`, host-system/architecture compatibility and adapter protocol 1. In addition:

- Windows requires `platformLaunchAttestations.Windows` with mode `windows-authenticode-fileid-v1`, an exact `publisherCertificateSha256` and `fileIdentityRequired=true`.
- macOS requires `platformLaunchAttestations.Darwin` with mode `macos-codesign-cdhash-v1`, an exact Team ID and exact code-directory hash.
- Linux requires no extra attestation because verification is already bound to the exact inherited file descriptor launched through `/proc/self/fd`.

The runtime normalizes only the attestation for the selected host. Missing, malformed or extra attestation fields fail manifest validation.

## Platform evidence validation

`validate_platform_launch_evidence()` validates the bounded evidence a future native binder must produce before launch:

- both platforms must match the manifest adapter SHA-256 exactly;
- Windows additionally requires valid Authenticode status, the exact publisher-certificate SHA-256 and non-empty volume/file identity;
- macOS additionally requires a valid code signature, exact Team ID, exact code-directory hash and non-empty file identity.

This evidence is not itself treated as a launch primitive. It is deliberately separate from process creation so the remaining platform implementation must prove the process image is the same verified object.

## Fail-closed runtime behavior

On non-Linux hosts StageMesh no longer executes an external adapter after a path-digest check. Until the Windows/macOS native binder exists, `IsolatedPluginHost` refuses external launch with an explicit launch-binding error. Builtin effects are unchanged. Linux external launch remains the checkpoint-51 file-descriptor binding.

## Validation

- Focused plugin-host tests cover required Windows/macOS attestations, exact platform evidence matching, missing file identity, publisher/Team/CDHash mismatch, and explicit non-Linux launch refusal.
- Linux external-adapter launch-binding regressions remain unchanged and pass.
- Focused plugin-host suite passes **22 tests**.
- Release Python suite passes **614 tests** with zero failures.
- Fresh RT native CTest passes **2/2**; native source is unchanged.
- Automation-performance passes.
- All **126 schemas plus OpenAPI** parse.
- All **7 frontend JavaScript files** pass Node syntax checking.

## Remaining

`PLUG-034` remains open for real Windows/macOS native launch binders. Those binders must create the process from or otherwise cryptographically bind it to the verified file/code object, expose bounded identity evidence, and be exercised on the target OS. Licensed plugin product qualification also remains separate.
