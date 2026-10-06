# Sol backlog checkpoint 10 validation

This checkpoint completes the remaining Linux software workflow for persistent
audio endpoint replacement. A persistent-identity change at a reused native ID is
observable and immediately fences active streams. Operators can explicitly trust a
connected replacement only while the affected direction is inactive.

The replacement receipt proves that no stream was started and physical output was
not armed. Ordinary discovery still cannot adopt topology-only replacements; only
the acknowledged workflow records that exact trust decision.

Validation covers first observation, event deduplication, active-stream fencing,
acknowledgement, inactive-direction enforcement, persistence, reselection without
activation, JSON schemas, OpenAPI parsing, frontend syntax, the full Python suite,
and existing native regression binaries. Physical hardware qualification and
Windows/macOS adapters remain deferred.

## Checks

- 383 Python unit/integration tests passed without skips with the qualification
  native engine selected.
- `stagemesh_native_tests` and `stagemesh_current_abi_smoke` passed.
- All 111 JSON schemas and the OpenAPI document parsed.
- `frontend/app.js` passed the Node syntax check.

The current runtime does not provide `cmake` or `ctest`, so this increment did not
repeat a clean configure or sanitizer build. No native sources changed in this
checkpoint; the existing freshly rebuilt native binaries were exercised directly.
