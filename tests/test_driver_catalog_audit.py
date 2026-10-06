import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from driver_compatibility import audit_catalog

class DriverCatalogAuditTests(unittest.TestCase):
    def test_bundled_catalog_is_usable_and_not_due_at_checkpoint_date(self):
        report=audit_catalog(ROOT/"packaging/driver-catalog.json",as_of=date(2026,9,14),warn_days=30)
        self.assertTrue(report["catalogUsable"]);self.assertFalse(report["reviewAttentionRequired"])
        self.assertEqual(report["counts"]["total"],5);self.assertEqual(report["counts"]["current"],5);self.assertEqual(report["counts"]["reviewDue"],0)

    def test_due_and_stale_records_are_reported_without_hiding_current_entries(self):
        base={"hardwareId":"USB:1234:ABCD","product":"X","os":"Windows","osReleases":["11"],"architecture":"AMD64","publisher":"V","package":"P","version":"1","url":"https://vendor.example/x","releaseDate":"2026-01-01","reviewedAt":"2026-01-02","reviewExpiresAt":"2026-10-01","reviewConfidence":"moderate","catalogClaim":"package-metadata-only","evidence":[{"kind":"vendor-download","url":"https://vendor.example/x"},{"kind":"hardware-id-source","url":"https://ids.example/x"}]}
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/"catalog.json";path.write_text(json.dumps({"schemaVersion":2,"packages":[base,{**base,"hardwareId":"USB:1234:ABCE","reviewExpiresAt":"2026-09-13"}]}))
            report=audit_catalog(path,as_of=date(2026,9,14),warn_days=30)
            self.assertFalse(report["catalogUsable"]);self.assertTrue(report["reviewAttentionRequired"]);self.assertEqual(report["counts"]["reviewDue"],2);self.assertEqual(report["counts"]["stale"],1)

    def test_invalid_catalog_is_unusable_and_cli_returns_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/"catalog.json";path.write_text('{"schemaVersion":2,"packages":[{"hardwareId":"bad"}]}')
            report=audit_catalog(path,as_of=date(2026,9,14));self.assertFalse(report["catalogUsable"]);self.assertEqual(report["counts"]["invalid"],1)
            proc=subprocess.run([sys.executable,str(ROOT/"scripts/stagemesh-driver-catalog-audit.py"),"--catalog",str(path),"--as-of","2026-09-14","--json"],capture_output=True,text=True)
            self.assertEqual(proc.returncode,1);self.assertFalse(json.loads(proc.stdout)["catalogUsable"])

if __name__=="__main__":unittest.main()
