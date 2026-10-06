# Developer-alpha release scope and gates

The first release target is a local-only Linux developer alpha. This is a target,
not a declaration of supported distributions or hardware. No interface is yet
qualified for unattended or show-critical production use.

## Repeatable software gate

The latest complete run is recorded in [Core 5.10.5 validation](core-5.10.5-validation.md):
fresh CMake/CTest Release and Debug sanitizer builds passed on 2026-09-11.
The release gate requires the selected native engine to report qualification
probes enabled; ordinary development tests still accept either build mode.

File conversion now computes interpolation positions from integer canonical-frame
coordinates, avoiding block-local rounding. A regression test compares identical
stereo samples across uneven read partitions at six input rates (32–192 kHz).
This establishes partition consistency, not conversion quality: the file converter
still uses linear interpolation without a qualified anti-alias filter.

Partial-range fade timing now uses the original clip offset and length, rather than
the clipped render region. Regression coverage compares partial-range arrangement
samples and 32-bit export PCM against the matching full-range audio for fade-in,
sustain and fade-out. The fixture avoids limiter activation; this does not establish
range equivalence for stateful effects/limiting or qualify alternative fade curves.

Linear and equal-power clip fades now share one implementation between playback
and export. Equal-power applies `sin(pi * level / 2)` to the normalized fade level;
unknown curve names are rejected. Existing sample endpoints are retained: an N-frame
fade-in progresses from 1/N to 1 before curve shaping, and fade-out reverses it.
This changes equal-power sessions that earlier versions incorrectly rendered with
linear fades. It does not implement phase-aware crossfades or other fade shapes.

Splits now preserve the original envelope through optional fade `spanFrames` and
`offsetFrames` fields. Splitting within a fade, including repeated splits, does not
restart or shorten that envelope. Explicit fade edits reset it to the edited clip;
trimming a split fragment advances its envelope offset. Older readers that ignore
these fields cannot reproduce the preserved split fades. Regression coverage checks
byte-identical exports across three split positions and saved-session reloads.

Install Python 3.10 or newer, a C++20 toolchain, CMake 3.20 or newer (with CTest),
and Node.js for JavaScript syntax checks. From the source root run:

If CMake/CTest are not installed, the pinned build-tools environment provides both:

```
python3 -m venv .venv-release
. .venv-release/bin/activate
python -m pip install -r requirements-release.txt
```

Then run the gate:

```
python3 scripts/release-check.py --check-prerequisites
python3 scripts/release-check.py
```

The gate builds in a new temporary directory, runs native and current ABI tests,
pins Python tests to the freshly built engine, rejects test failures and skipped
coverage, and checks browser JavaScript syntax. It does not enable services,
activate physical outputs, publish files, or qualify hardware. No ambient developer
build is accepted as release evidence. Run in an isolated test environment without
show hardware attached; the existing tests are not a production monitoring tool.

## Remaining publishing blockers

- Validate this CMake workflow on a clean Linux machine and record tool versions.
- Staged installation, qualification-helper lookup, reinstall preservation, safe uninstall and explicit purge have automated smoke tests. Sysusers/tmpfiles definitions and a hardened service unit are included. Real systemd installation, upgrade/rollback and permission qualification remain open.
- Managed import, save, MIDI Learn, reopen, native arrangement/sample submission and offline export now have a runtime acceptance test. Browser import, audible playback/loop and recording still need a combined workflow test.
- The HTTP acceptance suite now saves a DAW session, adds a marker and volume
  automation, moves a clip, validates a render plan, exports deterministic WAV,
  and—when the native engine is present—starts/stops queued playback. Every receipt
  remains physically disarmed. Live audible output and physical recording still
  require hardware qualification.

## Native sanitizer gate

`scripts/sanitizer-check.py` creates a fresh Debug CMake tree with
`STAGEMESH_ENABLE_SANITIZERS=ON`, builds all native targets, and runs CTest under
AddressSanitizer and UndefinedBehaviorSanitizer with halt-on-error behavior. The
default disables LeakSanitizer because traced/containerized environments may deny
the `/proc` task inspection it requires. Run `--detect-leaks` on an untraced Linux
qualification host. Neither mode activates stage hardware. A passing sanitizer run
is additional evidence, not a real-time latency or target-hardware qualification.
- Resolve callback-size/rate correctness, delay-bank concurrency and trigger races.
- Checkpoint 33 adds a strict loopback `proxy-https` deployment profile and executable backend/TLS-edge qualification helper; checkpoint 34 bounds the per-user authorization audit. A real LAN proxy/certificate/IdP/firewall deployment, controller workload/disk-cost qualification, specialized authorization-audit unification and witness/replication secret lifecycle still block LAN production claims.
- Apache License 2.0 is present and the public contribution/security/support files
  are release-gated. Owner/legal review of exact dependency redistribution rights
  and notices remains required before publication.
- Produce setup instructions, a demo session and known-issues documentation.
- Measure actual latency, dropouts, reconnect and recovery on named hardware.

Delay-graph activation remains a control-thread prototype, not connected live
alignment. Overload telemetry is advisory; automatic effect shedding is disabled.
Streaming banks share the arrangement playback producer; they are not independent
polyphonic streaming voices. LE/UWB synchronization and third-party plugin format
coverage must remain experimental until end-to-end qualification exists.

## Staged Linux installation

The service unit currently supports only `/usr`. The installer accepts an absolute
`DESTDIR` for package staging and `STAGEMESH_BUILD_DIR` for the selected build
directory.
It does not create the service account, enable/start a service, or activate devices.
Unsupported prefixes and missing engines fail before destination creation.
The staged smoke tests use a placeholder engine to validate packaging independently;
they do not establish that an installed service runs correctly on a target system.

## Session restart acceptance

`tests/test_session_restart.py` imports a generated 48 kHz WAV into managed media,
deletes the import source, saves the session through the runtime API,
learns a pad from injected native MIDI, closes the runtime, and
reopens the same data directory. It checks session and mapping preservation,
sampler preload, render planning, native arrangement/sample submission and a
non-silent 192 kHz stereo 32-bit PCM export with outputs disarmed.
A second test modifies the media before restart and verifies that its mapping is
preserved but not promoted to a native binding. These tests run in the clean release
gate; they establish neither audible output nor browser, recording or hardware
qualification. The WAV is a fixture, not evidence of the browser import workflow.

`tests/test_media_import_integrity.py` checks deduplication, rejection of corrupted
managed objects, and rejection/cleanup when source bytes change during copying.
Import verification is a publication-time check; it does not prevent later media
mutation or establish continuous integrity during arrangement streaming.

Arrangement start and offline export now verify declared audio-file hashes before
changing playback or writing output. Legacy sources without a hash remain accepted.
This preflight uses bounded reads but may add startup time for large sessions.
Playback/export now create private whole-file copies and hash the copied bytes,
then read only those copies for the operation. Subsequent changes to the original
cannot alter those reads. Legacy unhashed sources receive a calculated hash, without
establishing prior authenticity. Copies consume temporary disk space proportional
to the unique sources, including portions outside the selected range. Preparation
failure leaves current playback/export untouched. Playback retains copies until
its worker exits, including after a stop timeout; export removes them on completion
or error. Media snapshots now use a shared, locked store. Creation reclaims only
directories whose recorded boot/process-start identity is proven dead; unknown or
malformed owners remain and consume quota.

The developer alpha limits concurrent snapshots to 2 GiB per server process.
Reservations cover whole unique source/hash pairs before copying, and are released
on cleanup or preparation failure. Free-space checks conservatively include existing
reservations plus a 64 MiB reserve. Source growth beyond the reserved size is rejected.
These checks do not reserve filesystem blocks against other processes; disk writes
can still fail. The shared store serializes reservations across processes and counts
the greater of reserved or observed bytes. `STAGEMESH_SNAPSHOT_MAX_BYTES` and
`STAGEMESH_SNAPSHOT_FREE_RESERVE_BYTES` configure strict byte limits; invalid values
fail closed. `STAGEMESH_SNAPSHOT_DIR` selects the store. Live or unverifiable owners
are never reclaimed automatically. Starting a replacement while an old snapshot is retained must fit both within
the shared budget.

`GET /api/v1/daw/temp-resources` reports the shared store's configured budget,
reserved and observed bytes, and bounded live/reclaimable/unknown-owner entries.
It deliberately omits filesystem and source-media paths. The Production projection
includes the same status. `POST /api/v1/daw/temp-resources/cleanup` requires
`acknowledgeCleanup: true` and removes only entries whose exact boot/process-start
owner is proven dead; live and unverifiable owners remain. This maintenance action
does not activate playback, capture, plugins, or physical output.

Media imports and offline renders now use owner-described staging files before
atomic publication. Checkpoint 40 upgrades staging, media snapshots and isolated
plugin scratch to one internal version-2 owner manifest. The manifest is atomically
published and fsynced, binds boot/process-start identity to the exact filesystem
device/inode/kind, and directory-backed resources also sync their containing store.
Successful publication and ordinary failures remove both the stage and its ownership
evidence. If the process crashes, aggregate status reports residue using opaque IDs.
Acknowledged cleanup reloads the owner evidence and rechecks exact resource identity
immediately before deletion. Missing, malformed, legacy or replaced resources remain
`unknown-owner` and are never guessed away. Software fault injection covers fsync
failures and unclean process exit; physical storage/power-cut qualification remains
separate.
The native-backed changed-media test also verifies that rejection preserves
an existing export and leaves the playback generation unchanged.

## Arrangement loop control

The Production panel now accepts an explicit playback range and exposes play,
aligned-loop and stop controls together. Capture finish naming is kept inside that
panel, with explicit abort and status-refresh controls. Status refresh uses the
read-only `GET /api/v1/daw/production` projection so playback, capture, interrupted
recordings and the 192 kHz canonical rate arrive in one response. The projection
never arms hardware. Its frame-writing endpoints accept only non-negative, bounded
JSON integers; booleans, floats and numeric strings are rejected rather than
silently truncated.

Production transport/capture behavior now lives in a separately testable browser
module. All commands disable sibling production controls while a request is in
flight and report busy state to assistive technology. Abort asks for confirmation
before discarding a partial take. The shared request client is explicitly exported
to page modules, fixing a browser-only recovery-panel startup failure that the
former isolated harness did not expose. The release gate syntax-checks every
frontend JavaScript file, and a DOM harness covers initial status, range conversion,
loop submission, abort confirmation, busy state and control restoration.

Posting `{"action":"loop","beginFrame":256,"endFrame":768}` to
`/api/v1/daw/playback` restarts the selected range and enables repeated producer
submission. It does not merely change the loop range of the current playback.
The beginning must be non-negative, the end must be greater than the beginning,
and the length must be a multiple of 256 canonical (192 kHz) frames. Invalid ranges
are rejected before stopping the existing producer. `action: stop` stops playback
and the producer; `action: start` starts a new non-looping arrangement range.
The runtime acceptance test verifies repeated production and shutdown with outputs
disarmed. Arbitrary loop lengths and sample-exact software wrap position are complete; audible clicklessness on real output hardware remains a qualification item.

Arrangement start/stop operations are serialized. If a worker does not exit within
the one-second join timeout, stop reports an error and status exposes
`stopTimedOut: true`. Restart remains blocked while that worker is alive; cancellation
is not cleared. After the blocked operation returns, the worker exits and a later
stop/start can recover. This does not forcibly interrupt filesystem or native IPC
calls or establish a one-second upper bound on the complete stop request. Runtime
close still performs native cleanup before reporting a producer stop error.

## Pending recording takes

New recordings no longer overwrite existing filenames. Publication uses a hard link
within the media directory and fails if the destination name exists. The take stays
pending; enter a new WAV basename in Finish capture as and retry, or send
`{"action":"finish","fileName":"new-take.wav"}` to the capture API.
Successful publication with failed partial-file removal reports
`partialCleanupPending: true`; it is not treated as a failed recording. This requires
filesystem hard-link support. Offline export replacement behavior is unchanged.

Finish syncs completed WAV bytes before publication. Checkpoint 41 then creates the
non-replacing hard-link target and fsyncs the containing directory before success is
reported. A file-sync, publication or first directory-sync failure retains the sealed
partial take for retry; a newly linked target is removed best-effort if its directory
commit fails. After durable target publication, partial unlink and a second directory
sync make cleanup durable; failure there returns `partialCleanupPending: true` without
demoting the already durable recording. Interrupted-recording recovery uses the same
publication boundary. These software ordering/fault-injection checks do not qualify
physical storage power-cut behavior, which remains external evidence.

Capture start, finish and abort are serialized. A pending take must be finished or
aborted before another capture starts, even after automatic punch completion.
Finish/abort disarm capture and wait up to two seconds for the worker to exit.
If the worker remains alive, the request fails with `stopTimedOut: true` in status;
the spool and worker remain attached, and no WAV is published or deleted. Retry
finish/abort after the blocked operation returns. A block returned after cancellation
is discarded on abort. Finish instead consumes the available tail until an empty
queue is observed, with at most 65 blocks processed after its drain request.
This protects spool lifetime but does not forcibly interrupt native IPC or disk writes.
Runtime close still closes the native engine before reporting a capture stop error.
These cases use simulated capture blocks; live input and recording-rate qualification
remain open.

Capture read/processing/write exceptions set `state: failed` and `captureError`,
stop the worker, and request disarming. A failed disarm is recorded as `disarmError`;
status does not claim successful disarming. Finish refuses failed captures, retaining
the pending spool until abort. Sample arrays must match the declared frame count and
contain finite values; spool writes must contain exactly the declared PCM frames.
Only an `empty:` native queue response is retried. Fault-injection tests cover these
paths; recovery of partial recordings remains a backlog item.

Normal finish exposes `queueDrained: true` after observing the queue empty following
disarm. The bound allows the 64-block native queue plus one in-flight read. Exceeding
it fails capture and blocks publication. Punch completion still respects its end
boundary. Native recording disarm now closes an atomic submission gate and waits
for an admitted writer to publish before returning. With arm/disarm/pop serialized
on the native control thread, an empty observation after disarm has a stable queue
tail until rearm. This fences queue submission, not the complete device callback
or hardware input shutdown. The callback never waits for this gate; the control
thread yields while an admitted writer completes. Disarm has no fixed wall-clock
deadline if that writer is descheduled. Concurrent native regression coverage does
not substitute for latency measurements or sanitizer qualification on target systems.

## Partial recording recovery (Linux)

After restarting from an interrupted recording, POST
`{"action":"recover","fileName":".take-example.partial.wav"}` to
`/api/v1/daw/capture`, using the partial file's exact basename in the media directory.
Recovery requires no pending capture in this runtime and does not require a native
engine. Do not share the data directory with another running writer.
Only the engine's 44-byte PCM WAV header, stereo 32-bit integer / 192 kHz format
is supported. Complete frames present on disk are copied in bounded chunks into a
uniquely named `recovered-*.wav`; the partial source remains unchanged. Trailing
incomplete bytes are reported and excluded. Unsupported or absent headers cannot
be recovered by this path. Size/time changes during the copy cause rejection.
The receipt sets `continuityVerified: false`: buffered samples lost before the crash,
dropout metadata, original timeline placement and general WAV formats are not
reconstructed.

The DAW's Interrupted recordings panel provides Find interrupted recordings and
Recover copy controls. Discovery uses GET `/api/v1/daw/capture/recovery`, scans at
most 1,000 media-directory entries, and reports truncation. Candidates are validated
when recovery is requested; listing alone does not establish recoverability.
The panel renders filenames as text, disables repeat requests while busy, and shows
errors and recovered-copy details. Automated DOM-harness tests cover the interaction
logic. A local HTTP acceptance test also covers discovery, recovery, preserved source
bytes, output samples, invalid/missing paths and serving the panel script. Missing
files return a JSON validation error asking the user to refresh the list. Visual
browser qualification remains open.

The main operator page exposes a keyboard skip link, a consistent visible-focus
ring and polite live launcher feedback. `tests/test_ui_acceptance.py` checks unique
element IDs, explicit non-submitting buttons, status regions, focus/skip contracts
and the small-viewport shrink rules, then serves the actual HTML, CSS, JavaScript
and state API through the real loopback handler and verifies browser hardening
headers. Checkpoint 54 additionally runs the production assets in real Chromium at
1440×900, 1024×768, 768×1024 and 390×844; keyboard skip navigation, player selection
and a safe show-state edit pass with zero horizontal overflow. Managed Chromium still
blocks direct loopback navigation, so API fetches are bridged to the real handler.
This qualifies rendered/responsive reference behavior, not assistive technology or
deployed browser-to-LAN/TLS/IdP behavior.
