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
the bundled `stagemesh-runtime` sidecar and native engine. It waits for an
authenticated loopback readiness check before opening the console and shuts the
runtime down with the desktop window. See `docs/desktop-runtime.md` for the
runtime contract and its qualification boundaries.

## Local development

Install Rust, Node.js, and the platform webview prerequisites, then run:

    cd desktop
    npm install
    npm run tauri dev

Build a platform package:

    cd desktop
    npm run tauri build

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
`desktop-artifacts.json`; the latter binds the files to the source commit and
records that signing, clean-host installation, and physical hardware remain
unqualified.

## Driver and hardware boundary

Read docs/desktop-installation.md for WebView, audio, MIDI, permissions,
and driver prerequisites. Installing a driver or seeing a device in a scan is
not physical qualification; audible loopback, capture, latency, and continuity
evidence remain separate.
