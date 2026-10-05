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

## Signing input preflight

`desktop-signing-readiness.py` records whether the expected credential names
are populated for Windows or macOS without writing or printing credential
values. The report is included in each desktop artifact and checksummed by the
artifact manifest. It is informational for unsigned test builds; supplying
credentials does not itself prove that signing or notarization succeeded.

Windows supports two declared modes: `pfx`, using an imported Authenticode
certificate, thumbprint and timestamp URL; or `azure-artifact-signing`, using
Azure identity plus the account endpoint/profile configuration. macOS requires
the exported Developer ID certificate and temporary keychain password, plus a
complete Apple ID or App Store Connect API notarization credential set.

Never commit these credentials. Configure them as protected repository or
environment secrets only after the owner selects the signing providers.

The workflow expects certificate material, passwords and cloud identities in
GitHub Actions **secrets**. It expects non-secret mode, thumbprint, timestamp,
Azure account/profile, and API-key path configuration in Actions **variables**.
The preflight sees only the mapped environment for its runner and writes only
the names of present or missing inputs.

## Exact-artifact signing verification

`desktop-signing-verification.py` is the second, independent signing boundary.
It reads the generated `desktop-artifacts.json`, discovers the platform package
files or bundles, re-hashes every manifest entry represented by each selected
artifact, records the SHA-256 of that exact manifest in the report, and then
invokes the native verifier for the configured platform:

- Windows: Authenticode `signtool verify /pa /all`.
- macOS: `codesign`, `spctl`, or `pkgutil` according to the exact bundle type.
- Linux: remains blocked until the owner selects a package/repository signing
  policy and its verification adapter.

The workflow runs this report in advisory mode while
`STAGEMESH_SIGNING_VERIFICATION_MODE` is unset. Set that Actions variable to
`required` only after the provider, signing step, and verifier tool are all
configured; a missing verifier, manifest mismatch, or rejected signature then
fails the desktop job. The report never changes `desktop-artifacts.json`'s
`signed` or qualification fields, and a verified signature still does not
establish legal approval, clean-host installation, or physical audio/MIDI
qualification.

`signing-verification.json` is an evidence sidecar rather than a packaged-file
entry. It is deliberately excluded from `desktop-artifacts.json` and
`SHA256SUMS` to avoid a self-referential checksum cycle. CI must not regenerate
the artifact manifest after verification; the report's `artifactManifest`
SHA-256 binds it to the immutable manifest it actually checked.
