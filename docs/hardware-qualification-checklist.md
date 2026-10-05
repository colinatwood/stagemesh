# StageMesh hardware qualification checklist

The developer-alpha software gate is automated in CI. These items remain
separate and must be marked qualified only on a real Linux host or VM with the
corresponding devices.

## Software-only preparation

1. Build Release and run `ctest --test-dir build --output-on-failure`.
2. Run `scripts/release-check.py`.
3. Optionally run `sudo scripts/virtual-audio-check.sh` for ALSA loopback.

Before a host exercise, record the kernel and ALSA state without changing it:

```bash
uname -a
cat /proc/asound/cards
aplay -l
arecord -l
cat /proc/interrupts | grep -E 'snd|audio|xhci|usb' || true
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null || true
```

ALSA card ordering and module parameters are host-specific. If stable card
selection is required, configure the driver’s documented `index`/`id` options
for that machine and record the resulting `/proc/asound` state; do not assume
numeric card indices are portable. Use the kernel ALSA driver configuration
guide as the reference for module parameters.

For low-latency investigation, first record the current scheduler, governor,
IRQ, and memory-lock limits. Only then test a controlled change such as
threaded IRQs or an audio-group `rtprio`/`memlock` policy, with rollback and
xrun measurements. Do not apply generic tuning scripts or unbind devices as a
release prerequisite.

Loopback is evidence for software routing only; it does not qualify physical
audio, clock, latency, or device permissions.

## Clean-host package and service

- Install with `scripts/install-linux.sh` on a clean Ubuntu host or VM.
- Confirm sysusers/tmpfiles provision the service user and state directory.
- Run `systemctl daemon-reload`, then explicitly enable and start the service.
- Record `systemctl status stagemesh` and `journalctl -u stagemesh`.
- Verify reinstall preserves state and uninstall preserves documented state.

## Device access

- ALSA playback/capture, negotiated format, recovery, and sustained run.
- MIDI enumeration, input, disconnect, and reconnect.
- UWB and Bluetooth LE ISO permissions, framing, non-blocking behavior, and
  device-loss recovery.
- Art-Net and sACN output on an isolated test network.

## Evidence rules

Do not claim physical, audible, latency, clock, or hardware-permission
qualification from WSL, mocks, CI, or ALSA loopback alone. Record the host,
kernel, device identifiers, commands, logs, and pass/fail result.

References:

- [Linux kernel ALSA driver configuration guide](https://www.kernel.org/doc/html/v6.5/sound/alsa-configuration.html)
- [LinuxAudio system configuration](https://wiki.linuxaudio.org/wiki/system_configuration)
