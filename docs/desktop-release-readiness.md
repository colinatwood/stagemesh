# Desktop release readiness boundary

`desktop-release-readiness.py` is the software-only preflight for StageMesh
desktop packages. It is intentionally useful on pull requests and on unsigned
development artifacts without pretending that CI has performed a release,
legal review, or physical qualification.

Run it against the repository and the exact release tag:

```sh
python scripts/desktop-release-readiness.py --tag v0.1.0
```

After a package build, include the generated manifest:

```sh
python scripts/desktop-release-readiness.py \
  --tag v0.1.0 \
  --manifest desktop/src-tauri/target/release/bundle/desktop-artifacts.json
```

The check fails closed for mismatched desktop versions, a tag that does not
match those versions, missing `LICENSE` or `THIRD_PARTY_NOTICES.md`, malformed
artifact metadata, unsafe manifest paths, or a manifest that claims clean-host
or physical-hardware qualification. A passing result means only that the
software inputs are internally consistent and suitable for unsigned,
controlled testing. It does not make a signing, notarization, open-source,
installer, or hardware claim.

## Publication checklist

The report always keeps `readyForPublication` false. Before publishing an
installer, an owner must complete each separate gate and retain its evidence:

1. Select and confirm the project license and review the exact dependency and
   packaged-notice inventory. The repository files alone do not record that
   owner/legal decision.
2. Configure platform signing certificates and protected CI credentials, then
   run platform signing and notarization/verification on the exact artifacts.
   Credentials and certificates must never be committed or placed in this
   report.
3. Run the clean-host matrix in
   [`desktop-installation.md`](desktop-installation.md) on the supported
   Windows, macOS, and Linux versions, including a second non-developer user.
4. Keep audio/MIDI device, loopback, reference-signal, latency, continuity,
   and capture evidence separate from hosted software checks. Device
   enumeration or a successful package build is not physical qualification.
5. Re-run the version check with the exact tag. The current desktop manifests
   are `0.1.0`, so `v0.1.0` is the matching release shape; the historical
   `v0.1.0-alpha3` tag is deliberately rejected until all manifests are
   synchronized to that prerelease.

The CI desktop workflow runs this preflight after writing each unsigned
artifact manifest. Its JSON is a review aid, not a release approval.
