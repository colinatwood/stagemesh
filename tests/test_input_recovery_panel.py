import subprocess
import unittest
from pathlib import Path


class InputRecoveryPanelTests(unittest.TestCase):
    def test_input_recovery_workflow(self):
        subprocess.run(["node", str(Path(__file__).with_name("input_recovery_panel_test.js"))], check=True)
