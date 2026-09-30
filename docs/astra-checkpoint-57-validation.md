# Astra checkpoint 57 validation — cross-platform device lifecycle reconciliation

Checkpoint 57 closes the shared reconnect/hotplug lifecycle seam that sits between checkpoint 56's persistence-grade identity contract and future Windows/macOS platform enumerators. It does **not** claim that WASAPI/CoreAudio/CoreMIDI enumeration or physical audio execution is implemented on those operating systems.

## Audio disconnect and identity replacement

The hotplug safety path no longer assumes Linux ALSA when deciding whether an active output must stop. If a selected endpoint disappears or its pinned persistent identity changes, any active execution backend is deactivated before reselection is considered. This is the behavior future WASAPI/CoreAudio adapters inherit automatically.

Reselection still never activates a physical stream. Strong persistent identity can select a replacement endpoint, but output/input activation remains an explicit recovery action.

## MIDI persistent rebind

`MidiIdentityStore` now treats discovery as observation rather than authority:

- once a logical native endpoint ID is pinned, a later device at that same native token cannot silently replace the stored physical identity;
- a strong persisted identity can resolve to exactly one newly enumerated native endpoint ID;
- duplicate persistent-identity matches are ambiguous and therefore cannot auto-rebind;
- weak/topology/volatile identities remain explicit-rebind-only.

The runtime uses that resolver for desired MIDI bindings. A show binding may therefore remain keyed to the original logical endpoint while the currently enumerated OS/native endpoint token changes. The native attach call uses the current endpoint token, but authoritative show intent is not silently rewritten.

On endpoint disappearance or same-token identity replacement, StageMesh detaches the unsafe MIDI input before any rebind attempt. MIDI hotplug state now publishes a bounded generation/change history analogous to the audio hotplug status and still reports `automaticActivation: false` and `physicalOutputsArmed: false`.

## Concurrency

Audio scans were already serialized. Checkpoint 57 adds the same scan serialization to MIDI enumeration/reconciliation so two polling/control callers cannot race attachment and identity decisions.

## Validation

- **31 focused audio/MIDI lifecycle and identity tests pass**, including non-ALSA stream stop, native-ID churn rebind, duplicate identity rejection, same-token identity replacement, disconnect detach and concurrent MIDI scan serialization.
- Fresh RT native CTest passes **2/2**; native source is unchanged from checkpoint 56.
- Release Python suite passes **600 tests with zero skips**.
- Automation-performance passes.
- All **126 schemas plus OpenAPI** parse.
- All **7 frontend JavaScript files** pass Node syntax checking.

## Remaining

Windows/macOS platform code still must enumerate real audio/MIDI endpoints and deliver change notifications/polling snapshots into these contracts. Physical audio negotiation/conversion, stream creation/teardown, CoreMIDI/Windows MIDI I/O, Windows UPPF named pipes, platform-native plugin launch binding and real-device qualification remain open.
