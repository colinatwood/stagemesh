import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stagemesh-backlog-status.py"
WORKBOOK = ROOT / "docs/backlog" / "StageMesh-Master-Backlog-Checkpoint-83.xlsx"


def load_script():
    spec = importlib.util.spec_from_file_location("stagemesh_backlog_status", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BacklogStatusTests(unittest.TestCase):
    def test_authoritative_checkpoint_is_valid_and_counted(self):
        module = load_script()
        report = module.summarize(module.load_backlog(WORKBOOK), WORKBOOK)
        self.assertEqual(report["totalItems"], 49)
        self.assertEqual(report["openItems"], 25)
        self.assertEqual(report["statusCounts"], {"Done": 24, "In Progress": 7, "Blocked": 11, "Deferred": 7})
        self.assertEqual(report["openByPriority"], {"P0": 22, "P1": 3})
        self.assertEqual(report["openByType"], {"Decision": 2, "Qualification": 19, "Software": 4})

    def test_duplicate_ids_and_unknown_statuses_fail_closed(self):
        module = load_script()
        base = {"ID": "AUD-001", "Status": "Done"}
        with self.assertRaisesRegex(module.BacklogError, "duplicate IDs"):
            module.validate([base, dict(base)])
        with self.assertRaisesRegex(module.BacklogError, "unsupported statuses"):
            module.validate([{"ID": "AUD-001", "Status": "Maybe"}])

    def test_cli_emits_machine_readable_report(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--workbook", str(WORKBOOK), "--format", "json"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["documentType"], "org.stagemesh.backlog-status")
        self.assertIn("does not qualify hardware", report["qualificationBoundary"])

    def test_invalid_xlsx_fails_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            invalid = Path(temporary) / "invalid.xlsx"
            invalid.write_bytes(b"not an xlsx")
            result = subprocess.run([sys.executable, str(SCRIPT), "--workbook", str(invalid)],
                                    cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a valid XLSX", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
