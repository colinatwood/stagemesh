# Astra checkpoint 68 validation — service-identity device-permission qualification helper

Checkpoint 68 prepares the remaining Linux packaging/device-permission gate with an installed checker that evaluates explicit device nodes under the actual service identity. It does **not** claim any real audio, MIDI, Bluetooth or UWB device has been qualified in this container.

`backend/device_permissions.py` accepts only absolute device paths and `r`, `w` or `rw` modes. It uses `lstat`, rejects symlinks and non-character devices, records major/minor/ownership/mode, and evaluates effective access. The qualification fails if the process effective UID is not the requested service account, which prevents root from accidentally proving permissions the unprivileged service does not have.

`scripts/stagemesh-device-permissions.py` emits a bounded JSON report with `hardwarePermissionsQualified`, `serviceIdentityQualified` and `physicalOutputsArmed=false`. It never mutates ACLs, groups, udev rules or device nodes. The installer packages the helper and checkpoint-61 isolated-rootfs qualification verifies it is present.

Real `PKG-034` evidence still requires a clean host/VM running the helper as `stagemesh` against the exact ALSA/MIDI/UWB nodes used by that deployment.

## Release gate

- **11 focused device-permission/installer/package tests** pass.
- The complete Python suite passes **650 tests** in deterministic discovery-equivalent chunks against the exact fresh RT-qualified engine.
- Fresh RT native CTest passes **2/2**.
- Automation-performance passes.
- All **130 JSON schemas plus OpenAPI** parse, and all **7 frontend JavaScript files** pass Node syntax checking.

`PKG-034` remains open for the real clean-host device matrix. The checkpoint removes ambiguity about how that evidence must be gathered; it does not substitute `/dev/null` for stage hardware.
