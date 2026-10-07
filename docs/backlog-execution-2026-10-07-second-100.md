# Second 100-entry backlog pass — 2026-10-07

This is a follow-on audit against merged main commit `8a46e4c`. It contains 100 operational backlog checks across ten domains. These audit IDs are not replacements for the repository's substantive backlog IDs.

## Disposition rules

- `Verified/documented` means repository or hosted software evidence exists.
- `Owner/external evidence required` means the software path is prepared but the required clean host, physical device, deployment, or measurement artifact is absent.
- `Owner decision/credential required` means the project owner must supply a license, certificate, notarization identity, licensed fixture, or release decision.
- No external qualification is inferred from CI.

| Audit ID | Domain | Check | Disposition |
| --- | --- | --- | --- |
| AUD2-001 | Source/reproducibility | main commit and parent binding | Verified/documented |
| AUD2-002 | Source/reproducibility | continuity record freshness | Verified/documented |
| AUD2-003 | Source/reproducibility | backlog workbook identity | Verified/documented |
| AUD2-004 | Source/reproducibility | 50-item ledger preservation | Verified/documented |
| AUD2-005 | Source/reproducibility | 100-entry audit preservation | Verified/documented |
| AUD2-006 | Source/reproducibility | no fabricated IDs | Verified/documented |
| AUD2-007 | Source/reproducibility | historical provenance retention | Verified/documented |
| AUD2-008 | Source/reproducibility | branch/PR baseline binding | Verified/documented |
| AUD2-009 | Source/reproducibility | commit signature visibility | Verified/documented |
| AUD2-010 | Source/reproducibility | diff hygiene | Verified/documented |
| AUD2-011 | CI/test | StageMesh CI trigger | Verified/documented |
| AUD2-012 | CI/test | Platform Modules trigger | Verified/documented |
| AUD2-013 | CI/test | Native Device Lifecycle trigger | Verified/documented |
| AUD2-014 | CI/test | desktop path filtering | Verified/documented |
| AUD2-015 | CI/test | Python suite record | Verified/documented |
| AUD2-016 | CI/test | native CTest record | Verified/documented |
| AUD2-017 | CI/test | compileall record | Verified/documented |
| AUD2-018 | CI/test | release-check entrypoint | Verified/documented |
| AUD2-019 | CI/test | expected-skip disclosure | Verified/documented |
| AUD2-020 | CI/test | failure triage path | Verified/documented |
| AUD2-021 | Desktop packaging | Windows NSIS artifact path | Owner/external evidence required |
| AUD2-022 | Desktop packaging | Windows MSI artifact path | Owner/external evidence required |
| AUD2-023 | Desktop packaging | offline WebView2 setting | Owner/external evidence required |
| AUD2-024 | Desktop packaging | WebView2 size disclosure | Owner/external evidence required |
| AUD2-025 | Desktop packaging | macOS bundle path | Owner/external evidence required |
| AUD2-026 | Desktop packaging | Linux AppImage path | Owner/external evidence required |
| AUD2-027 | Desktop packaging | Linux Debian path | Owner/external evidence required |
| AUD2-028 | Desktop packaging | manifest verification | Owner/external evidence required |
| AUD2-029 | Desktop packaging | SHA-256 index | Owner/external evidence required |
| AUD2-030 | Desktop packaging | SBOM/provenance binding | Owner/external evidence required |
| AUD2-031 | Windows | Windows 11 x64 target | Owner/external evidence required |
| AUD2-032 | Windows | clean-host install | Owner/external evidence required |
| AUD2-033 | Windows | NSIS install | Owner/external evidence required |
| AUD2-034 | Windows | MSI install | Owner/external evidence required |
| AUD2-035 | Windows | missing-WebView2 path | Owner/external evidence required |
| AUD2-036 | Windows | offline/no-network path | Owner/external evidence required |
| AUD2-037 | Windows | service boot | Owner/external evidence required |
| AUD2-038 | Windows | upgrade from prior version | Owner/external evidence required |
| AUD2-039 | Windows | uninstall residue | Owner/external evidence required |
| AUD2-040 | Windows | Windows signing | Owner decision/credential required |
| AUD2-041 | macOS | macOS 14 Apple Silicon target | Owner/external evidence required |
| AUD2-042 | macOS | bundle install | Owner/external evidence required |
| AUD2-043 | macOS | first-launch readiness | Owner/external evidence required |
| AUD2-044 | macOS | save/restart recovery | Owner/external evidence required |
| AUD2-045 | macOS | CoreAudio endpoint selection | Owner/external evidence required |
| AUD2-046 | macOS | CoreMIDI source discovery | Owner/external evidence required |
| AUD2-047 | macOS | MIDI hotplug | Owner/external evidence required |
| AUD2-048 | macOS | uninstall cleanup | Owner/external evidence required |
| AUD2-049 | macOS | notarization | Owner decision/credential required |
| AUD2-050 | macOS | Gatekeeper behavior | Owner decision/credential required |
| AUD2-051 | Linux | Ubuntu 22.04 x64 target | Owner/external evidence required |
| AUD2-052 | Linux | Ubuntu 24.04 x64 target | Owner/external evidence required |
| AUD2-053 | Linux | AppImage launch | Owner/external evidence required |
| AUD2-054 | Linux | Debian package install | Owner/external evidence required |
| AUD2-055 | Linux | service permissions | Owner/external evidence required |
| AUD2-056 | Linux | audio namespace | Owner/external evidence required |
| AUD2-057 | Linux | ALSA endpoint selection | Owner/external evidence required |
| AUD2-058 | Linux | MIDI enumeration | Owner/external evidence required |
| AUD2-059 | Linux | upgrade cleanup | Owner/external evidence required |
| AUD2-060 | Linux | repository/license notices | Owner/external evidence required |
| AUD2-061 | Audio/MIDI | Apogee BOOM playback | Owner/external evidence required |
| AUD2-062 | Audio/MIDI | Apogee BOOM capture | Owner/external evidence required |
| AUD2-063 | Audio/MIDI | 48 kHz reference | Owner/external evidence required |
| AUD2-064 | Audio/MIDI | 24-bit reference | Owner/external evidence required |
| AUD2-065 | Audio/MIDI | balanced TRS loopback | Owner/external evidence required |
| AUD2-066 | Audio/MIDI | aligned WAV measurement | Owner/external evidence required |
| AUD2-067 | Audio/MIDI | SNR measurement | Owner/external evidence required |
| AUD2-068 | Audio/MIDI | THD+N measurement | Owner/external evidence required |
| AUD2-069 | Audio/MIDI | FLkey Mini event delivery | Owner/external evidence required |
| AUD2-070 | Audio/MIDI | controller reconnect/soak | Owner/external evidence required |
| AUD2-071 | Security/network | loopback authentication | Verified/documented |
| AUD2-072 | Security/network | sidecar shutdown authentication | Verified/documented |
| AUD2-073 | Security/network | TLS proxy contract | Owner/external evidence required |
| AUD2-074 | Security/network | IdP integration | Owner/external evidence required |
| AUD2-075 | Security/network | firewall behavior | Owner/external evidence required |
| AUD2-076 | Security/network | authorization retention | Verified/documented |
| AUD2-077 | Security/network | HMAC rotation | Verified/documented |
| AUD2-078 | Security/network | rate policy | Verified/documented |
| AUD2-079 | Security/network | operation cost bounds | Verified/documented |
| AUD2-080 | Security/network | independent witness topology | Owner/external evidence required |
| AUD2-081 | UX/accessibility | operator workflow acceptance | Owner/external evidence required |
| AUD2-082 | UX/accessibility | responsive review | Owner/external evidence required |
| AUD2-083 | UX/accessibility | keyboard traversal | Owner/external evidence required |
| AUD2-084 | UX/accessibility | focus visibility | Owner/external evidence required |
| AUD2-085 | UX/accessibility | screen-reader labels | Owner/external evidence required |
| AUD2-086 | UX/accessibility | NVDA exercise | Owner/external evidence required |
| AUD2-087 | UX/accessibility | VoiceOver exercise | Owner/external evidence required |
| AUD2-088 | UX/accessibility | contrast review | Owner/external evidence required |
| AUD2-089 | UX/accessibility | reduced-motion review | Owner/external evidence required |
| AUD2-090 | UX/accessibility | error recovery messaging | Owner/external evidence required |
| AUD2-091 | Release/governance | Apache license decision | Owner decision/credential required |
| AUD2-092 | Release/governance | third-party notices | Owner decision/credential required |
| AUD2-093 | Release/governance | plugin license inventory | Owner decision/credential required |
| AUD2-094 | Release/governance | licensed Windows fixture | Owner decision/credential required |
| AUD2-095 | Release/governance | licensed macOS fixture | Owner decision/credential required |
| AUD2-096 | Release/governance | release signing credentials | Owner decision/credential required |
| AUD2-097 | Release/governance | notarization credentials | Owner decision/credential required |
| AUD2-098 | Release/governance | clean-host witness | Owner decision/credential required |
| AUD2-099 | Release/governance | release approval record | Owner/external evidence required |
| AUD2-100 | Release/governance | public release tag | Owner decision/credential required |

## Highest-value next actions

1. Run merged-main candidates on clean Windows 11 x64, macOS 14+ Apple Silicon, and Ubuntu 22.04/24.04 x64 hosts.
2. Use the Apogee BOOM with a 48 kHz/24-bit balanced-TRS loopback to produce aligned reference/capture WAV measurements.
3. Exercise FLkey Mini attach, event delivery, disconnect, reconnect, and topology-loss recovery.
4. Obtain signing/notarization credentials and make the project-license decision before publishing.
5. Reconcile resulting artifacts into the primary 50-item ledger and preserve all historical evidence.

## Hardware/testing dependencies

- Clean hosts: Windows 11 x64, macOS 14+ Apple Silicon, Ubuntu 22.04/24.04 x64.
- Audio: Apogee BOOM, USB-C data cable, two balanced 1/4-inch TRS cables, current firmware/control software, and a reference signal/capture path.
- MIDI: FLkey Mini and USB data cable.
- Evidence tools: SHA-256 utility, WAV measurement tooling, screen-reader/keyboard test setup, and a separate prior StageMesh version for real-upgrade testing.
