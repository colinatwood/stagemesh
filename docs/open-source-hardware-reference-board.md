# Open-source hardware reference board

These projects are reference material for StageMesh hardware configuration,
audio/video transport, lighting control, mapping, robotics, and safety
research. They are not StageMesh dependencies and do not by themselves
qualify StageMesh hardware support.

## Audio, realtime, and media

- [Linux ALSA driver configuration](https://www.kernel.org/doc/html/v6.5/sound/alsa-configuration.html)
- [LinuxAudio system configuration](https://wiki.linuxaudio.org/wiki/system_configuration)
- [Ardour](https://github.com/ardour) — digital audio workstation and audio-hosting reference
- [Audacity](https://github.com/audacity/audacity) — cross-platform recording and editing reference
- [JACK Audio Connection Kit](https://github.com/jackaudio) — low-latency graph and session reference
- [PipeWire](https://github.com/PipeWire) — modern Linux media graph and device-session reference
- [FFmpeg](https://github.com/ffmpeg/ffmpeg) — media format, codec, and transport reference

StageMesh guidance: [FFmpeg interoperability](ffmpeg-interoperability.md).

## Lighting, DMX, and visual control

- [hobbyquaker/artnet](https://github.com/hobbyquaker/artnet) — ArtDMX sender behavior
- [QLC+](https://github.com/mcallegari/qlcplus) — lighting console and fixture-control reference
- [Open Lighting Architecture](https://github.com/OpenLightingProject/ola) — DMX/Art-Net/sACN gateway reference
- [WLED](https://github.com/wled/WLED) — network-controlled LED and embedded lighting reference
- [ChamSys](https://github.com/ChamSys) — lighting-control ecosystem reference
- [OBS Studio](https://github.com/obsproject/obs-studio) — live audiovisual routing and capture reference
- [CasparCG](https://github.com/casparcg) — broadcast graphics and playout reference

StageMesh guidance: [broadcast playout interoperability](broadcast-playout-interoperability.md).

## Mapping, robotics, and control

- [USGS MapIO](https://github.com/usgs/MapIO) — mapping/geospatial reference
- [ROS 2](https://github.com/ros2) — robotics middleware and distributed control reference
- [Espressif Arduino-ESP32](https://github.com/espressif/arduino-esp32) — embedded Wi-Fi/Bluetooth control reference
- [LinuxCNC](https://github.com/linuxcnc/linuxcnc) — deterministic machine-control reference
- [paperManu/splash](https://github.com/paperManu/splash) — visual/control reference for further review

StageMesh guidance: [projection mapping interoperability](projection-mapping-interoperability.md).

## Pyro and safety research

- [giuseppe-coco/FireShow](https://github.com/giuseppe-coco/FireShow) — pyro/show-control reference for safety and authorization review

StageMesh guidance: [pyrotechnic visualization and show safety](pyrotechnic-visualization-interoperability.md).

Pyrotechnic or physical-actuation behavior must remain fail-closed, explicitly
armed, independently authorized, and subject to applicable law and venue
procedures. Borrowing a protocol or UI pattern from a reference project does
not establish safe operation.

## Use rules

1. Inspect each project’s current license before copying code or assets.
2. Prefer protocol and architecture references over source-code copying.
3. Keep StageMesh’s explicit arming, identity, authorization, and audit
   boundaries intact.
4. Record named hardware, OS, kernel, firmware, topology, and measurements
   before making a support claim.
5. Keep simulated, loopback, hosted-CI, and reference-project evidence separate
   from physical qualification.
