# StageMesh desktop runtime boundary

The Tauri application now owns the lifecycle boundary for a local StageMesh
runtime. On startup it:

1. Creates a per-user data directory with separate `sessions`, `media`,
   `preferences`, `logs`, and `tmp` areas.
2. Resolves the packaged `stagemesh-runtime` and `stageforge_engine` sidecars.
3. Reserves a loopback port and starts the local runtime with a random API
   credential, a separate desktop-session bootstrap credential, and explicit
   paths for the data directory, frontend, and native engine.
4. Waits for an authenticated `/healthz` response before loading the console.
5. Exchanges the URL-fragment bootstrap credential for an HttpOnly,
   SameSite-strict session cookie. The fragment is removed before normal UI
   requests start.
6. Terminates the runtime child when the desktop window is destroyed.

The sidecar is intentionally fail-closed. Development builds can point to a
runtime with `STAGEMESH_RUNTIME_EXECUTABLE=/absolute/path/to/stagemesh-runtime`
and a native engine with
`STAGEMESH_NATIVE_ENGINE_EXECUTABLE=/absolute/path/to/stageforge_engine`.
Packaged builds include both target-specific executables. The application does
not create its main window when either executable is absent, exits early, or
fails the authenticated readiness check.

The desktop workflow now compiles the native engine and freezes the Python API
runtime with PyInstaller before Tauri builds the Windows, macOS, and Linux
packages. Each runner starts those exact target-tagged sidecars and verifies the
authenticated health, native-engine status, desktop-session cookie, and bundled
frontend response before packaging. This proves package composition and
software startup behavior only.
It does not qualify a physical device, audible output, recording quality,
drivers, signing identity, or target-OS hardware behavior. Those remain
separate external qualification gates.
