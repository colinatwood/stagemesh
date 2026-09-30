# StageMesh

StageMesh consolidates the recovered Checkpoint 69 engine, backend,
frontend, schemas, packaging and tests with the Checkpoint 70–83 platform work.
GitHub is the canonical source. Recovery provenance and integration limits are
recorded in `docs/consolidation-checkpoint-84.md`.

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

GitHub Actions also provides a manually runnable Linux release-artifact
workflow. It builds a Release engine, runs native tests, stages the Linux
installation tree, and publishes an archive with SHA-256 checksums. The
Windows/macOS platform evidence workflows run on pull requests, `main` pushes,
and manual dispatches.

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
