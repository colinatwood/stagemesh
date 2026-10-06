# Astra checkpoint 52 validation — reviewed Focusrite Scarlett 4th Gen Windows package metadata

Checkpoint 52 expands the deliberately small v2 driver catalog with three reviewed Windows x64 package-metadata records. This remains compatibility assistance only: a catalog match does not install a driver, qualify an interface or change StageMesh hardware-support claims.

## Added reviewed records

The catalog now contains Windows 10/11 AMD64 records for:

- Focusrite Scarlett Solo 4th Gen — `USB:1235:8218`;
- Focusrite Scarlett 2i2 4th Gen — `USB:1235:8219`;
- Focusrite Scarlett 4i4 4th Gen — `USB:1235:821A`.

Each record points to the product-specific Focusrite downloads page and identifies **Focusrite Control 2 1.1108.0**, whose 2026-08-13 release notes list the entire Scarlett 4th Gen range and include Windows driver **4.150.0.432**. Hardware IDs are backed by independent Linux device/driver evidence rather than inferred from product names.

Evidence URLs stored in the catalog include:

- `https://support.focusrite.com/hc/en-gb/articles/13289679039378-Focusrite-Control-2-Release-Notes`
- `https://downloads.focusrite.com/focusrite/scarlett-4th-gen/scarlett-solo-4th-gen`
- `https://downloads.focusrite.com/focusrite/scarlett-4th-gen/scarlett-2i2-4th-gen`
- `https://downloads.focusrite.com/focusrite/scarlett-4th-gen/scarlett-4i4-4th-gen`
- independent hardware-ID evidence under the Geoffrey Bennett Scarlett Linux projects/discussions.

The entries were reviewed on 2026-09-14, expire on 2027-03-14 and carry `moderate` confidence. No ARM64 record is added because the reviewed Focusrite evidence used here does not establish an ARM64 Windows package contract for these entries.

## Validation

Validated on 2026-09-14 using the checkpoint-51 RT-qualified native engine:

- native CTest remains **2/2 passed**; no native source changed in this checkpoint;
- full Python suite: **569 tests passed**;
- focused driver-catalog suite: **7/7 passed**;
- exact Windows 11 AMD64 matching succeeds for all three new hardware IDs;
- Windows ARM64 matching remains `no-verified-match` for all three records;
- every bundled record still reports `automaticInstallAllowed: false` and `qualification: hardware-tests-required`;
- automation-performance gate passed: **4096 points / 8192 reads / 8192 frames in 6.763 ms**;
- **125 JSON schemas plus OpenAPI and the driver catalog parsed**;
- **7/7 frontend JavaScript files** passed `node --check`.

## Remaining boundary

The bundled catalog is still intentionally small. It does not replace Windows/macOS endpoint evidence adapters, installed-driver inspection, real driver installation, device testing or periodic vendor re-review. Package metadata can help an operator find the right software; it cannot prove audio timing, hotplug, StageMesh compatibility or stage qualification.
