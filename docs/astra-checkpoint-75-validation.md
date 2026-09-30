# Astra Checkpoint 75 validation

Checkpoint 75 adds privacy-preserving persistent endpoint identity and conservative
reconciliation to the native Windows/macOS device lifecycle layer.

## Successful hosted gate

Source head `8028ac5005e81ddd6f69a8df2bfed0a28ee7e313` passed all three GitHub workflows:

- generic CI: run `34881629544`
- StageMesh Platform Modules: run `34881629490`
- StageMesh Native Device Lifecycle: run `34881629489`

The native lifecycle matrix passed on Windows Server 2025 x64 and Apple Silicon
macOS 14.8.9. The macOS build/test used AddressSanitizer.

### macOS evidence

Artifact digest:
`sha256:08ed7bea660a89e1140eb02bfc96dac8775987d5c1e1a7f735b78bd7b8433d03`

The evidence reports:
- 25 lifecycle cycles passed
- 3 baseline CoreAudio devices with strong hashed identities
- CoreAudio software aggregate-device add/remove/recreate notifications observed
- CoreMIDI virtual-source add/remove/recreate notifications observed
- detach on removal and exact-unique identity recovery after recreate passed for
  both CoreAudio and CoreMIDI
- topology revision reached 11
- `physicalOutputsArmed=false`
- `physicalHardwareQualified=false`
- `audioStreamingQualified=false`
- `physicalHotplugQualified=false`

### Windows evidence

Artifact digest:
`sha256:6b3902bed5602f5b9ccf73307d33c518cbbf80910a43605780b7398f59e3f6dd`

The evidence reports:
- 25 lifecycle cycles passed
- deterministic identity reconciliation contract passed
- no active audio endpoints were present on the hosted runner
- `stableIdentityApiCompiled=false` because the runner's SDK 26100 does not expose
  the newer `PKEY_AudioEndpoint_StableId` header symbol
- no live Windows endpoint identity or notification-delivery claim is made
- all physical/audio-stream qualification fields remain false

## Bugs found by target-OS CI

Checkpoint development intentionally retained failures until their causes were
identified:

1. CoreMIDI removal initially timed out because notification delivery uses the
   run loop that created the MIDI client. The bounded wait now services that run
   loop rather than sleeping through it.
2. The CoreAudio aggregate fixture crashed under ASan because the C API aggregate
   dictionary keys are C strings and must be wrapped in `CFSTR(...)` before being
   passed to CoreFoundation.
3. Windows Server 2025 CI uses Windows SDK 26100, whose headers do not contain the
   newer StableId property symbol. CMake now feature-detects that API; fallback
   identity remains installation-scoped and refuses automatic rebind.
4. Windows endpoint UTF-16 to UTF-8 conversion allocated the wrong size for the
   terminating NUL. The buffer handling now allocates the full converted size and
   removes the NUL afterward.

## Claim boundary

This checkpoint qualifies native software topology event delivery and strong
identity recovery on macOS software fixtures. It does not qualify physical
hotplug, a physical audio device, audio streaming, Windows live StableId retrieval,
or the full StageMesh engine's stream-fencing/rearm behavior.

The remaining device software work is integration of these observations and
reconciliation decisions into the full engine lifecycle. WASAPI/CoreAudio stream
negotiation and stream loss handling remain separate audio rows.
