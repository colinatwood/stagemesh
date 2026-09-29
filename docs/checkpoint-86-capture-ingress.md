# Checkpoint 86: shared capture ingress (in progress)

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

## Validation on this branch

- The manually compiled native C++ test executable passed, including the new
  shared capture ingress regression.
- `native/src/engine_main.cpp` compiled with GCC 12 in C++20 mode and
  `-Wall -Wextra -Wpedantic`.
- `tests/test_daw_capture.py`: 8 tests passed with the manually built engine.
- The full Python suite ran all 676 tests: 667 passed, 9 failed in existing
  temporary-resource ownership tests that depend on process-lifetime evidence,
  and one was skipped. These failures do not involve capture ingress.
- CMake is unavailable in the current Linux environment. Windows/macOS SDKs and
  native runners are not available locally, so platform compilation and the
  corresponding workflow evidence remain outstanding.

## Next action

Connect `NativeCaptureStream` to the shared engine ingress path, preserve its
owner-thread service and selected-device execution fence, and verify Windows and
macOS builds before updating the native integration evidence. Keep accessible
endpoint and named-device recording-quality qualification separate.
