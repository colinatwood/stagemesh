# Astra checkpoint 55 validation — Windows/macOS audio endpoint and installed-driver evidence adapters

Checkpoint 55 closes the remaining **software evidence-adapter** seam in driver diagnostics without changing platform support claims. The existing USB inventory remains intact; Windows and macOS gain separate read-only audio endpoint/driver evidence that fails closed and preserves identifier privacy.

## Windows evidence contract

The Windows probe is a fixed, read-only PowerShell command. It inventories present `AudioEndpoint` PnP objects and `Win32_PnPSignedDriver` records whose device class is `MEDIA`. The response exports friendly/status data plus SHA-256 hashes of opaque endpoint/device identifiers. Full PnP instance IDs and serial-bearing suffixes are not returned. When a USB VID/PID can be safely extracted, it is normalized to `USB:VVVV:PPPP`.

Installed driver provider, version, INF name, signature state and signer are reported as **installed OS evidence**. They are deliberately separate from the reviewed package catalog. An installed driver never becomes a reviewed package match merely because version/provider strings look similar.

Microsoft documents MMDevice endpoint properties and notes that ordinary endpoint IDs can change after OS/driver updates; Windows 11 24H2 adds `PKEY_AudioEndpoint_StableId`. Checkpoint 55 does not claim to retrieve that StableId: the exported hash is explicitly a snapshot correlation token.

## macOS evidence contract

The macOS adapter reads `system_profiler SPAudioDataType -json -detailLevel mini`. Parsing is intentionally tolerant because `system_profiler` field names vary by release. When available, StageMesh reports device name, manufacturer, transport and input/output channel hints. CoreAudio device UID material is hashed before export.

The corresponding driver evidence is `coreaudio-device-present` with package semantics set to `not-applicable-no-windows-style-package-claim`. StageMesh does not manufacture INF/package/version concepts for CoreAudio. Apple documents persistent CoreAudio device UID/model UID concepts and HAL plug-ins; actual host execution remains required before claiming platform support.

## Failure isolation

Endpoint probing is independent of the existing USB inventory. If the audio endpoint/driver probe fails, the report keeps any usable USB inventory and sets `endpointIssues` plus `scanStatus: partial-or-unavailable`. No probe opens an audio stream, mutates a device, installs a driver or arms physical outputs.

## Validation

- 19 focused audio-endpoint/hardware-diagnostics/driver-catalog tests pass before the broad gate.
- A fresh Release build with RT qualification passes **2/2 native CTest targets**.
- The release Python suite passes **578 tests with zero skips** against that engine.
- Automation-performance passes.
- All **126 JSON schemas plus OpenAPI** parse successfully.
- All **7 frontend JavaScript files** pass Node syntax checking.

## Remaining qualification

This checkpoint does **not** claim that the probes have run on Windows or macOS hardware. Real host execution, installed-driver correlation, persistent identity/hotplug behavior, physical audio negotiation/conversion and named-hardware qualification remain open.
