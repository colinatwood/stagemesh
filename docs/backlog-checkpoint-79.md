# Checkpoint 79: native playback and Windows MIDI discovery

[Master backlog](backlog/StageMesh-Master-Backlog-Checkpoint-79.xlsx) remains
**25 open / 22 P0**: four software, 19 qualification, two decisions.
No status or acceptance criterion was changed. PLUG-034 stays Done and licensed
compatibility stays separate. Workbook checks preserved eight sheets, three
tables, one chart and 63 formulas; totals were recalculated and sheets rendered.

`NativePlaybackStream` owns pinned, exact float32 playback through IAudioClient3
on Windows and AUHAL on macOS. It configures and reads back the client format;
the existing device rate/period must already match. It does not change global
device settings or silently convert rate/channels. Missing identity, stale fence,
wrong direction, unsupported conversion and nonexact configuration fail closed.

macOS callbacks use atomic permission and notification epochs. Native stop drains
in-flight callbacks before configuration/context teardown. A conservative policy
fences all prepared streams when any watched topology/device property changes.
The caller must service the stream regularly to complete native shutdown;
notifications never automatically rearm or substitute another endpoint.

Windows MIDI inventory uses WinMM plus Configuration Manager PnP notification
registration. Driver interface paths are hashed and treated as installation
identities, never sufficient for automatic rebind. Index/name fallback identities
are volatile and invalidated by notified topology changes. No raw device names
or paths are included in evidence.

## Hosted validation

Code revision `34fd5cfa134ba2bb2fe011d2c50143e91c12812a` passed all six checks.
[Native run 34925110894](https://github.com/colinatwood/stagemesh/actions/runs/34925110894)
records test merge `456e4cd3e773d75eb8f17b57ce7a17eeffaccd08` and exact source and
binary hashes. Five CTests per OS passed. Reports are archived in
`docs/evidence/checkpoint-79/`.

- macOS arm64/ASan: native AUHAL callbacks at verified 48,000 Hz, 512 frames,
  two-channel float32; 19 callbacks / 9,728 frames in the evidence execution.
  Disarm stops native I/O; callbacks stop accessing context after shutdown;
  explicit rearm restarts. Creating a software aggregate device produces a real
  OS topology notification which stops the active stream. The tested output is
  silence. These are native callbacks, not manual AudioUnitRender calls.
- Windows: the WASAPI adapter compiles and missing-endpoint/lifecycle checks
  pass. Zero audio endpoints were present, so no live WASAPI I/O is claimed.
  WinMM enumerated one weak-identity MIDI endpoint. PnP registration and teardown
  passed over 25 monitor cycles; no native Windows PnP event was observed.
- A read-only availability probe reports hosted macOS microphone authorization
  as authorized. It did not request permission or capture audio. Capture stream
  ownership remains the next software slice.

The tests do not qualify selected-device physical loss, hardware clocks/timing,
audible output, conversion quality, real products or the full engine. Full-engine
integration needs the unavailable Checkpoint 69 takeover source; see
[remaining data requirements](remaining-data-requirements.md).

API references: [IAudioClient3 initialization](https://learn.microsoft.com/en-us/windows/win32/api/audioclient/nf-audioclient-iaudioclient3-initializesharedaudiostream),
[AUHAL](https://developer.apple.com/library/archive/technotes/tn2091/_index.html),
[WinMM interface query](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/drv-querydeviceinterface).
