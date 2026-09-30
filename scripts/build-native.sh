#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BUILD_DIR=${STAGEMESH_BUILD_DIR:-${STAGEMESH_BUILD_DIR:-"$ROOT/build"}}
BUILD_CONFIG=${STAGEMESH_BUILD_CONFIG:-${STAGEMESH_BUILD_CONFIG:-}}

# Pass generator, toolchain and feature switches after the script name.  This
# keeps one build entry point usable for native builds and SDK/cross builds.
# Example:
#   STAGEMESH_SKIP_TESTS=1 ./scripts/build-native.sh \
#     -G Ninja -DCMAKE_TOOLCHAIN_FILE=/tmp/mingw.cmake
cmake -S "$ROOT" -B "$BUILD_DIR" "$@"
if [ -n "$BUILD_CONFIG" ]; then
    cmake --build "$BUILD_DIR" --config "$BUILD_CONFIG"
else
    cmake --build "$BUILD_DIR"
fi

# Cross-compiled binaries cannot run on the build host.  The caller must opt
# out explicitly so native builds retain the test gate by default.
if [ "${STAGEMESH_SKIP_TESTS:-${STAGEMESH_SKIP_TESTS:-0}}" != 1 ]; then
    if [ -n "$BUILD_CONFIG" ]; then
        ctest --test-dir "$BUILD_DIR" -C "$BUILD_CONFIG" --output-on-failure
    else
        ctest --test-dir "$BUILD_DIR" --output-on-failure
    fi
fi
printf '\nNative engine: %s\n' "$BUILD_DIR/native/stagemesh_engine"
