# StageMesh desktop installation and hardware prerequisites

StageMesh is distributed as a native desktop executable. The website is only
the product overview and download page.

## Installer formats

The release workflow builds the platform-native bundles:

- Windows: NSIS setup executable and MSI
- macOS: application bundle and DMG
- Linux: AppImage and Debian package

Each bundle contains the local StageMesh API runtime and the matching native
engine. Startup is fail-closed: the desktop window opens only after an
authenticated loopback health check succeeds. No public network listener is
created.

Current CI installers are unsigned and are for development and controlled
testing only. Public desktop publication remains blocked until the owner
selects platform signing providers and the Linux package-signing policy,
configures protected credentials, verifies the exact signed artifacts, and
completes the separate legal and clean-host gates.

The historical `v0.1.0-alpha1` through `v0.1.0-alpha3` GitHub releases predate
the current StageMesh desktop pipeline and are not current Windows, macOS, and
Linux desktop installers. Use artifacts from the `StageMesh Desktop` workflow
for controlled testing and pair the three platform artifacts with the
commit-specific release-candidate index.

Each CI artifact includes `SHA256SUMS`, `desktop-artifacts.json`, and a
self-contained `verify-download.py`. After downloading and extracting one
platform artifact, verify the complete bundle before running an installer:

```sh
python verify-download.py --directory .
```

The verifier rejects missing, changed, or unexpected files; cross-checks the
manifest and checksum list; and binds `signing-verification.json` to the exact
manifest when that report is present. The JSON inventory records the
product version, source commit, platform, byte count, and SHA-256 digest for every packaged file;
it also preserves the explicit unsigned, clean-host, and physical-hardware
qualification boundaries.

Because the verifier and checksums arrive in the same download, a pass detects
corruption and inconsistent contents but does not authenticate the publisher.
Only execute the bundled script when you already trust the download channel;
otherwise use trusted system checksum tooling and obtain expected digests over
a separate trusted channel. Use platform signature verification for publisher
authenticity. A pass is not signing, notarization, legal, clean-host,
accessibility, or physical audio/MIDI qualification.

The Node and Rust desktop dependency graphs are pinned by committed lockfiles.
CI verifies `Cargo.toml` against `Cargo.lock` with Cargo's locked mode before
building on each operating system. This improves repeatability but is not a
claim of bit-for-bit reproducible installers or a substitute for dependency
license review.

## Windows

The Windows installer bundles the WebView2 Evergreen offline installer.
This adds about 127 MB to the Windows packages, but lets the installer set up
WebView2 without internet access when the runtime is missing. Windows 10
(version 1803 and later) and Windows 11 normally include WebView2; when a
compatible runtime is present, it remains managed and updated by Windows.

For audio and MIDI:

- Class-compliant USB MIDI devices use Windows' built-in MIDI support.
- Install the manufacturer's current driver for non-class-compliant interfaces.
- ASIO support is an explicit adapter milestone; the desktop shell does not
  claim ASIO qualification yet.
- The installer does not silently install vendor audio drivers.

### Windows clean-host evidence

The Windows CI bundle contains `windows-clean-host.py`. It records the exact
manifest and installer hashes, a hashed machine/user identity, Windows 11
build and architecture, WebView2 detection, installed-version state, and the
baseline/install/restart/upgrade/uninstall sequence. It never marks the host
qualified; a complete report only becomes ready for owner review.

Keep the report outside the downloaded bundle so the bundle remains exactly
verifiable. From PowerShell on a fresh Windows 11 x64 host or VM, first run the
offline verifier and record the clean baseline (replace the installer path
with the NSIS or MSI path in the bundle):

```powershell
py .\verify-download.py --directory .
py .\windows-clean-host.py `
  --phase baseline `
  --evidence ..\stagemesh-evidence\windows-clean-host.json `
  --bundle-directory . `
  --installer .\nsis\StageMesh_0.1.0_x64-setup.exe `
  --clean-host-attested
```

Install and launch StageMesh. Create a harmless saved template with a unique
marker name, confirm that the application reaches its main window, then record
the installed phase:

```powershell
py .\windows-clean-host.py `
  --phase installed `
  --evidence ..\stagemesh-evidence\windows-clean-host.json `
  --runtime-ready-observed `
  --persistence-marker "PKG-033-clean-host-canary"
```

Close and relaunch StageMesh, confirm that the marker is still present, and
record restart recovery:

```powershell
py .\windows-clean-host.py `
  --phase restarted `
  --evidence ..\stagemesh-evidence\windows-clean-host.json `
  --runtime-ready-observed `
  --save-restart-recovered `
  --persistence-marker "PKG-033-clean-host-canary"
```

The upgrade phase requires a genuinely different prior StageMesh version; a
same-version reinstall is rejected. After upgrading to the exact candidate,
confirm readiness and the same saved marker:

```powershell
py .\windows-clean-host.py `
  --phase upgraded `
  --evidence ..\stagemesh-evidence\windows-clean-host.json `
  --previous-version 0.0.9 `
  --upgrade-observed `
  --runtime-ready-observed `
  --save-restart-recovered `
  --persistence-marker "PKG-033-clean-host-canary"
```

Finally uninstall StageMesh, verify that it is absent from installed programs
and no StageMesh process remains, then record uninstall:

```powershell
py .\windows-clean-host.py `
  --phase uninstalled `
  --evidence ..\stagemesh-evidence\windows-clean-host.json `
  --uninstall-observed
```

If no prior StageMesh desktop version is available yet, run baseline,
installed, restarted, and uninstalled as a partial exercise. The report will
correctly keep `readyForQualificationReview` false until a real upgrade is
tested. Use a clean snapshot again for the eventual complete sequence.

## macOS

StageMesh uses WKWebView, CoreAudio, and CoreMIDI.

The macOS CI bundle contains `posix-clean-host.py`. On a fresh macOS 14+
Apple Silicon host, verify the bundle, record the baseline against the DMG,
drag `StageMesh.app` to `/Applications`, and then record the installed and
restart phases. The collector hashes the exact DMG and manifest, machine/user
identity, installed application identity, observed version, process state, and
the persistence marker without retaining its plaintext value:

```sh
python3 verify-download.py --directory .
python3 posix-clean-host.py \
  --phase baseline \
  --evidence ../stagemesh-evidence/macos-clean-host.json \
  --bundle-directory . \
  --installer ./dmg/StageMesh_0.1.0_aarch64.dmg \
  --clean-host-attested

python3 posix-clean-host.py \
  --phase installed \
  --evidence ../stagemesh-evidence/macos-clean-host.json \
  --installed-executable /Applications/StageMesh.app \
  --runtime-ready-observed \
  --persistence-marker "PKG-033-clean-host-canary"

python3 posix-clean-host.py \
  --phase restarted \
  --evidence ../stagemesh-evidence/macos-clean-host.json \
  --installed-executable /Applications/StageMesh.app \
  --runtime-ready-observed \
  --save-restart-recovered \
  --persistence-marker "PKG-033-clean-host-canary"
```

Use the same `upgraded` and `uninstalled` phase flags documented for Windows.
The upgrade must start from a genuinely different version. Remove the app
before recording uninstall. A complete report is only ready for owner review;
it does not establish Gatekeeper, signing, notarization, accessibility, or
audio/MIDI qualification.

On first use:

- grant microphone permission when capture is requested;
- connect the interface before running the device scan;
- use the vendor driver only when the interface is not class-compliant;
- approve any vendor system extension through macOS System Settings.

The FLkey Mini and Apogee BOOM paths remain subject to the native hardware
qualification evidence. Device visibility in the app is not the same as
audible loopback or recording qualification.

For BOOM conversion measurement, use a balanced 1/4-inch TRS cable from one
main output to a line input, select the line input in Apogee Control 2, disable
direct monitoring, and start at a low output level. Record the exact Control 2
routing and gain settings with the reference and captured WAV files. Apogee's
official guidance confirms that BOOM line inputs accept 1/4-inch connections:
<https://knowledge.apogeedigital.com/how-to-connect-line-inputs-to-boom>.

## Linux

The AppImage is portable but still relies on the host's webview and graphics
stack. The Debian package declares the WebKitGTK and GTK runtime dependencies.

The Linux CI bundle also contains `posix-clean-host.py`. Run it on a fresh
Ubuntu 22.04 or 24.04 x64 host for the AppImage and Debian package separately.
The Debian path reads its installed version from `dpkg`; the AppImage path
requires the installed/portable executable path and an explicit observed
version because AppImage has no package registration:

```sh
python3 verify-download.py --directory .
python3 posix-clean-host.py \
  --phase baseline \
  --evidence ../stagemesh-evidence/linux-appimage-clean-host.json \
  --bundle-directory . \
  --installer ./appimage/StageMesh_0.1.0_amd64.AppImage \
  --clean-host-attested

python3 posix-clean-host.py \
  --phase installed \
  --evidence ../stagemesh-evidence/linux-appimage-clean-host.json \
  --installed-executable "$HOME/.local/bin/StageMesh.AppImage" \
  --observed-installed-version 0.1.0 \
  --runtime-ready-observed \
  --persistence-marker "PKG-033-clean-host-canary"
```

Record restart, real-version upgrade, and uninstall exactly as with macOS,
continuing to pass the installed executable and observed version until it is
removed. For the Debian exercise, select the `.deb`; package registration is
then mandatory and fail-closed. Preserve each installer format's report
separately.

For audio and MIDI, install the host's supported stack:

```sh
sudo apt install libwebkit2gtk-4.1-0 libgtk-3-0 pipewire pipewire-audio   pipewire-alsa pipewire-jack alsa-utils
```

For USB device access, use the distribution's udev rules or the device
manufacturer's documented rules. StageMesh will not add a broad world-writable
USB rule. A device can be visible while still being unavailable to the
selected audio or MIDI backend.

## Troubleshooting sequence

1. Launch StageMesh and open Compatibility.
2. Scan hardware and record the backend/device identity shown.
3. Confirm the OS has granted the required permission.
4. Confirm the vendor driver or class-compliant path is installed.
5. Run the platform smoke test.
6. For physical qualification, run the required audible/capture loopback and
   continuity measurements separately.

Driver installation, device enumeration, and software smoke tests do not prove
audible quality, latency, SNR, THD+N, or long-run continuity.

## Clean-host acceptance matrix

Run each installer on a host that has not used the StageMesh source tree or a
previous development package:

| Priority | Host | Required evidence |
| --- | --- | --- |
| P0 | Windows 11 x64 | NSIS/MSI install, WebView2 bootstrap or existing-runtime detection, launch/readiness, save/restart recovery, upgrade and uninstall |
| P0 | macOS 14+ Apple Silicon | DMG install, Gatekeeper behavior for the unsigned test build, microphone permission, launch/readiness, save/restart recovery, real-version upgrade and uninstall; preserve `macos-clean-host.json` |
| P0 | Ubuntu 22.04/24.04 x64 | AppImage plus Debian install, WebKitGTK 4.1 dependency resolution, launch/readiness, save/restart recovery, real-version upgrade and uninstall; preserve separate JSON reports |
| P1 | A second non-developer user account on each host | Per-user data isolation, permissions, log location and uninstall state preservation |

The matrix qualifies installed software behavior only. A host passes hardware
qualification only after the named audio/MIDI device, driver, cable/routing,
reference signal, capture, continuity, and review artifacts also pass.

### Bind the complete clean-host matrix

After all five reports are complete, place them with the CI
`desktop-release-index.json` and run the reviewer shipped in any desktop
bundle. Each report must match that index's version, source commit, and exact
platform-manifest digest; every phase must have passed. Duplicate, unsupported,
incomplete, or cross-candidate reports fail closed.

```sh
python3 review-clean-host.py \
  --index desktop-release-index.json \
  --evidence windows-nsis-clean-host.json \
  --evidence windows-msi-clean-host.json \
  --evidence macos-clean-host.json \
  --evidence linux-deb-clean-host.json \
  --evidence linux-appimage-clean-host.json \
  --output desktop-clean-host-review.json
```

A complete review document sets `readyForOwnerReview` to true while keeping
`ownerReviewComplete`, `cleanHostInstallQualified`, accessibility, and physical
hardware qualification false. A partial set is still summarized with the exact
missing installer tracks, so evidence can be collected incrementally without
overstating completion.
