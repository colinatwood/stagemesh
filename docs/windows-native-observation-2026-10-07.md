# Windows native device observation — 2026-10-07

This record preserves a user-run Windows test session. It is a host observation only:
the exact source revision, Windows build, BOOM driver/firmware, and endpoint format settings
were not captured in the shared console output. It must not close device qualification
or be treated as evidence bound to a particular release candidate.

## Host and devices observed

- Repository path: `C:\Users\djgre\src\stagemesh`
- Build: CMake configure and Visual Studio/MSBuild Release build completed successfully.
- Windows PnP listed these device endpoints with status `OK`:
  - Apogee BOOM media device, audio endpoints `Speakers (2- Apogee BOOM)` and
    `Line (2- Apogee BOOM)`, and an Apogee BOOM MIDI endpoint.
  - Focusrite FLkey Mini media device and MIDI endpoints.
- The PnP output did not establish runtime MIDI event delivery or physical audio
  quality.

## Test results reported by the operator

- CTest excluding `native_capture`: **12/12 passed** with
  `STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST=1` and
  `STAGEMESH_ALLOW_UNAVAILABLE_NATIVE_MIDI=1`.
- `native_playback`: passed on retry with
  `STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST=1`.
- `native_playback_service`: passed in the earlier playback CTest invocation.
- `device_lifecycle`: passed with
  `STAGEMESH_ALLOW_UNAVAILABLE_NATIVE_MIDI=1`. This explicitly permits the
  unavailable native MIDI path; it does not demonstrate FLkey callback delivery.
- `native_capture`: failed on repeated runs with
  `initialize exact WASAPI stream: -2147024726` (HRESULT `0x800700AA`,
  Win32 `ERROR_BUSY`), including after the capture test's explicit opt-in.
- The capture failure remained reproducible in the last supplied output. No
  capture endpoint lifecycle pass is claimed for this Windows host.

## Separate AUD-034 measurement report

The operator supplied an aligned 48 kHz, stereo, 24-bit reference/capture report
with 54,121-frame alignment. It observed zero clipped samples, dropouts, or
discontinuities, approximately 66.12 dB minimum reference-residual SNR, approximately
88.36 dB tone SNR, and approximately -88.36 dB THD+N. The measured gain ratio was
approximately -1.006 on each channel. With a periodic sine reference, this may
reflect phase-alignment ambiguity or polarity inversion; this observation does
not distinguish the two. A separately synchronized or nonperiodic reference
is needed before concluding that the physical routing inverts polarity. The report itself
keeps threshold application, owner review, conversion qualification, and physical
hardware qualification false. Preserve the original WAVs, JSON report, hashes, and
bench notes with the owner’s evidence bundle; this repository note does not replace
those source artifacts or independently verify them.

## Evidence boundary and next capture fields

This session is not bound to a source commit because `git rev-parse HEAD` was not
included. It also lacks the exact Windows edition/build, Apogee firmware and driver
versions, Apogee Control version, endpoint exclusive-mode settings, default format,
physical TRS routing, and a full saved CTest transcript. Keep Windows capture and
MIDI hot-plug qualification open.

For a repeatable follow-up, record:

- `git rev-parse HEAD`, `winver`, and `Get-CimInstance Win32_OperatingSystem | Select Caption, Version, BuildNumber`
- Apogee BOOM firmware, Windows driver, and Apogee Control versions
- Windows default playback/recording endpoint names, sample rate/bit depth, and exclusive-mode settings
- Whether the capture source was BOOM analog input or loopback, exact cables/adapters, gain, and routing
- Full CTest output, with only the necessary opt-in variables set for each physical endpoint test
- A real FLkey event and disconnect/reconnect transcript, without the unavailable-MIDI allowance

Successful hosted/software tests and PnP visibility remain separate from physical
audio/MIDI acceptance.

## Read-only provenance collector

From the repository, collect the source snapshot, binary SHA-256, Windows
release/version/architecture, and the existing privacy-preserving USB/audio
endpoint/installed-driver inventory:

```powershell
cd C:\Users\djgre\src\stagemesh
py -3 .\scripts\native-host-evidence.py `
  --binary .\build\native\Release\native_capture_smoke.exe `
  --output .\evidence\windows-native-host-session.json
```

The collector resolves Git from its repository even if the shell starts in
another directory. Input/output paths still resolve from the shell's working
directory. It does not run the binary, capture audio, request microphone
access, or change device settings. Failed inventory probes remain reported as
unavailable; they are not proof that devices are absent.

To bind the identity of saved console files, add `--transcript` once per
existing transcript. A new run must use a new output filename; the collector
refuses to overwrite an earlier session or any input. File hashes identify
observed bytes. Evidence inputs must be distinct regular files with distinct
filenames; symlinks, repeated files, ambiguous filenames, and files that change
while hashing fail closed. Copy separately named, stable transcripts into the
session evidence directory before collection rather than passing aliases. These
checks do not establish that a binary was built from the observed commit or that
a transcript belongs to that build. Preserve the actual build
and test commands, timestamps, exit codes and opt-ins for owner review.
Firmware, Apogee Control version, Windows edition, endpoint settings, cables,
gain and routing still require operator notes. Collect these notes before
closing unrelated audio applications and repeating the capture test.
