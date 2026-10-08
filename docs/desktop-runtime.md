# StageMesh desktop runtime boundary

The Tauri application now owns the lifecycle boundary for a local StageMesh
runtime. On startup it:

1. Creates a per-user data directory with separate `sessions`, `media`,
   `preferences`, `logs`, and `tmp` areas.
2. Resolves the packaged `stagemesh-runtime` and `stagemesh_engine` sidecars.
3. Reserves a loopback port and starts the local runtime with a random API
   credential, a separate desktop-session bootstrap credential, and explicit
   paths for the data directory, frontend, and native engine.
4. Waits for an authenticated `/healthz` response before loading the console.
5. Exchanges the URL-fragment bootstrap credential for an HttpOnly,
   SameSite-strict session cookie. The fragment is removed before normal UI
   requests start.
6. Requests authenticated loopback shutdown when the desktop window is
   destroyed, waits up to two seconds for runtime cleanup, and force terminates
   the child only when the bounded graceful path cannot complete.

The packaged shell and sidecar use the canonical `STAGEMESH_DATA_DIR`,
`STAGEMESH_FRONTEND_DIR`, `STAGEMESH_RUNTIME_MODE`,
`STAGEMESH_REQUIRE_API_TOKEN`, `STAGEMESH_API_TOKEN`, and
`STAGEMESH_DESKTOP_SESSION_TOKEN` environment contract. The one-time browser
exchange uses `X-StageMesh-Desktop-Token`; retired pre-migration desktop-mode
and bootstrap-token names are not accepted.

The sidecar is intentionally fail-closed. Development builds can point to a
runtime with `STAGEMESH_RUNTIME_EXECUTABLE=/absolute/path/to/stagemesh-runtime`
and a native engine with
`STAGEMESH_NATIVE_ENGINE_EXECUTABLE=/absolute/path/to/stagemesh_engine`.
Packaged builds include both target-specific executables. The application does
not create its main window when either executable is absent, exits early, or
fails the authenticated readiness check.

The shutdown route exists only in desktop mode, requires the random control
credential, and accepts loopback clients only. The runtime sends its response
before stopping the HTTP server; the normal `finally` path then closes native
services and persistence resources. A crashed or unresponsive sidecar cannot
hold the desktop open indefinitely because the supervisor retains the bounded
force-termination fallback.

The desktop workflow now compiles the native engine and freezes the Python API
runtime with PyInstaller before Tauri builds the Windows, macOS, and Linux
packages. Each runner first verifies that the exact target-tagged runtime fails
closed and cleans up its native child when the selected loopback port is already
owned. It then releases that port and restarts the same packaged runtime against
the same data directory, verifying authenticated health, native-engine status,
desktop-session cookie, and bundled frontend response before requesting
authenticated graceful shutdown and requiring a clean process exit. This proves
package composition, port-collision recovery, and software startup/shutdown
behavior only.
It does not qualify a physical device, audible output, recording quality,
drivers, signing identity, or target-OS hardware behavior. Those remain
separate external qualification gates.
