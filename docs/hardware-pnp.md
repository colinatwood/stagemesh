# Hardware discovery and driver assistance

This increment prepares PnP diagnosis without requiring bench hardware. In the
Compatibility panel, select **Scan hardware and find drivers**. The scan runs on
the server host, not the browser's computer. Rescan after connecting or removing
a device. The command-line equivalent is:

```sh
python3 scripts/stagemesh-hardware-doctor.py
```

`GET /api/v1/hardware/diagnostics` returns a fresh, read-only USB inventory, host OS,
release and architecture, hardware VID/PID, available driver binding/error,
diagnostic next steps, and online lookup links. It does not open audio streams,
alter routes, install drivers, or arm outputs. Existing qualification remains separate.

## Platform coverage

| Host | Inventory | Driver diagnosis |
| --- | --- | --- |
| Linux | sysfs USB devices and composite interfaces | Bound interface driver names; unavailable sysfs reported explicitly |
| Windows | Fixed PowerShell USB + AudioEndpoint queries | USB service/error plus separately reported signed MEDIA-driver provider/version/INF/signature evidence |
| macOS | `system_profiler` USB + Audio JSON | CoreAudio device presence/UID-hash/manufacturer/transport evidence; no Windows-style package claim |

Checkpoint 55 extends the Windows/macOS fixture adapters with audio endpoint/installed-driver evidence. They have not been exercised on those operating systems. Linux remains the application's supported release
target. Adding discovery adapters does not establish full cross-platform audio
engine support. Serial numbers are excluded. Connection-port/snapshot identities
are not persistent MIDI mapping keys. PCI, Thunderbolt-native, network, LE Audio
capability and UWB radio identification need dedicated adapters. A USB radio
appearing in this list does not establish BAP support or clock synchronization.


### Endpoint and installed-driver evidence

Checkpoint 55 adds `audioEndpoints`, `audioDrivers` and `endpointIssues` to the existing diagnostics response. These fields are read-only evidence, never stream authority.

On Windows, StageMesh runs a fixed PowerShell inventory for present `AudioEndpoint` devices and signed `MEDIA` PnP drivers. Full endpoint/PnP instance strings are not exported: StageMesh emits one-way SHA-256 hashes plus safe USB VID/PID when derivable. Installed provider/version/INF/signature metadata is explicitly `installed-os-evidence-not-reviewed-package-catalog`; it never inherits reviewed-catalog status and never authorizes installation. The endpoint hash is a snapshot correlation aid, not a claim that StageMesh retrieved Windows 11 `PKEY_AudioEndpoint_StableId`.

On macOS, StageMesh runs `system_profiler SPAudioDataType -json` and normalizes device name, manufacturer, transport and channel hints when the host reports them. A reported CoreAudio UID is hashed before export. The matching driver-evidence record says `coreaudio-device-present` and deliberately has no package version/INF semantics. Apple CoreAudio device/plugin identity is therefore represented as OS-native evidence rather than translated into a Windows package model.

Probe failure is isolated: USB inventory may remain usable while `endpointIssues` reports the missing audio-endpoint evidence. All endpoint/driver evidence remains `qualified: false`.

## Internet driver workflow

Links open only when selected. Windows gets an exact VID/PID Microsoft Update
Catalog search; Linux/macOS get a VID/PID search restricted to kernel.org or
support.apple.com. Official OS audio guidance is available even without hardware.
The application does not fetch, rank or verify search results automatically.
Searches send only VID/PID; no serial, host name or full inventory. Results can be
empty. Missing bindings can also reflect disabled devices or probe limitations,
so the scan does not automatically diagnose a missing driver.

Each discovered entry now has `driverCompatibility`. Bound Linux/Windows USB class
drivers are reported as class-driver evidence. Search links are always marked as
unverified matches. A curated catalog can supply package metadata only when hardware
ID, OS name, exact OS release and architecture all match. Checkpoints 43 and 52 add a
small reviewed bundled set for RME Babyface Pro FS proprietary USB mode plus Focusrite
Scarlett Solo/2i2/4i4 4th Gen Windows x64 package metadata; every
v2 entry carries review/expiry dates, confidence and multi-source provenance. Expired
records become `curated-match-review-stale`, while legacy entries without review
evidence become `curated-match-unreviewed`. Catalog records are not live publisher
signatures, never permit automatic installation and still require hardware tests.

Before choosing a package, verify its exact hardware IDs, OS release, CPU
architecture, firmware requirements and publisher against the official OS or
manufacturer documentation. A model-specific vendor support catalog is future
work; arbitrary download sites are not treated as trusted publishers. Install
through the OS/vendor's supported process, then rescan and test application access.

Microsoft documents its in-box USB Audio 2 driver and topology/format limits:
https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/usb-2-0-audio-drivers

Linux driver configuration reference:
https://docs.kernel.org/sound/alsa-configuration.html

Apple Audio MIDI Setup guide:
https://support.apple.com/guide/audio-midi-setup/welcome/mac

Sources checked/reviewed through 2026-09-13. This is lookup/package-metadata guidance, not a compatibility certification.

## Validation of this increment

On 2026-09-11, a fresh qualification-enabled CMake Release build passed both
native CTest targets. Against that engine, all 324 Python tests passed with no
skips, including the new diagnostic fixtures and HTTP endpoint. Frontend
JavaScript syntax passed; all 105 schema files parsed (not full JSON Schema
instance validation). The local CLI correctly reported unavailable USB sysfs.
An initial API run selected an older workspace binary and failed an existing
audit endpoint test; the fresh-engine run resolved that failure. No physical
devices, Windows/macOS hosts, driver packages or live browser interactions were
tested. ABI 1.67 and engine handshake 5.0 remain unchanged.

## Remaining PnP work

An explicit Linux audio constraint preflight is now available; see
[audio preflight](audio-preflight.md). Activation integration and actual negotiated
parameter reporting remain unfinished.

Next: native audio endpoint capability negotiation (rates, formats, channels,
exclusive access), permission diagnostics, persistent identities, and hotplug
events integrated with mapping preservation and explicit stream recovery. Never
assume a discovered USB device supports 192 kHz or 32-bit physical conversion.
The engine's canonical format is separate from the device's negotiated format.
Then validate real hardware using `qualification/README.md`. Universal device
support cannot be guaranteed by inventory or driver installation alone.

Checkpoint 53 adds `stagemesh-driver-catalog-audit.py`, an offline review-freshness
report. It never contacts vendors or refreshes evidence automatically; it tells the
operator which reviewed records are approaching expiry or have become stale so a
new human/vendor evidence review can happen deliberately.
