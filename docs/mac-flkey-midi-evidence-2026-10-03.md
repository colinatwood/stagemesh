# macOS FLkey Mini MIDI callback evidence

Date: 2026-10-03
Repository: `colinatwood/stagemesh`
Validated main commit: `2444b4d187c014422ef83f30312e543362d64b76`
Hardware: Novation FLkey Mini connected to a MacBook Air

## Command

```sh
export STAGEFORGE_MIDI_DEVICE_NAME="MIDI Out FLkey Mini"
./build-mac-hardware/native/midi_hardware_smoke 2>&1 | tee midi-hardware-smoke.json
```

## Observed result

```json
{"endpointName":"MIDI Out","matchedName":"MIDI Out FLkey Mini","attached":true,"eventsObserved":1,"callbackMessages":1,"physicalOutputsArmed":false,"hardwareQualified":true}
```

A real key event was observed while the FLkey Mini was exercised. The result confirms production CoreMIDI attach and callback delivery after PR #60 corrected use of the source connection refcon.

## Boundary

This evidence qualifies the named MIDI callback smoke on the connected Mac. It does not qualify audio input/output, audible output quality, physical hotplug/topology loss, conversion quality, or full target-platform release acceptance. Those gates remain open.

## Next action

Set the Apogee BOOM as the Mac default input and output, rerun native playback/capture evidence, and continue the AUD-034 reference-signal measurements.
