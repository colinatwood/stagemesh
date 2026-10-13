# Checkpoint 84: Windows hardware and installed-desktop evidence

Checkpoint 84 reconciles four private self-hosted Windows jobs into the
authoritative backlog without turning scoped observations into broad product or
hardware claims.

- Output-disarmed `safe-suite` run
  [38380829106](https://github.com/colinatwood/stagemesh-hardware-control/actions/runs/38380829106)
  passed against exact merged StageMesh source
  `467094294bf91fd926a7056011ba749179ede66a`.
- Live MIDI run
  [38423812244](https://github.com/colinatwood/stagemesh-hardware-control/actions/runs/38423812244)
  observed 446 FLkey events with zero queue drops.
- Physical hotplug run
  [38424849186](https://github.com/colinatwood/stagemesh-hardware-control/actions/runs/38424849186),
  attempt 2, restored all three initial devices, recorded two topology detaches,
  observed two post-reconnect events and reported zero queue drops.
- Installed-desktop keyboard run
  [38465282365](https://github.com/colinatwood/stagemesh-hardware-control/actions/runs/38465282365)
  passed for exact StageMesh source
  `bd9fb1519d2568a23b1659daeedfc7b4ccc85674`. Seven bounded synthetic key
  observations reached the skip link, Stage Editor and Show Control, with zero
  unnamed focusable controls. The evidence artifact digest is
  `sha256:e83fc741d0d588064d0b7cc0768aa8ec32a90fcc7450d57b07ee910fadf7e504`;
  `ui-keyboard-smoke.json` is
  `sha256:24875bca5feefe231cc2ecc7d9a6bde3e7391af30103bbeadf7add95afd70905`.

The installed unsigned online artifact ZIP was verified as
`sha256:9a0578eda1af4493fe38b0834a01a8d34a8891a72f28ed248a35c7aad26da056`;
its MSI was
`sha256:43ca83297d45a86cc8bfa8834671ee15d4a9f9dd1b5f8d263e90e4969135e132`.
The packaged executable is `stagemesh-desktop.exe`. The Windows clean-host
collector now detects that exact Tauri executable name instead of the obsolete
`StageMesh.exe` assumption.

DEV-035 moves from **Deferred** to **In Progress**. No row becomes Done.
The authoritative inventory remains **49 total / 25 open / 22 P0**: 24 Done,
8 In Progress, 11 Blocked and 6 Deferred. The updated workbook is
[StageMesh-Master-Backlog-Checkpoint-84.xlsx](backlog/StageMesh-Master-Backlog-Checkpoint-84.xlsx).

The evidence does not establish audible or recording quality, exact Windows
audio routing/loss behavior, repeated hotplug soak, controller latency/jitter,
screen-reader or status-announcement behavior, clean-host restart/upgrade/
uninstall, signing, licensed-plugin compatibility, deployed services or
full-engine integration. The keyboard input was synthetic, and the hotplug
operation deliberately retained `physicalHardwareQualified=false`.
