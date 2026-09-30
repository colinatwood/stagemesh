# Astra checkpoint 56 validation — cross-platform persistence-grade audio/MIDI identity contract

Checkpoint 56 defines how future Windows/macOS device adapters may participate in StageMesh's existing fail-closed reconnect/rebind lifecycle. It is a **contract foundation**, not a claim that Windows/macOS hotplug or audio streaming is implemented.

## Audio identity

`describe_audio_device()` now accepts platform-specific privacy-preserving identity evidence:

- `backend: wasapi` + `stableIdHash` produces `identityStrength: os-stable-endpoint` and may be automatically reconnected.
- A WASAPI `instanceIdHash` without a StableId is only `installation-snapshot`; it has a correlation identity but `automaticReconnectEligible: false`.
- `backend: coreaudio` + `uidHash` produces an OS-stable endpoint identity eligible for reconnect.
- Raw identifiers are never accepted in the hash fields; malformed/unhashed tokens remain volatile.

Microsoft documents that ordinary audio endpoint IDs are tied to the device installation and can change across driver/OS updates, while Windows 11 24H2 adds `PKEY_AudioEndpoint_StableId` as the more durable endpoint identity. Checkpoint 56 therefore refuses to elevate the checkpoint-55 snapshot hash into automatic reconnect authority.

Apple documents CoreAudio device UIDs as persistent identifiers; StageMesh consumes only a SHA-256 hash so private UID material is not exposed through the runtime's device state. Mutable endpoint properties still have to be re-read after identity resolution.

## MIDI identity

`describe_midi_device()` now accepts:

- CoreMIDI `uniqueIdHash` / `connectionUniqueIdHash` as persistence-grade hashed identity. Apple documents `kMIDIPropertyUniqueID` as the system-assigned unique identifier for devices/entities/endpoints.
- Windows MIDI `persistentIdHash` only when the future platform adapter also sets `persistentIdentityVerified: true`. A merely present token is not enough to authorize automatic rebind.

All of these identities feed the existing stores, which already reject ambiguous duplicate matches and refuse to replace pinned identities from observation alone.

## Validation

- **15 focused audio/MIDI identity tests pass**, including six new cross-platform strength/privacy cases.
- Release Python suite passes **584 tests with zero skips**.
- Fresh RT native CTest remains **2/2**; native source is unchanged from checkpoint 55.
- Automation-performance passes.
- All **126 schemas plus OpenAPI** parse.
- All **7 frontend JavaScript files** pass Node syntax checking.

## Remaining

Windows/macOS endpoint enumeration must still feed these identity fields from real platform APIs. Hotplug notifications/polling, disconnect-triggered stream stops, conservative reselection, physical audio negotiation/conversion and real-device qualification remain open.
