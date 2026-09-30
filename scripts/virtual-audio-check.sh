#!/usr/bin/env sh
set -eu

# Prepare a Linux host for software-only ALSA loopback testing. This never
# activates StageMesh hardware output; it only loads snd-aloop when available.
if ! command -v modprobe >/dev/null 2>&1; then
    echo "modprobe is unavailable; use a Linux VM with module support." >&2
    exit 2
fi

if ! grep -q '^snd_aloop ' /proc/modules 2>/dev/null; then
    if ! modprobe snd-aloop index=7 id=StageMeshLoopback pcm_substreams=2; then
        echo "Unable to load snd-aloop; run with sudo on a Linux host or VM." >&2
        exit 2
    fi
fi

echo "Virtual ALSA loopback is available. Devices:"
if command -v aplay >/dev/null 2>&1; then aplay -l || true; fi
if command -v arecord >/dev/null 2>&1; then arecord -l || true; fi
echo "Use this only for loopback/software qualification; physical hardware remains unqualified."
