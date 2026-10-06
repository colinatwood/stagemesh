#!/usr/bin/env sh
set -eu
DESTDIR=${DESTDIR:-}
PREFIX=${PREFIX:-/usr}
PURGE=${1:-}
if [ "$PREFIX" != /usr ]; then printf '%s\n' 'Only PREFIX=/usr is supported.' >&2; exit 1; fi
case "$DESTDIR" in ""|/*) ;; *) printf '%s\n' 'DESTDIR must be empty or absolute.' >&2; exit 1;; esac
if [ "$PURGE" != "" ] && [ "$PURGE" != "--purge-data" ]; then
  printf '%s\n' 'Usage: uninstall-linux.sh [--purge-data]' >&2; exit 1
fi
rm -f "$DESTDIR$PREFIX/lib/systemd/system/stagemesh.service" \
      "$DESTDIR$PREFIX/lib/systemd/system/stagemesh-witness.service" \
      "$DESTDIR$PREFIX/lib/udev/rules.d/70-stagemesh-uwb.rules" \
      "$DESTDIR$PREFIX/lib/sysusers.d/stagemesh.conf" \
      "$DESTDIR$PREFIX/lib/tmpfiles.d/stagemesh.conf"
rm -rf "$DESTDIR$PREFIX/libexec/stagemesh" "$DESTDIR$PREFIX/share/stagemesh"
if [ "$PURGE" = "--purge-data" ]; then
  rm -rf "$DESTDIR/var/lib/stagemesh"
  printf '%s\n' 'Removed StageMesh program files and StageMesh state data. The service account was not deleted.'
else
  printf '%s\n' "Removed StageMesh program files; preserved $DESTDIR/var/lib/stagemesh. The service account was not deleted."
fi
