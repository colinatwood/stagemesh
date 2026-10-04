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

The desktop shell now prepares a portable per-user data directory and
supervises an optional `stagemesh-runtime` sidecar. See
`docs/desktop-runtime.md` for the runtime contract. The current packages still
need the sidecar binary bundled before they can be called a complete local
application.

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
repository secrets.

## Driver and hardware boundary

Read docs/desktop-installation.md for WebView, audio, MIDI, permissions,
and driver prerequisites. Installing a driver or seeing a device in a scan is
not physical qualification; audible loopback, capture, latency, and continuity
evidence remain separate.
