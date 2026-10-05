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

The first published installers will be unsigned until the project signing
secrets and certificates are configured. Unsigned packages are for development
and controlled testing only.

Each CI artifact includes `SHA256SUMS` plus `desktop-artifacts.json`. Verify the
checksum for the installer before running it. The JSON inventory records the
product version, source commit, platform, byte count, and SHA-256 digest for every packaged file;
it also preserves the explicit unsigned, clean-host, and physical-hardware
qualification boundaries.

The Node and Rust desktop dependency graphs are pinned by committed lockfiles.
CI verifies `Cargo.toml` against `Cargo.lock` with Cargo's locked mode before
building on each operating system. This improves repeatability but is not a
claim of bit-for-bit reproducible installers or a substitute for dependency
license review.

## Windows

The installer uses the WebView2 download bootstrapper. The installer needs
internet access on machines that do not already have WebView2. Windows 10
(version 1803 and later) and Windows 11 normally include WebView2.

For audio and MIDI:

- Class-compliant USB MIDI devices use Windows' built-in MIDI support.
- Install the manufacturer's current driver for non-class-compliant interfaces.
- ASIO support is an explicit adapter milestone; the desktop shell does not
  claim ASIO qualification yet.
- The installer does not silently install vendor audio drivers.

## macOS

StageMesh uses WKWebView, CoreAudio, and CoreMIDI.

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
| P0 | macOS 14+ Apple Silicon | DMG install, Gatekeeper behavior for the unsigned test build, microphone permission, launch/readiness, save/restart recovery and uninstall |
| P0 | Ubuntu 22.04/24.04 x64 | AppImage plus Debian install, WebKitGTK 4.1 dependency resolution, launch/readiness, save/restart recovery, upgrade and uninstall |
| P1 | A second non-developer user account on each host | Per-user data isolation, permissions, log location and uninstall state preservation |

The matrix qualifies installed software behavior only. A host passes hardware
qualification only after the named audio/MIDI device, driver, cable/routing,
reference signal, capture, continuity, and review artifacts also pass.
