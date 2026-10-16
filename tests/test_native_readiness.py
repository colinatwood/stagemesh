"""Exercise live readiness transitions without a native or hardware session."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js is required for frontend behavior checks")
class NativeReadinessTests(unittest.TestCase):
    def test_readiness_updates_and_status_request_failures(self):
        result = subprocess.run(["node", "tests/native_readiness_test.js"], cwd=ROOT,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
