# Third 100-entry executable-readiness pass — 2026-10-07

This runbook records 100 concrete execution checks against merged main commit `765edca`. These are operational audit entries, not fabricated replacements for the substantive backlog IDs.

## Status rules

- **CI/software evidence verified:** supported by repository or hosted software evidence.
- **Prepared; external exercise pending:** the software path exists, but the target host, device, or assistive technology still must be exercised.
- **External host/device/owner evidence required:** cannot be closed in hosted CI.

| Entry | Domain | Check | Status |
| --- | --- | --- | --- |
| EX3-001 | Windows install | download exact candidate | CI/software evidence verified |
| EX3-002 | Windows install | verify release index | CI/software evidence verified |
| EX3-003 | Windows install | verify archive paths | CI/software evidence verified |
| EX3-004 | Windows install | install NSIS online | External host/device/owner evidence required |
| EX3-005 | Windows install | install NSIS offline | External host/device/owner evidence required |
| EX3-006 | Windows install | install MSI online | External host/device/owner evidence required |
| EX3-007 | Windows install | install MSI offline | External host/device/owner evidence required |
| EX3-008 | Windows install | missing WebView2 path | External host/device/owner evidence required |
| EX3-009 | Windows install | existing WebView2 path | Prepared; external exercise pending |
| EX3-010 | Windows install | uninstall residue | External host/device/owner evidence required |
| EX3-011 | macOS install | download exact candidate | CI/software evidence verified |
| EX3-012 | macOS install | verify bundle digest | CI/software evidence verified |
| EX3-013 | macOS install | install on Apple Silicon | External host/device/owner evidence required |
| EX3-014 | macOS install | first launch | External host/device/owner evidence required |
| EX3-015 | macOS install | permission prompts | External host/device/owner evidence required |
| EX3-016 | macOS install | save/restart | External host/device/owner evidence required |
| EX3-017 | macOS install | sidecar relaunch | External host/device/owner evidence required |
| EX3-018 | macOS install | uninstall cleanup | External host/device/owner evidence required |
| EX3-019 | macOS install | Gatekeeper assessment | External host/device/owner evidence required |
| EX3-020 | macOS install | notarization readiness | External host/device/owner evidence required |
| EX3-021 | Linux install | download AppImage | External host/device/owner evidence required |
| EX3-022 | Linux install | verify AppImage digest | CI/software evidence verified |
| EX3-023 | Linux install | launch on Ubuntu 22.04 | External host/device/owner evidence required |
| EX3-024 | Linux install | launch on Ubuntu 24.04 | External host/device/owner evidence required |
| EX3-025 | Linux install | install Debian package | External host/device/owner evidence required |
| EX3-026 | Linux install | service permissions | External host/device/owner evidence required |
| EX3-027 | Linux install | save/restart | External host/device/owner evidence required |
| EX3-028 | Linux install | uninstall cleanup | External host/device/owner evidence required |
| EX3-029 | Linux install | desktop entry | External host/device/owner evidence required |
| EX3-030 | Linux install | library dependency report | External host/device/owner evidence required |
| EX3-031 | Runtime/sidecar | authenticated startup | CI/software evidence verified |
| EX3-032 | Runtime/sidecar | readiness response | CI/software evidence verified |
| EX3-033 | Runtime/sidecar | authenticated shutdown | CI/software evidence verified |
| EX3-034 | Runtime/sidecar | graceful sidecar exit | CI/software evidence verified |
| EX3-035 | Runtime/sidecar | bounded force fallback | CI/software evidence verified |
| EX3-036 | Runtime/sidecar | unexpected sidecar exit | CI/software evidence verified |
| EX3-037 | Runtime/sidecar | restart recovery | CI/software evidence verified |
| EX3-038 | Runtime/sidecar | port collision | CI/software evidence verified |
| EX3-039 | Runtime/sidecar | malformed request | CI/software evidence verified |
| EX3-040 | Runtime/sidecar | log redaction | CI/software evidence verified |
| EX3-041 | Persistence | create template | CI/software evidence verified |
| EX3-042 | Persistence | edit template | CI/software evidence verified |
| EX3-043 | Persistence | publish template | CI/software evidence verified |
| EX3-044 | Persistence | reload template | CI/software evidence verified |
| EX3-045 | Persistence | restart recovery | Prepared; external exercise pending |
| EX3-046 | Persistence | atomic write | CI/software evidence verified |
| EX3-047 | Persistence | parent durability | CI/software evidence verified |
| EX3-048 | Persistence | temporary cleanup | CI/software evidence verified |
| EX3-049 | Persistence | corrupt file recovery | Prepared; external exercise pending |
| EX3-050 | Persistence | schema compatibility | Prepared; external exercise pending |
| EX3-051 | Audio engine | device enumeration | CI/software evidence verified |
| EX3-052 | Audio engine | default endpoint selection | Prepared; external exercise pending |
| EX3-053 | Audio engine | explicit endpoint selection | Prepared; external exercise pending |
| EX3-054 | Audio engine | missing endpoint fail-closed | CI/software evidence verified |
| EX3-055 | Audio engine | playback lifecycle | CI/software evidence verified |
| EX3-056 | Audio engine | capture lifecycle | CI/software evidence verified |
| EX3-057 | Audio engine | execution fence | CI/software evidence verified |
| EX3-058 | Audio engine | topology loss | Prepared; external exercise pending |
| EX3-059 | Audio engine | rearm | Prepared; external exercise pending |
| EX3-060 | Audio engine | owner-thread close | CI/software evidence verified |
| EX3-061 | Audio evidence | 48 kHz reference | External host/device/owner evidence required |
| EX3-062 | Audio evidence | 24-bit reference | External host/device/owner evidence required |
| EX3-063 | Audio evidence | BOOM playback | External host/device/owner evidence required |
| EX3-064 | Audio evidence | BOOM capture | External host/device/owner evidence required |
| EX3-065 | Audio evidence | balanced TRS loopback | External host/device/owner evidence required |
| EX3-066 | Audio evidence | aligned WAVs | External host/device/owner evidence required |
| EX3-067 | Audio evidence | SNR metric | External host/device/owner evidence required |
| EX3-068 | Audio evidence | THD+N metric | External host/device/owner evidence required |
| EX3-069 | Audio evidence | continuity metric | External host/device/owner evidence required |
| EX3-070 | Audio evidence | measurement artifact review | External host/device/owner evidence required |
| EX3-071 | MIDI | FLkey discovery | Prepared; external exercise pending |
| EX3-072 | MIDI | callback event | Prepared; external exercise pending |
| EX3-073 | MIDI | event queue bound | CI/software evidence verified |
| EX3-074 | MIDI | attach | CI/software evidence verified |
| EX3-075 | MIDI | detach | CI/software evidence verified |
| EX3-076 | MIDI | reconnect | Prepared; external exercise pending |
| EX3-077 | MIDI | topology loss | Prepared; external exercise pending |
| EX3-078 | MIDI | identity reconciliation | CI/software evidence verified |
| EX3-079 | MIDI | shutdown | CI/software evidence verified |
| EX3-080 | MIDI | physical hotplug evidence | External host/device/owner evidence required |
| EX3-081 | Accessibility | keyboard navigation | Prepared; external exercise pending |
| EX3-082 | Accessibility | focus order | Prepared; external exercise pending |
| EX3-083 | Accessibility | visible focus | Prepared; external exercise pending |
| EX3-084 | Accessibility | screen-reader names | Prepared; external exercise pending |
| EX3-085 | Accessibility | NVDA run | External host/device/owner evidence required |
| EX3-086 | Accessibility | VoiceOver run | External host/device/owner evidence required |
| EX3-087 | Accessibility | high contrast | Prepared; external exercise pending |
| EX3-088 | Accessibility | reduced motion | Prepared; external exercise pending |
| EX3-089 | Accessibility | error announcement | Prepared; external exercise pending |
| EX3-090 | Accessibility | responsive review | Prepared; external exercise pending |
| EX3-091 | Security/release | loopback auth | CI/software evidence verified |
| EX3-092 | Security/release | TLS proxy | External host/device/owner evidence required |
| EX3-093 | Security/release | IdP integration | External host/device/owner evidence required |
| EX3-094 | Security/release | firewall behavior | External host/device/owner evidence required |
| EX3-095 | Security/release | audit retention | CI/software evidence verified |
| EX3-096 | Security/release | HMAC rotation | CI/software evidence verified |
| EX3-097 | Security/release | rate policy | CI/software evidence verified |
| EX3-098 | Security/release | SBOM binding | CI/software evidence verified |
| EX3-099 | Security/release | signing certificate | External host/device/owner evidence required |
| EX3-100 | Security/release | license and notices | External host/device/owner evidence required |

## Required evidence kit

- Clean Windows 11 x64, macOS 14+ Apple Silicon, and Ubuntu 22.04/24.04 x64 hosts.
- Apogee BOOM, USB-C data cable, two balanced 1/4-inch TRS cables, current firmware/control software, and a reference signal/capture path.
- FLkey Mini with USB data cable.
- NVDA on Windows and VoiceOver on macOS.
- A distinct prior StageMesh version for real-upgrade testing.
- Signing certificates, Apple notarization credentials, license decision, and third-party notices.

## Handoff rule

Do not mark an external entry complete until the exact host/device identity, source commit, package digest, procedure output, and reviewer/witness record are preserved. Hosted CI remains software evidence only.
