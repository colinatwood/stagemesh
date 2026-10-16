import subprocess
import unittest
from pathlib import Path


class InputRecoveryPanelTests(unittest.TestCase):
    def test_input_recovery_workflow(self):
        subprocess.run(["node", str(Path(__file__).with_name("input_recovery_panel_test.js"))], check=True)

    def test_input_recovery_observations(self):
        subprocess.run(["node", str(Path(__file__).with_name("input_recovery_observations_test.js"))], check=True,
                       cwd=Path(__file__).resolve().parents[1], timeout=10)
