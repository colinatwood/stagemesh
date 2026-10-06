# SDK and cross-build entry point

`scripts/build-native.sh` is the single configure/build entry point for native
and target-SDK builds. CMake generator, toolchain, and feature switches are
passed after the script name; `STAGEMESH_BUILD_DIR` selects the output tree.
`STAGEMESH_BUILD_CONFIG` selects a multi-configuration build and
`STAGEMESH_SKIP_TESTS=1` explicitly skips host execution for cross-builds.

Native builds run CTest by default:

```sh
STAGEMESH_BUILD_DIR=build ./scripts/build-native.sh \
  -G Ninja -DSTAGEMESH_BUILD_TESTS=ON
```

Cross-compiled binaries are linked but cannot run on the host. Skip CTest only
for that case, explicitly:

```sh
STAGEMESH_BUILD_DIR=build-mingw STAGEMESH_SKIP_TESTS=1 \
  ./scripts/build-native.sh -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=/path/to/mingw-toolchain.cmake \
  -DSTAGEMESH_BUILD_TESTS=ON
```

`STAGEMESH_BUILD_CONFIG` is available for multi-configuration generators such
as Visual Studio (`Release`, for example). Native runtime tests remain required
on a matching Windows or macOS runner; a successful cross-build is compile and
link evidence only.

## Packaging

The root build installs `stagemesh_engine`, the core/device libraries, and both
public include trees. CPack produces a deterministic package name containing the
StageMesh version, target OS, and architecture:

```sh
cmake --build build --target package
```

Packaging proves artifact assembly only. It does not claim native device access,
callback delivery, or physical qualification on the packaging host.
