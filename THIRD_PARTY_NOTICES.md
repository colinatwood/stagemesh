# Third-party runtime and build dependencies

StageMesh source currently vendors no third-party source libraries in this archive.
It dynamically loads the host ALSA library (`libasound.so.2`) on Linux. ALSA is an
operating-system dependency and is distributed under its own terms by the host
distribution. The build/test environment uses CMake 4.4.3 from
`requirements-release.txt`; CMake is a build tool and is not included in the
application payload. Python, Node.js, the C/C++ runtime, systemd and Linux kernel
interfaces are supplied by the target/build host under their respective terms.

Third-party audio plugins and user media are not bundled. A publisher must inventory
the exact distribution payload and reproduce all required copyright/license notices
before release. This file is an engineering inventory, not legal advice or a project
license grant.
