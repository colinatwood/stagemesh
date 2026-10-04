# StageMesh Desktop

StageMesh now has a cross-platform desktop application target backed by Tauri 2.
The desktop executable uses the operating system webview:

- Windows: WebView2
- macOS: WKWebView
- Linux: WebKitGTK

The existing `frontend/` is reused as the desktop UI, so the web design and
desktop design do not drift. The existing C++ native engine remains the
authority for audio, MIDI, device identity, lifecycle, and qualification
boundaries.

## Local development

Install Rust, Node.js, and the platform webview prerequisites, then run:

```sh
cd desktop
npm install
npm run tauri dev
```

Build the executable:

```sh
cd desktop
npm run tauri build
```

The first milestone intentionally keeps the bundle step disabled while the
native engine bridge is integrated. The next desktop milestones are:

1. start the local backend/runtime from the executable;
2. expose native audio and MIDI operations through a typed bridge;
3. enable signed installers for Windows, macOS, and Linux;
4. run platform smoke tests against the executable.

Hosted browser checks and physical hardware qualification remain separate
evidence. A desktop build must not claim physical qualification merely because
the application launches.
