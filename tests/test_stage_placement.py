"""Run the production placement controller's user interaction transactions."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js required for placement checks")
class StagePlacementTests(unittest.TestCase):
    def test_placement_transactions(self):
        result = subprocess.run(["node", "tests/stage_placement_test.js"], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
