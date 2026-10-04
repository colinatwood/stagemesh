import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/platform-ci-smoke.py"
spec=importlib.util.spec_from_file_location("stageforge_platform_ci_smoke",SCRIPT)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PlatformCiSmokeTests(unittest.TestCase):
    def test_windows_sid_parser_accepts_whoami_csv(self):
        with mock.patch.object(module.subprocess,"check_output",return_value='"HOST\\runner","S-1-5-21-1-2-3-1001"\n'):
            self.assertEqual(module._current_windows_sid(),"S-1-5-21-1-2-3-1001")

    def test_windows_sid_parser_fails_closed(self):
        with mock.patch.object(module.subprocess,"check_output",return_value='"HOST\\runner","not-a-sid"\n'):
            with self.assertRaises(RuntimeError): module._current_windows_sid()

    def test_linux_report_is_non_physical_and_hashes_exact_engine(self):
        with tempfile.TemporaryDirectory() as td:
            engine=Path(td)/"stagemesh_engine";engine.write_bytes(b"engine")
            expected=module.hashlib.sha256(b"engine").hexdigest()
            with mock.patch.object(module,"_find_engine",return_value=engine), \
                 mock.patch.object(module.platform,"system",return_value="Linux"):
                report=module.build_report()
            self.assertEqual(report["nativeEngine"]["sha256"],expected)
            self.assertFalse(report["physicalOutputsArmed"])
            self.assertFalse(report["physicalHardwareQualified"])
            self.assertTrue(report["platformExecutionQualified"])
            self.assertIn("linuxReference",report["checks"])

    def test_workflow_has_linux_windows_and_macos_jobs(self):
        text=(ROOT/".github/workflows/ci.yml").read_text(encoding="utf-8")
        for token in ("ubuntu-latest","windows-latest","macos-14","platform-ci-smoke.py","release-check.py"):
            self.assertIn(token,text)
        self.assertIn("contents: read",text)

if __name__=="__main__": unittest.main()
