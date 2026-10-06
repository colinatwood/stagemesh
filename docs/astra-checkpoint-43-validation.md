# Astra backlog checkpoint 43 validation

Checkpoint 43 replaces the intentionally empty bundled driver catalog with a narrowly reviewed, provenance-bearing package-metadata set and makes review freshness part of the matching contract. Catalog evidence remains assistance only: it never authorizes installation and never establishes hardware qualification.

## Reviewed bundled entries

The bundled v2 catalog currently contains two architecture-specific records for **RME Babyface Pro FS in proprietary USB mode** on Windows:

- USB identity: `USB:2A39:3FC0`.
- Package: `driver_usb_win_1276.zip`, version `1.276`.
- AMD64: Windows 10 and Windows 11.
- ARM64: Windows 11.
- Package/vendor evidence: RME's official downloads listing, reviewed 2026-09-13.
- Device-ID evidence: Linux kernel driver discussion identifying VID `0x2a39`, PID `0x3fc0` for Babyface Pro FS proprietary mode.
- Review confidence: `moderate`, because the package support statement is vendor-authored while the exact USB-ID evidence is independently sourced rather than published in the vendor download record.
- Review expiry: 2027-03-13. Expiry does not delete the record; it changes the match to `curated-match-review-stale` until re-reviewed.

## Contract changes

- Driver-catalog schema advances to v2 with explicit product identity, package/release version, review/expiry dates, confidence, `package-metadata-only` claim scope and at least two HTTPS evidence sources.
- The loader remains able to read v1 locally curated catalogs for compatibility, but entries without v2 review evidence can only produce `curated-match-unreviewed`.
- Expired reviewed evidence produces `curated-match-review-stale` and `catalogReviewRequired=true`.
- Only a current exact hardware/OS/release/architecture record can produce `curated-exact-match`.
- `automaticInstallAllowed` remains false and `qualification` remains `hardware-tests-required` for every result.
- Search links remain explicitly unverified and are never promoted by the catalog matcher.

## Validation

- Focused driver-catalog suite: 6 tests passed.
- Driver + hardware diagnostics + installer integration group: 17 tests passed.
- Fresh release native build with `STAGEMESH_RT_QUALIFICATION=ON`: 2/2 CTest targets passed.
- Release Python suite against that exact engine: 531 tests passed.
- Automation performance: passed with 4096 points / 8192 frames and binary block-entry search.
- Public JSON schemas: 117 parsed successfully.
- `frontend/openapi.json`: parsed successfully as OpenAPI 3.1.0.
- Frontend JavaScript: 7/7 files passed `node --check`.

## Remaining boundary

The bundled set is intentionally tiny and is not a general device-compatibility database. Windows/macOS endpoint evidence adapters, additional reviewed vendor records, periodic re-review, real driver installation and physical device qualification remain separate work. A catalog match is package metadata evidence, not proof that StageMesh or a particular device works correctly.
