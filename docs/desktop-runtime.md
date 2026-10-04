# StageMesh desktop runtime boundary

The Tauri application now owns the lifecycle boundary for a local StageMesh
runtime. On startup it:

1. Creates a per-user data directory with separate `sessions`, `media`,
   `preferences`, `logs`, and `tmp` areas.
2. Reserves a loopback port and starts a local runtime sidecar when one is
   available.
3. Passes `STAGEFORGE_DATA_DIR`, `STAGEFORGE_FRONTEND_DIR`, and
   `STAGEFORGE_RUNTIME_MODE=desktop` to that sidecar.
4. Loads the console from the sidecar endpoint and terminates the child when
   the desktop window is destroyed.

The sidecar is intentionally fail-closed. Development builds can point to a
runtime with `STAGEMESH_RUNTIME_EXECUTABLE=/absolute/path/to/stagemesh-runtime`.
Packaged builds will use `stagemesh-runtime` beside the application resources
when that binary is included by a future release packaging step. If no sidecar
exists, the application opens its embedded console and reports `unavailable`;
it does not silently claim that the API, audio, MIDI, or native engine is live.

The current supervisor establishes the process/data contract. It does not by
itself qualify a physical device, audible output, recording quality, drivers,
or target-OS hardware behavior. Those remain separate external qualification
gates.
