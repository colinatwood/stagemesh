# Native engine service loop design

The target audio streams are owner-thread objects. `prepare`, `start`,
`service`, `close`, and `stats` must run on the same thread that created the
stream. Windows requires `service()` to pump the WASAPI event handle; macOS
uses an asynchronous AUHAL callback but still requires the owner thread to
reconcile the execution fence and close the unit after callbacks drain.

The engine command loop currently blocks in `std::getline`, so a stream cannot
be created in that loop and serviced safely. The integration slice must use one
dedicated native I/O owner per engine instance (or one owner for all native
slots) with this contract:

1. The owner creates the `DeviceMonitor` snapshot and `DeviceExecutionFence`.
2. Activation is a bounded command copied into an owner queue. The owner pins
   the selected `DeviceRecord`, arms the fence, prepares the exact
   `NativeCaptureStream`, starts it, and publishes a status result.
3. While active, the owner calls `service(fence, wait_ms)` at a bounded cadence.
   It reconciles monitor revisions before each pass and closes the stream when
   the fence becomes disallowed.
4. The capture callback only copies packet metadata and borrowed samples into
   the existing bounded ingress helper. It never touches the fence, monitor,
   command queue, or engine command output.
5. Deactivation is another owner command. The owner marks the slot disabled,
   closes the stream, waits for callback drain through `close()`, then releases
   the fence and reports completion.
6. Shutdown first stops accepting commands, closes every stream on its owner,
   joins the owner, and only then destroys callback contexts.

The command response path must remain ordered and bounded. A response carries
the slot, operation, generation, backend, and failure reason. A fence loss is a
normal fail-closed result (`running=0`, `explicitRearmRequired=1`), not a
request to silently select another endpoint. Re-arming requires an explicit
control command after an exact attached or strong unique rebound resolution.

`NativeCaptureService` now owns this lifecycle boundary for one capture slot.
It keeps the monitor, fence, stream, callback context and close ordering
together; activation failures and fence loss fail closed and release the stream
before the authority object. The engine command loop still needs to construct
and drive this controller on a dedicated owner thread.

This controller is the prerequisite for wiring the shared capture ingress to
Windows and macOS. The endpoint source is excluded from the Linux engine build.
A Windows SDK cross-build checks compilation and linking; native Windows/macOS
execution remains required to validate this newer service boundary.

## Windows cross-build verification

The Linux workspace now has CMake, Ninja and MinGW-w64 installed. A complete
Windows-target cross-build of the root project reaches all engine, device,
capture, playback and selected-loss smoke binaries. The SDK headers available
to MinGW do not expose `CM_Register_Notification`, so the device monitor now
detects that API at configure time and builds a fail-closed topology monitor
without that optional MIDI notification hook. The target links `ksuser` for
the kernel-streaming format GUIDs used by audio preflight. The resulting PE
executables are compile/link evidence only. A prior Wine attempt could not
create its server socket in this workspace. The owner subsequently passed all
10 macOS native tests on merged main for PR #37; that validates main components,
not this newer service boundary or full-engine capture integration.
