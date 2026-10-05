# Astra checkpoint 51 validation — Linux verified plugin-adapter launch binding

Checkpoint 51 closes the Linux verification-to-launch race for external plugin adapter executables. The manifest digest is still an admission contract, but Linux launch now binds process creation to the same opened regular file that was hashed instead of reopening the manifest path after verification.

## Linux launch contract

- External adapter paths remain absolute and must name executable regular files.
- Linux opens the adapter with `O_NOFOLLOW` and rejects symlink adapters.
- StageForge hashes the opened file descriptor and compares it with the manifest `adapterSha256` immediately before launch.
- The child inherits that exact descriptor and executes `/proc/self/fd/<fd>`; Python adapters are passed to the configured Python interpreter through that inherited descriptor.
- Replacing or renaming the manifest path after verification cannot change the bytes executed by that launch.
- The inherited verification descriptor is closed by the parent immediately after process creation.
- Plugin-host status reports `launch.binding = linux-procfd-sha256` and the verified device/inode/size/timestamp identity for observability. Builtin effects remain `builtin`.
- The existing identity/format/protocol/capability/latency handshake, bypass-on-failure behavior, private scratch lifecycle and physical-output disarm contract remain unchanged.

Non-Linux hosts retain the existing path-digest gate until platform-native Windows/macOS launch binding is implemented and exercised on those systems.

## Regression coverage

The focused plugin-host suite includes an adversarial replacement test. It opens and verifies adapter A, replaces the manifest path with adapter B inside the `Popen` interception point, and proves that the launched process is still adapter A by its handshake and original inode identity. A separate regression proves that an executable symlink is rejected before launch.

## Validation

Validated on 2026-09-14:

- fresh Release + `STAGEMESH_RT_QUALIFICATION=ON` native build;
- native CTest: **2/2 passed**;
- full Python suite against that engine: **568 tests passed**;
- focused plugin/latency/security regressions: **36 tests passed**;
- automation-performance gate passed: **4096 points / 8192 reads / 8192 frames in 7.876 ms**;
- **125 JSON schemas plus OpenAPI parsed**;
- **7/7 frontend JavaScript files** passed `node --check`.

The first full Python attempt omitted the installed Node directory from `PATH`, producing five harness-launch errors and no StageForge assertion failures. The rerun restored Node while keeping `/usr/bin/python3` and the same freshly built native engine; all 568 tests passed. No production timeout or watchdog value was changed.

## Remaining boundary

Checkpoint 51 hardens Linux external-adapter launch identity. It does not provide equivalent Windows or macOS verification-to-launch binding, OS sandbox/resource-limit integration, licensed third-party plugin fixtures or real product compatibility evidence. Those remain separate cross-platform and qualification gates. No plugin format or product support claim changes solely because this launch race is closed.
