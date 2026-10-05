#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DESTDIR=${DESTDIR:-}
PREFIX=${PREFIX:-/usr}
# STAGEMESH_BUILD_DIR is canonical; retain the legacy variable for existing
# build/deployment scripts while the installed program paths migrate.
BUILD_DIR=${STAGEMESH_BUILD_DIR:-${STAGEFORGE_BUILD_DIR:-"$ROOT/build"}}
if [ "$PREFIX" != /usr ]; then
    printf '%s\n' 'Only PREFIX=/usr is supported by the bundled service unit.' >&2
    exit 1
fi
case "$DESTDIR" in
    ""|/*) ;;
    *) printf '%s\n' 'DESTDIR must be empty or an absolute staging path.' >&2; exit 1 ;;
esac
if [ ! -x "$BUILD_DIR/native/stagemesh_engine" ]; then
    printf '%s\n' 'Build the native engine before installation.' >&2
    exit 1
fi
# Remove only superseded program artifacts. Persistent state, service account,
# and /etc/stageforge configuration remain in place for upgrade compatibility.
rm -rf "$DESTDIR$PREFIX/libexec/stageforge" "$DESTDIR$PREFIX/share/stageforge"
rm -f "$DESTDIR$PREFIX/lib/systemd/system/stageforge.service" \
      "$DESTDIR$PREFIX/lib/systemd/system/stageforge-witness.service" \
      "$DESTDIR$PREFIX/lib/udev/rules.d/70-stageforge-uwb.rules"
install -d "$DESTDIR$PREFIX/libexec/stagemesh" "$DESTDIR$PREFIX/share/stagemesh" "$DESTDIR$PREFIX/share/stagemesh/packaging" "$DESTDIR$PREFIX/lib/systemd/system" "$DESTDIR$PREFIX/lib/udev/rules.d" "$DESTDIR$PREFIX/lib/sysusers.d" "$DESTDIR$PREFIX/lib/tmpfiles.d"
install -m 0755 "$BUILD_DIR/native/stagemesh_engine" "$DESTDIR$PREFIX/libexec/stagemesh/stagemesh_engine"
install -m 0755 "$ROOT/scripts/stageforge-plugin-host.py" "$ROOT/scripts/stageforge-qualify.py" "$ROOT/scripts/stageforge-hardware-doctor.py" "$ROOT/scripts/stageforge-http-qualify.py" "$ROOT/scripts/stageforge-witness-qualify.py" "$ROOT/scripts/stageforge-driver-catalog-audit.py" "$ROOT/scripts/stageforge-package-qualify.py" "$ROOT/scripts/stageforge-qualification-plan.py" "$ROOT/scripts/stageforge-qualification-review.py" "$ROOT/scripts/stageforge-qualification-status.py" "$ROOT/scripts/stageforge-device-permissions.py" "$DESTDIR$PREFIX/libexec/stagemesh/"
cp -R "$ROOT/backend" "$ROOT/frontend" "$ROOT/schemas" "$DESTDIR$PREFIX/share/stagemesh/"
install -m 0644 "$ROOT/LICENSE" "$ROOT/THIRD_PARTY_NOTICES.md" "$DESTDIR$PREFIX/share/stagemesh/"
install -m 0644 "$ROOT/packaging/driver-catalog.json" "$DESTDIR$PREFIX/share/stagemesh/packaging/driver-catalog.json"
install -m 0644 "$ROOT/packaging/stagemesh-proxy.env.example" "$DESTDIR$PREFIX/share/stagemesh/packaging/stagemesh-proxy.env.example"
install -m 0644 "$ROOT/packaging/stagemesh-witness.env.example" "$DESTDIR$PREFIX/share/stagemesh/packaging/stagemesh-witness.env.example"
install -d "$DESTDIR$PREFIX/share/stagemesh/packaging/reverse-proxy"
install -m 0644 "$ROOT/packaging/reverse-proxy/README.md" "$DESTDIR$PREFIX/share/stagemesh/packaging/reverse-proxy/README.md"
install -m 0644 "$ROOT/packaging/systemd/stagemesh.service" "$DESTDIR$PREFIX/lib/systemd/system/stagemesh.service"
install -m 0644 "$ROOT/packaging/systemd/stagemesh-witness.service" "$DESTDIR$PREFIX/lib/systemd/system/stagemesh-witness.service"
install -m 0644 "$ROOT/packaging/udev/70-stagemesh-uwb.rules" "$DESTDIR$PREFIX/lib/udev/rules.d/70-stagemesh-uwb.rules"
install -m 0644 "$ROOT/packaging/sysusers/stagemesh.conf" "$DESTDIR$PREFIX/lib/sysusers.d/stagemesh.conf"
install -m 0644 "$ROOT/packaging/tmpfiles/stagemesh.conf" "$DESTDIR$PREFIX/lib/tmpfiles.d/stagemesh.conf"
printf 'Installed under %s%s; provision sysusers/tmpfiles, review device permissions, then explicitly enable the service.\n' "$DESTDIR" "$PREFIX"
