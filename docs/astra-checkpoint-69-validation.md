# Astra checkpoint 69 validation — GitHub-hosted cross-platform CI reference

Checkpoint 69 adds a GitHub Actions CI definition and target-OS smoke evidence helper so Windows/macOS code can execute on the kernels it targets instead of being validated only through Linux-side mocks.

The workflow has a Linux RT developer-alpha gate plus Windows x64 and macOS Apple Silicon build/smoke jobs. All jobs compile the native engine with tests enabled. Windows then runs the real protected `CreateNamedPipeW` StageMesh endpoint using the hosted runner's explicit user SID, performs the pre-accept kernel DACL attestation from checkpoints 66–67, and completes an authenticated UPPF roundtrip through the native pipe. The report deliberately leaves `unauthorizedClientDenialQualified=false` because the hosted job has only one trusted login context. macOS executes the real `system_profiler SPAudioDataType` CoreAudio evidence probe but does not claim a named external audio interface.

`scripts/platform-ci-smoke.py` emits `org.upp.platform-ci-smoke` evidence bound to the exact native-engine SHA-256 with `physicalOutputsArmed=false` and `physicalHardwareQualified=false`. `.github/workflows/ci.yml` uploads that JSON as a 30-day artifact for each target platform.

## Local release gate

- Fresh RT native CTest: **2/2**.
- Complete Python release suite: **654 tests**, zero skips.
- Linux instance of the new platform smoke helper passes and hashes the exact fresh native engine.
- Automation-performance passes.
- All JSON schemas plus OpenAPI parse.
- All frontend JavaScript files pass Node syntax checking.

Actual Windows/macOS workflow results remain target-OS evidence and must be reviewed after GitHub executes the branch. Hosted runners are software/platform references, not physical audio/MIDI/plugin qualification.
