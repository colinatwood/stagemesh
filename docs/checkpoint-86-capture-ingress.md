# Checkpoint 86: shared capture ingress (integration boundary recorded)

The engine's ALSA capture callback and DAW record queue previously shared an
inlined handoff in `engine_main.cpp`. That handoff is now factored into
`stageforge::submit_capture_packet` in
`native/include/stageforge/capture_ingress.hpp`. The function consumes borrowed
interleaved float samples synchronously, writes to the existing fanout ring,
splits bounded DAW recording blocks, sanitizes non-finite samples and records
native discontinuities as sequence gaps. It does not retain or allocate sample
buffers.

The native endpoint capture adapter remains separate from this engine path.
`AUDIO_INPUT_ACTIVATE` still selects the ALSA backend on Linux; Windows/macOS
native capture stream callbacks are not connected to the full engine. The native
capture evidence continues to report `fullEngineIntegrated: false`. No platform,
endpoint or recording-quality claim changes here.

The packet metadata type is shared by the endpoint stream and engine ingress.
The target-OS `CaptureReceive` adapter forwards the complete metadata object to
`submit_capture_packet`; its discontinuity flag reserves a recording sequence
gap. The native regression exercises that metadata overload. This is an
integration seam only: no `NativeCaptureStream` is currently constructed by the
engine, and activation/fencing/service ownership remain open. Linux compilation
excludes the endpoint callback under platform guards.

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

The integration therefore needs an engine-owned control/service loop that
preserves owner-thread stream operations, feeds the shared bounded ingress,
reconciles topology changes, and reports activation/deactivation safely. A
callback that directly calls the helper without this lifecycle would leave
Windows event packets unserviced and could keep stale device authority armed.
The current Linux environment has no CMake or Windows/macOS SDK, so target-OS
compilation and event-pump verification are unavailable here. Treat the
full-engine hookup as blocked until that loop is designed and target-OS build
validation can run; do not change `fullEngineIntegrated` evidence meanwhile.

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

## Next action

Design and test an engine-owned native capture control/service loop, then connect
`NativeCaptureStream` to `submit_capture_packet` through its bounded callback.
Preserve the selected-device fence and owner-thread lifecycle, and verify Windows
and macOS builds before updating native integration evidence. Keep accessible
endpoint and named-device recording-quality qualification separate.
