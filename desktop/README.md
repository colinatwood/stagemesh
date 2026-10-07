# StageMesh Desktop

StageMesh is a cross-platform desktop application backed by Tauri 2.
The executable uses the operating system webview:

- Windows: WebView2
- macOS: WKWebView
- Linux: WebKitGTK

The existing frontend/app.html is reused as the local console UI. The public
website root is a download and product overview page. The existing C++ native
engine remains the authority for audio, MIDI, device identity, lifecycle, and
qualification boundaries.

The desktop shell prepares a portable per-user data directory and supervises
the bundled `stagemesh-runtime` sidecar and `stagemesh_engine` native engine.
It waits for an
authenticated loopback readiness check before opening the console and shuts the
runtime down with the desktop window. See `docs/desktop-runtime.md` for the
runtime contract and its qualification boundaries.

## Local development

Install Rust, Node.js, and the platform webview prerequisites, then run:

    cd desktop
    npm install
    npm run tauri dev

Rust dependencies are pinned by `src-tauri/Cargo.lock`. Keep the lockfile in
source control and use Cargo's `--locked` verification after changing
`Cargo.toml`; CI rejects a manifest that no longer matches the committed lock.

Build a platform package:

    cd desktop
    npm run tauri build

Before creating a release tag, keep the version synchronized across the npm,
Tauri, Cargo, and lock manifests and verify it with:

    python scripts/verify-desktop-version.py --tag v0.1.0

Tags matching `v*` run the same Windows, macOS, and Linux package workflow as
pull requests and `main`. The version gate rejects a tag that does not exactly
match all six manifest/lockfile version records.

The build automatically generates the platform icon set from
src-tauri/icons/stagemesh.svg. Outputs are written beneath
desktop/src-tauri/target/release/bundle/.

## Platform outputs

- Windows: NSIS setup executable and MSI
- macOS: application bundle and DMG
- Linux: AppImage and Debian package

The current CI artifacts are unsigned development packages. Code signing,
notarization, and release publication require platform certificates and
repository secrets. Every CI artifact includes `SHA256SUMS` and
`desktop-artifacts.json`; the latter binds the files to the synchronized product
version and source commit and
records that signing, clean-host installation, and physical hardware remain
unqualified.

Windows NSIS and MSI packages bundle the WebView2 Evergreen offline
installer. Tauri documents an increase of approximately 127 MB per installer.
The PR #103 combined Windows CI archive measured 451,685,898 bytes, versus
24,019,887 bytes for the preceding main archive, because the workflow emits
both NSIS and MSI installers. Check each candidate's artifact metadata for the
actual distribution size. Existing WebView2 installations remain managed by
Windows; this package does not pin a fixed WebView2 version.

## Driver and hardware boundary

Read docs/desktop-installation.md for WebView, audio, MIDI, permissions,
and driver prerequisites. Installing a driver or seeing a device in a scan is
not physical qualification; audible loopback, capture, latency, and continuity
evidence remain separate.
