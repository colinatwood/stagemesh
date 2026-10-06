# Linux developer-alpha installation

Build and run the clean software gate before installation. Stage into a temporary
root first:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DSTAGEMESH_BUILD_TESTS=ON
cmake --build build
DESTDIR=/tmp/stagemesh-stage STAGEMESH_BUILD_DIR="$PWD/build" sh scripts/install-linux.sh
```

Run the repeatable isolated-rootfs packaging reference after building:

```sh
python3 scripts/stagemesh-package-qualify.py --build-dir "$PWD/build"
```

The helper runs the real installer twice, provisions the staged service account/state
directory with `systemd-sysusers`/`systemd-tmpfiles`, verifies both systemd units,
checks state preservation on reinstall/uninstall and checks explicit purge. Its report
intentionally keeps `cleanHostQualified` and `hardwarePermissionsQualified` false.

Inspect the staged service and files. On a real host, run the installer as root,
then provision the service identity and state directory using the host's supported
systemd packaging hooks (`systemd-sysusers` and `systemd-tmpfiles`). Review audio, MIDI, Bluetooth and UWB device permissions for that account. The installer does
not enable or start the service. Run the installed permission verifier **as the service identity** against the exact device nodes intended for the deployment, for example:

```sh
runuser -u stagemesh -- /usr/libexec/stagemesh/stagemesh-device-permissions.py \
  --service-user stagemesh \
  --device /dev/snd/pcmC0D0p:rw \
  --device /dev/snd/midiC0D0:rw
```

The helper does not change groups, ACLs or udev rules. A failure means the host permission policy must be corrected and reviewed; do not make the installer broaden access automatically.

The StageMesh service listens on `127.0.0.1:8765`, uses the existing
`/var/lib/stagemesh` state path for upgrade compatibility, and starts with
systemd sandboxing, and receives no automatic hardware qualification. Do not expose
the developer bridge to a LAN until the pending authentication/origin review is
complete. Copy `examples/demo-session.json` through the documented session API or
UI only after reviewing the developer-alpha limitations.

Remove program files while preserving state:

```sh
sh scripts/uninstall-linux.sh
```

`--purge-data` irreversibly removes `/var/lib/stagemesh` when executed on the real
root. Back up data first. Neither path removes the service account. Stop/disable the
service through normal host administration before uninstalling; scripts do not
change service enablement. The canonical installed program roots are
`/usr/libexec/stagemesh` and `/usr/share/stagemesh`; program files are replaced
on install and removed on uninstall while the established account,
environment-file paths, and state are retained. Upgrade is reinstall-in-place and preserves state, but
real host upgrade/rollback compatibility remains unqualified.
