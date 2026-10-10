# Contributing to StageMesh

Thank you for helping improve StageMesh. The project welcomes focused bug fixes,
tests, documentation, portability work, and narrowly scoped features.

## Before opening an issue

- Use the bug or feature template and search existing issues first.
- Do not publish vulnerability details in an issue. Follow [SECURITY.md](SECURITY.md).
- Include the StageMesh version or commit, operating system/version, installer or
  source-build path, and the smallest reproducible example.
- Separate software observations from physical-hardware, signing, legal, or
  production-readiness claims.

## Development setup

StageMesh uses Python 3.10+, Node.js, CMake 3.20+, a C++20 compiler, and Rust for
the desktop shell. From the repository root:

```text
python -m pip install -r requirements-release.txt
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DSTAGEMESH_BUILD_TESTS=ON
cmake --build build --config Release --parallel 2
ctest --test-dir build -C Release --output-on-failure
python -m unittest discover -s tests -p "test_*.py"
```

For desktop changes, also run the relevant commands from
[desktop/README.md](desktop/README.md). The complete software release gate is:

```text
python scripts/release-check.py --check-prerequisites
python scripts/release-check.py
```

The release gate is software evidence only. Do not describe CI, virtual devices,
silent endpoints, or mocked peripherals as physical qualification.

## Pull requests

- Keep one coherent change per pull request and explain why it is needed.
- Add regression coverage for behavior changes and update user-facing docs.
- Preserve fail-closed authentication, device identity, persistence, and output
  arming behavior.
- Do not add credentials, signing material, copyrighted media, proprietary SDKs,
  or licensed plugin binaries.
- Record tests actually run and any expected skips or unavailable platforms.
- Pin third-party GitHub Actions to full commit SHAs. Dependabot proposes updates;
  keep the readable major-version comment beside each pin.
- Call out changes that need clean-host, accessibility, hardware, legal, or
  signing review instead of asserting those reviews passed.

By submitting a contribution, you agree that it is provided under the repository's
[Apache License 2.0](LICENSE) and that you have the right to submit it.

## Community

Be constructive and follow the [Code of Conduct](CODE_OF_CONDUCT.md). General
usage questions belong in the support channel described in [SUPPORT.md](SUPPORT.md).
