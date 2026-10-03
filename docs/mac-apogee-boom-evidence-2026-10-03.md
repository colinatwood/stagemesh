# macOS Apogee BOOM endpoint lifecycle evidence

Date: 2026-10-03
Repository: `colinatwood/stagemesh`
Validated main commit: `aeabd9f4be3255b2aaeaa5304bea78341f64211e`
Host: MacBook Air, Darwin arm64
Device inventory: Apogee BOOM over USB, 48 kHz, 2 input channels, 4 output channels

## Evidence commands

```sh
python3 ci/native_playback_evidence.py \
  build-mac-hardware/native/native_playback_smoke

python3 ci/native_capture_evidence.py \
  build-mac-hardware/native/native_capture_smoke
```

## Playback result

```json
{
  "status": "passed",
  "sourceCommit": "aeabd9f4be3255b2aaeaa5304bea78341f64211e",
  "nativeCallbacksObserved": true,
  "nativeStopDrained": true,
  "explicitRestartObserved": true,
  "nativeTopologyStoppedStream": true,
  "singleExplicitRearmAfterNativeEvent": true,
  "callbacks": 25,
  "frames": 12800,
  "configuredRateHz": 48000,
  "configuredPeriodFrames": 512,
  "configuredChannels": 4,
  "configuredFormat": "float32",
  "silentTestOnly": true,
  "physicalHardwareQualified": false,
  "audibleOutputQualified": false
}
```

## Capture result

```json
{
  "status": "passed",
  "sourceCommit": "aeabd9f4be3255b2aaeaa5304bea78341f64211e",
  "nativeCallbacksObserved": true,
  "nativeStopDrained": true,
  "explicitRestartObserved": true,
  "nativeTopologyStoppedStream": true,
  "singleExplicitRearmAfterNativeEvent": true,
  "callbacks": 26,
  "frames": 13312,
  "configuredRateHz": 48000,
  "configuredPeriodFrames": 512,
  "configuredChannels": 2,
  "configuredFormat": "float32",
  "captureBuffersDiscarded": true,
  "physicalHardwareQualified": false,
  "physicalCaptureQualified": false
}
```

## Boundary

These results provide provenance-correct silent endpoint lifecycle and callback evidence for the BOOM-compatible Mac configuration. They do not qualify audible output, recording quality, conversion quality, or full physical hardware acceptance. The BOOM device inventory reported 2 inputs and 4 outputs at 48 kHz; the 4-channel playback and 2-channel capture readback are consistent with that endpoint selection.

## Next action

Run the AUD-034 reference-signal measurement task and publish numeric conversion error, SNR, THD+N, continuity, and measurement-summary artifacts.
