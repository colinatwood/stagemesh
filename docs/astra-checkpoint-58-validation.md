# Astra checkpoint 58 validation — backend-neutral physical audio execution fencing

Checkpoint 58 removes remaining Linux-only assumptions from the shared physical-audio runtime without pretending that WASAPI or CoreAudio execution is implemented. The platform adapters are still absent; the common state machine is now ready to treat them correctly when they arrive.

## Backend-neutral execution state

Physical audio execution is now recognized by capability, not by the literal string `alsa`. ALSA, future WASAPI/CoreAudio and other explicit physical backends share the same rules, while `none`, `bridge-only`, `null` and `null-audio` remain non-physical.

For output activation:

- a running non-null physical backend is reported active;
- StageMesh immediately rescans/revalidates the selected persistent identity after stream start;
- if the endpoint disappeared or no longer resolves, the just-started stream is stopped and activation fails;
- post-promotion physical-output evidence is marked only after that identity fence passes.

Input activation applies the same post-start revalidation and stop-on-loss behavior.

`audio_stream_status()` and input status use the same physical-backend classification, so future platform backends will not be falsely reported inactive and the built-in null engine will not be falsely reported as armed physical audio.

## Platform preflight boundary

The existing preflight implementation is specifically an ALSA numeric-hardware constraint probe. Checkpoint 58 makes this boundary explicit:

- absent/legacy backend metadata continues to use the existing ALSA probe for compatibility;
- an explicit non-ALSA backend fails before activation with a clear platform-preflight-adapter error;
- no WASAPI/CoreAudio support is inferred from the shared runtime changes.

A future platform adapter must supply its own exact configured/requested parameter evidence before physical stream activation can be enabled.

## Validation

- **23 focused audio runtime/hotplug/recovery tests pass**, including simulated WASAPI output state, CoreAudio input loss after start, explicit missing-platform-preflight failure and backend-neutral unsafe stream stop.
- Release Python suite passes **604 tests with zero skips**.
- Fresh RT native CTest remains **2/2**; native source is unchanged from checkpoint 56.
- Automation-performance passes.
- All **126 schemas plus OpenAPI** parse.
- All **7 frontend JavaScript files** pass Node syntax checking.

## Remaining

Windows/macOS still need real platform endpoint enumeration, change notifications, exact preflight/configuration evidence, physical stream open/close and conversion integration. Windows UPPF named-pipe transport, Windows/macOS plugin verified-launch binding and real platform/hardware qualification remain open.
