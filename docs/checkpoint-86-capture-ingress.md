# Checkpoint 86: shared capture ingress (integration completed in later work)

The engine's ALSA capture callback and DAW record queue previously shared an
inlined handoff in `engine_main.cpp`. That handoff is now factored into
`stageforge::submit_capture_packet` in
`native/include/stageforge/capture_ingress.hpp`. The function consumes borrowed
interleaved float samples synchronously, writes to the existing fanout ring,
splits bounded DAW recording blocks, sanitizes non-finite samples and records
native discontinuities as sequence gaps. It does not retain or allocate sample
buffers.

At Checkpoint 86, the native endpoint capture adapter remained separate from
this engine path. Later integration now makes `AUDIO_INPUT_ACTIVATE` construct
an engine-owned `NativeCaptureService` on Windows/macOS and routes its callback
through `capture_native_audio` into `submit_capture_packet`. Linux continues to
use the ALSA input owner and the same shared ingress helper.

The packet metadata type is shared by the endpoint stream and engine ingress.
The target-OS `CaptureReceive` adapter forwards the complete metadata object to
`submit_capture_packet`; its discontinuity flag reserves a recording sequence
gap. The native regression exercises that metadata overload. Linux compilation
excludes the native endpoint callback under platform guards.

## Integration boundary found after Checkpoint 86

The next step cannot safely be implemented as a callback-only hookup:

- `NativeEndpointStream` is owner-thread controlled. Windows capture requires
  its owner thread to pump the WASAPI event handle; `service()` also reconciles
  the selected-device execution fence and stops native I/O after revocation.
- The engine command loop currently blocks on `std::getline`. It has no
  continuously serviced owner loop for a native stream.
- Windows/macOS selection must be pinned from the live `DeviceMonitor` records
  and armed through `DeviceExecutionFence`. `AudioDeviceManager` currently
  exports hashed endpoint tokens but discards the records needed to build and
  maintain that authority.

That later integration supplies the required engine-owned control/service loop.
Each active Windows/macOS slot owns a worker that constructs, services, closes,
and destroys the monitor, fence, and stream on one thread. Explicit activation
pins the selected endpoint token; topology loss fails closed and requires an
explicit rearm. The callback only submits bounded data and metadata to the
shared ingress.

The authenticated target-OS engine smoke now records
`captureIngressIntegrated`, `nativeCaptureOwnerIntegrated`, and
`targetOsCaptureIntegrationCompiled`. These are software integration claims,
not evidence that a live endpoint delivered samples. The standalone
`native_capture_smoke` still reports `fullEngineIntegrated: false` because that
binary intentionally exercises the endpoint adapter outside the engine. No
physical endpoint, microphone-permission, recording-quality, or conversion-
quality claim changes.

## Validation on this branch

- The manually compiled native C++ test executable passed, including the new
  shared capture ingress regression.
- `native/src/engine_main.cpp` compiled with GCC 12 in C++20 mode and
  `-Wall -Wextra -Wpedantic`.
- The native C++ test executable passed with the shared capture ingress tests.
- The packet-metadata ingress overload is covered by native C++ tests. The
  target-OS callback binding is not compiled by this Linux run; a Windows or
  macOS engine build remains required to verify its API binding.
- `tests/test_daw_capture.py`: 8 tests passed with the manually built engine.
- The full Python suite ran all 676 tests: 667 passed, 9 failed in existing
  temporary-resource ownership tests that depend on process-lifetime evidence,
  and one was skipped. These failures do not involve capture ingress.
- CMake is unavailable in the current Linux environment. Windows/macOS SDKs and
  native runners are not available locally, so platform compilation and the
  corresponding workflow evidence remain outstanding.

## Remaining qualification action

Run the target-OS engine against a selected physical input and capture the
activation, callback, audit, deactivation, and topology-loss evidence. Separately
run the named-device loopback and recording-quality suite. Hosted compilation and
capability reporting must not be promoted to either physical claim.
