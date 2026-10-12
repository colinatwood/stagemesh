# Clean-host and Windows evidence execution — 2026-10-10

This execution followed the merged CI supply-chain reconciliation on `main` at
`133a78b9823b8a5d6baa0c789f4e18428b316f18`. The downloadable candidate used
for direct checks was PR #163's successful desktop run `38102800559`, whose
workflow head was `f06d1b9597101281a7c68b9bd4aca59ddf074a6a` and whose generated
candidate source commit was `f9170f231aa8f7466743961ec6507fd565ca927a`.
The PR's four workflows and all 13 jobs passed before merge.

## Exact artifacts checked

| Artifact | GitHub artifact ID | Archive digest | Direct result |
| --- | ---: | --- | --- |
| Release candidate index | `11689156731` | `sha256:83238f31b7150a1e798fb59cab6238f745895521abc8c57274bb5a92732dbe20` | Downloaded and parsed; it binds Linux/standard, macOS/standard, Windows/online, and Windows/offline bundles. |
| Ubuntu 22.04 standard bundle | `11688831261` | `sha256:0a051c9e539463fbed063e7dbb83ce277f7fb2d99298f11283abce8428ffa8dd` | Packaged verifier passed all 445 manifest entries. Signing status remains `not-configured`. |
| Windows 2022 online bundle | `11689225006` | `sha256:03043b88498256e901a0fa2491a512458a74b2911ef1ce7c7735cf79665e36ff` | Packaged verifier passed all eight manifest entries. Signing status remains `not-configured`. |

These verifier passes establish transport integrity and internal consistency.
They do not authenticate a publisher or qualify installation, signing,
accessibility, legal review, physical hardware, or audible quality.

## Ubuntu 24.04 clean-host exercise

The supported x86-64 Ubuntu 24.04 runner had no StageMesh package, executable,
or process before the exercise. Both Debian and AppImage collectors recorded a
passing baseline bound to the exact bundle and installer digest.

The Debian install then exposed a collector defect before qualification could
continue: the built package registers as `stage-mesh` and installs
`/usr/bin/stagemesh-desktop`, while the collector queried `stagemesh` and
`/usr/bin/stagemesh`. The collector now uses the actual package and executable
identities, with executable regressions. The same run also found that this
minimal host lacks `libwebkit2gtk-4.1-0`, `libsoup-3.0.so.0`, and
`libjavascriptcoregtk-4.1.so.0`; the package remained unconfigured and was
purged. The environment's package index could not supply the dependencies.

The AppImage copied and extracted successfully, but its desktop process stopped
at GTK initialization because the runner has no graphical display. Runtime
readiness was not asserted. Restart, real-version upgrade, and uninstall phases
therefore remain open. The copied AppImage was removed after the observation.

The managed runner's `ps` command also fails independently of StageMesh. Linux
collection now reads process names directly from `/proc`, while macOS retains
its existing `ps` path. This preserves the no-running-process check without
weakening it.

## Windows evidence path

The exact Windows online bundle includes both NSIS and MSI installers, the
Windows clean-host collector, reviewer, dependency inventory, SBOM, checksums,
and signing reports. The bundle verifier passed, the collector CLI loaded, and
the Windows collector plus native-evidence regression suites passed locally.

Target-host execution subsequently continued on Windows 11 Pro 10.0.26300 x64
at source commit `133a78b9823b8a5d6baa0c789f4e18428b316f18`, using CMake 4.4.3,
Python 3.14.3, Git 2.53, and Visual Studio 2022 Build Tools. The Release build
passed its four configured native CTests: native, current ABI, capture owner,
and MIDI owner.

The source-bound capture exercise completed against the attached Apogee BOOM
environment without reproducing the earlier `0x800700AA` busy failure. It
recorded 16 callbacks and 30,720 stereo float32 frames at 192 kHz, with
stop/drain/restart passing and no audio retained. The matching silent playback
exercise also completed 16 callbacks and 30,720 frames at 192 kHz. Device
inventory recorded the Apogee BOOM driver as `5.68.0.25871`. Because the smoke
transcript does not expose the selected endpoint's human-readable name and the
playback was intentionally silent, these observations qualify the native
capture/playback execution paths, not audible BOOM quality or routing.

The first production-engine MIDI attach attempt crashed before operator input.
Targeted inspection found that the WinMM `midiInOpen` callback and instance
arguments were reversed, causing Windows to execute the slot data address as a
function. Commit `c3b4096` corrects the ordering and adds a source regression.
The correction passed 14 focused tests and the complete Python suite (836
passed, 24 expected environment skips) before target-host verification.

The operator then applied only that two-argument correction to the clean
`133a78b` checkout, rebuilt `stagemesh_engine.exe`, and exercised all three
enumerated WinMM inputs while playing only the FLkey Mini. All three inputs
attached successfully; one stable endpoint delivered 297 events through the
production IPC observer. The MIDI audit recorded 302 callback messages, zero
queue drops, zero injected messages, and zero topology detaches. Events
included note traffic on status bytes 145 (`0x91`) and 153 (`0x99`) with both
nonzero velocities and releases. All three inputs detached cleanly and the
engine returned `OK bye=1`. This target-host result confirms the callback fix
and live FLkey MIDI ingress. `mapped=0` is expected because the diagnostic did
not configure show-event mappings.

Windows MIDI lifecycle qualification remains open. The diagnostic lifecycle
run reported `nativeMidiEnumerationAvailable=true` but
`midiNotificationsRegistered=false`, and the build-time
`STAGEMESH_HAS_CM_NOTIFY` probe failed. Consequently, physical disconnect and
reconnect recovery without the unavailable-native-MIDI allowance has not
passed and is not implied by the successful steady-state ingress run.

## Local validation

- Complete Python discovery passes: 835 tests passed with 24 explicit
  environment skips.
- POSIX clean-host, cross-platform reviewer, and release-readiness focused tests pass.
- Windows clean-host and native host evidence/exercise focused tests pass.
- Exact Linux and Windows online bundle verification passes.
- On 2026-10-11, CMake 4.4.3 was installed in an isolated temporary
  environment from the repository's exact release-tool pin. A fresh
  Release/RT build at `a3c95a64fae3bf9e441bbb85793e4127daeccec1`
  passed all five native CTests. The same five tests passed under ASan/UBSan.
- The five-test native set then passed 100 consecutive repetitions per test
  (500 executions total).
- A newly frozen PyInstaller desktop runtime and matching native engine passed
  the packaged sidecar smoke, including authenticated startup, loopback-port
  collision failure/recovery, persistent restart, corrupt-store fencing, and
  graceful shutdown. The same smoke passed 20 consecutive repetitions.
- The automation performance contract passed with RT qualification required;
  the native engine authentication/dispatch smoke and Linux platform smoke
  also passed.
- Desktop release readiness and the exact `v0.1.0` version shape passed.
  Dependency inventory and CycloneDX generation recorded 430 locked
  components each.
- The complete combined release gate remains unavailable on this managed
  filesystem: its isolated-rootfs ownership exercise cannot use this host's
  disabled `sudo`, and a direct root execution reaches `systemd-tmpfiles` but
  fails with `fchownat(...): Invalid argument`. This is an execution-environment
  limitation; the underlying Python, native, sanitizer, runtime, version,
  schema, frontend syntax, and performance checks above passed independently.

## Ordered Windows PC continuation

The remaining sequence is deliberately target-host bound and must not be
reported as completed from this Linux session:

1. Publish the collector repair and WinMM callback correction, then use
   artifacts built from the resulting merged commit.
2. On fresh Windows 11 x64 snapshots, run four independent tracks: online
   NSIS, online MSI, offline NSIS, and offline MSI. For each, preserve the
   baseline, installed, restarted, genuine different-version upgrade, and
   uninstalled phases. Do not reuse one report across installers or channels.
3. Repeat the BOOM capture and FLkey ingress exercises from a clean checkout of
   the merged fix so their binary provenance points directly to the release
   candidate. Record BOOM firmware and Apogee Control versions, explicit
   selected endpoint identity, format/exclusive mode, routing, cable, and gain.
4. Restore Windows configuration-manager notification support, then exercise
   FLkey Mini physical disconnect and reconnect without
   `STAGEMESH_ALLOW_UNAVAILABLE_NATIVE_MIDI`. Preserve the event and topology
   transcript; steady-state ingress does not qualify hot-plug recovery.
5. Exercise the installed application keyboard-only with NVDA at 100%, 150%,
   and 200% display scaling. Preserve an issue log covering focus order,
   visible focus, control names/states, live status announcements, zoom/reflow,
   and error recovery.
6. Select and configure the Windows signing provider. Current local preflight
   confirms that neither PFX inputs nor Azure Artifact Signing inputs are
   configured. Rebuild, sign, timestamp, and run exact-artifact verification
   before any release rehearsal.

No external qualification status was closed by this execution.
