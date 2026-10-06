# Astra checkpoint 53 validation — proactive driver-catalog review audit

Checkpoint 53 turns driver-catalog expiry from a passive match-time rule into an explicit operator/release audit. The audit is deterministic and offline: it does not fetch vendor sites or mutate the catalog, and therefore cannot silently convert an internet lookup into reviewed evidence.

## Audit contract

`stagemesh-driver-catalog-audit.py` reads a catalog and emits `org.upp.driver-catalog-audit-report` version 1.

The report includes:

- deterministic `asOf` date and configurable review-warning horizon;
- total/current/review-due/stale/unreviewed/invalid counts;
- per-record review state and days until expiry;
- `catalogUsable`, which fails closed for invalid, stale or unreviewed records;
- `reviewAttentionRequired`, which becomes true for stale/unreviewed/invalid entries and for otherwise-current entries inside the warning horizon.

The command exits non-zero when the catalog is unusable. A current but soon-to-expire catalog remains usable while still raising review attention, allowing operators to re-review before exact matches disappear on the expiry date.

The Linux installer now ships the audit helper beside the other StageMesh qualification utilities.

## Validation

Validated on 2026-09-14:

- bundled catalog audit at a 30-day warning horizon: **5 total / 5 current / 0 due / 0 stale / 0 unreviewed / 0 invalid**;
- focused driver catalog + audit suite: **10/10 passed**;
- full Python suite: **572 tests passed** on the rerun;
- an initial full run had one unrelated community magic-link API test return 403 once; the test passed immediately in isolation and the unchanged full suite then passed 572/572. No production behavior or timeout was changed to obtain the pass;
- native RT CTest remains **2/2 passed**; no native source changed in checkpoints 52–53;
- automation-performance gate passed: **4096 points / 8192 reads / 8192 frames in 5.846 ms**;
- **126 JSON schemas plus OpenAPI and the driver catalog parsed**;
- **7/7 frontend JavaScript files** passed `node --check`.

## Remaining boundary

The audit can reveal review debt but cannot perform a vendor review. Humans still need to verify vendor package/version/platform information and independent device identity evidence, then intentionally update `reviewedAt`, `reviewExpiresAt`, confidence and sources. Windows/macOS endpoint evidence adapters, installed-driver inspection, broader vendor/model coverage and physical qualification remain open.
