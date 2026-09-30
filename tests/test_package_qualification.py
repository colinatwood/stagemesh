import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux packaging reference qualification")
class PackageQualificationTests(unittest.TestCase):
    def test_isolated_rootfs_qualification_preserves_then_purges_state(self):
        for tool in ("systemd-sysusers", "systemd-tmpfiles", "systemd-analyze"):
            if shutil.which(tool) is None:
                self.skipTest(f"missing {tool}")
        if os.environ.get("STAGEMESH_PACKAGE_QUALIFY_SUDO") != "1":
            self.skipTest("isolated rootfs ownership test requires sudo")
        with tempfile.TemporaryDirectory() as raw:
            build = Path(raw) / "build"
            (build / "native").mkdir(parents=True)
            engine = build / "native/stagemesh_engine"
            engine.write_text("#!/bin/sh\nexit 0\n")
            engine.chmod(0o755)
            command = [sys.executable, str(ROOT / "scripts/stagemesh-package-qualify.py"), "--build-dir", str(build)]
            # Only the isolated rootfs ownership exercise needs root. The full
            # suite and engine stay under the normal runner identity.
            if os.environ.get("STAGEMESH_PACKAGE_QUALIFY_SUDO") == "1":
                command = ["sudo", "-n", "--", *command]
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertTrue(report["passed"])
            self.assertEqual(report["qualification"], "isolated-rootfs-reference")
            self.assertFalse(report["cleanHostQualified"])
            self.assertFalse(report["hardwarePermissionsQualified"])
            self.assertTrue(report["reinstallPreservedState"])
            self.assertTrue(report["uninstallPreservedState"])
            self.assertTrue(report["purgeRemovedState"])
            self.assertEqual(report["stateDirectory"]["mode"], "0750")
            self.assertEqual(report["systemdUnitsVerified"], 2)
            self.assertFalse(report["serviceAutoEnabled"])
            self.assertTrue(report["licenseNoticesInstalled"])

    def test_qualification_fails_without_built_engine(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/stagemesh-package-qualify.py"), "--build-dir", "/definitely/missing"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertFalse(report["passed"])
        self.assertIn("built native", report["error"])


if __name__ == "__main__":
    unittest.main()
