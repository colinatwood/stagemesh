# Third-party runtime and build dependencies

StageMesh source currently vendors no third-party source libraries in this archive.
The desktop build resolves the pinned Rust, npm, and Python build inputs recorded
in `desktop/src-tauri/Cargo.lock`, `desktop/package-lock.json`, and
`requirements-desktop.txt`. CI includes a generated `desktop-dependencies.json`
inventory in each desktop artifact bundle. That inventory can include build-only,
optional, and target-specific packages and is not proof of payload inclusion or
license compliance.

The native engine dynamically loads the host ALSA library (`libasound.so.2`) on
Linux. ALSA is an operating-system dependency and is distributed under its own
terms by the host distribution. Python, Node.js, Rust, the C/C++ runtime, WebView,
systemd, and operating-system interfaces are supplied by the target/build host or
resolved during the build under their respective terms.

Third-party audio plugins and user media are not bundled. A publisher must inventory
the exact distribution payload and reproduce all required copyright/license notices
before release. This file is an engineering inventory, not legal advice or a project
license grant.
