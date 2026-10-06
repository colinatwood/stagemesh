# StageMesh

StageMesh consolidates the recovered Checkpoint 69 engine, backend,
frontend, schemas, packaging and tests with the Checkpoint 70–83 platform work.
GitHub is the canonical source. Recovery provenance and integration limits are
recorded in `docs/consolidation-checkpoint-84.md`.

StageMesh is licensed under [Apache License 2.0](LICENSE). See
[CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes,
[SECURITY.md](SECURITY.md) for private vulnerability reporting,
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations, and
[SUPPORT.md](SUPPORT.md) for support scope.

Build the engine from the repository root with `cmake -S . -B build`, then
`cmake --build build --config Release` and
`ctest --test-dir build -C Release --output-on-failure`.
On Windows and macOS this also builds the native device lifecycle components.
Their standalone build remains available with `cmake -S native -B build`.

The Linux developer-alpha software gate is `python scripts/release-check.py`.
Install its build requirements from `requirements-release.txt` and provide Node.js.
Hosted software evidence does not qualify physical audio/MIDI hardware, licensed
plugins, deployed services, or installed packages. See
`docs/remaining-data-requirements.md` for remaining acceptance inputs.

GitHub Actions provides a manually runnable Linux release-artifact workflow
and a cross-platform desktop workflow. The desktop workflow builds native
Windows, macOS, and Linux installers, verifies each downloadable bundle, then
publishes a small SHA-256-bound release-candidate index as a CI artifact. Each
bundle includes a deterministic CycloneDX 1.7 SBOM for its locked npm, Cargo,
and Python components. These are unsigned test artifacts rather than a public
release; signing, legal review, clean-host installation, accessibility, and
physical hardware remain separate gates. Each bundle's SHA-256 subject list
and SBOM also receive a
GitHub artifact provenance attestation, and the final cross-platform candidate
index receives its own provenance attestation before upload. This is
supply-chain evidence, not platform signing, notarization, legal approval, or
hardware qualification.
Platform evidence workflows run on pull requests, `main` pushes, and manual
dispatches.

The desktop artifacts also carry fail-closed clean-host evidence collectors
for Windows, macOS, and Linux plus a cross-platform reviewer. They bind all
five installer tracks to one exact release candidate and record baseline,
install, restart, real-version upgrade, and uninstall observations without
asserting qualification. See `docs/desktop-installation.md`.

For software-only ALSA loopback preparation, run
`sudo scripts/virtual-audio-check.sh` on a Linux host or VM. Loopback verifies
routing behavior only; it does not qualify physical hardware. The complete
clean-host, service, device, and evidence procedure is in
`docs/hardware-qualification-checklist.md`.

The open-source audio, lighting, media, mapping, robotics, and safety
reference board is documented in
`docs/open-source-hardware-reference-board.md`.

The corresponding StageMesh interoperability boundaries and qualification
guides are collected in `docs/`:

- Audio and media: `daw-interoperability.md`, `media-editing-interoperability.md`,
  `jack-interoperability.md`, `pipewire-interoperability.md`,
  `ffmpeg-interoperability.md`.
- Lighting and playout: `lighting-console-interoperability.md`,
  `ola-interoperability.md`, `wled-interoperability.md`,
  `lighting-console-operator-model.md`, `av-scene-graph-interoperability.md`,
  `broadcast-playout-interoperability.md`, `artnet-interoperability.md`.
- Mapping and control: `geospatial-interoperability.md`,
  `projection-mapping-interoperability.md`,
  `ros2-robotics-interoperability.md`, `esp32-device-interoperability.md`,
  `linuxcnc-motion-interoperability.md`.
- Safety and visualization: `pyrotechnic-visualization-interoperability.md`.

These documents describe adapter boundaries and testable behavior; they do not
claim that optional host software, devices, or physical outputs have been
qualified.
