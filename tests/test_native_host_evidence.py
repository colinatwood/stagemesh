import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_host_evidence", ROOT / "scripts/native-host-evidence.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class NativeHostEvidenceTests(unittest.TestCase):
    def test_hashes_files_without_executing_binary_or_inferring_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "native_capture_smoke.exe"
            binary.write_bytes(b"not an executable\x00")
            transcript = root / "capture.txt"
            transcript.write_text("native_capture FAILED 0x800700AA\n")
            with patch.object(module, "source_observation", return_value={"commit": "1" * 40, "worktreeDirty": True}), patch.object(module, "diagnose_hardware", return_value={"scanStatus": "partial-or-unavailable", "issues": ["probe failed"]}), patch.object(module.subprocess, "run") as run:
                report = module.collect(root, binary, [transcript])
            run.assert_not_called()
            self.assertEqual(report["binary"]["sha256"], hashlib.sha256(binary.read_bytes()).hexdigest())
            self.assertEqual(report["savedTranscripts"][0]["sha256"], hashlib.sha256(transcript.read_bytes()).hexdigest())
            self.assertTrue(report["source"]["worktreeDirty"])
            self.assertEqual(report["hardwareInventory"]["scanStatus"], "partial-or-unavailable")
            for field in ("binaryExecuted", "audioCaptured", "physicalOutputsArmed", "testsPassedInferred", "binarySourceBindingVerified", "transcriptSourceBindingVerified", "physicalHardwareQualified"):
                self.assertIs(report["evidenceBoundary"][field], False)
            self.assertNotIn(str(root), json.dumps(report))

    def test_source_is_resolved_from_repository_not_callers_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "source.txt").write_text("source")
            subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
            report = module.source_observation(root)
            self.assertRegex(report["commit"], r"^[0-9a-f]{40}$")
            self.assertFalse(report["worktreeDirty"])
            (root / "source.txt").write_text("changed")
            self.assertTrue(module.source_observation(root)["worktreeDirty"])

    def test_invalid_inputs_fail_before_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "binary"
            binary.write_bytes(b"bytes")
            for path in (root / "missing", root):
                with self.subTest(path=path), patch.object(module, "diagnose_hardware") as inventory:
                    with self.assertRaises(ValueError):
                        module.collect(root, path, [])
                    inventory.assert_not_called()
            binary.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                module.file_observation(binary)

    def test_cli_preserves_inputs_and_existing_sessions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "binary"
            binary.write_bytes(b"original")
            with patch.object(module, "collect") as collect:
                self.assertEqual(module.main(["--binary", str(binary), "--output", str(binary)]), 2)
                existing = root / "report.json"
                existing.write_text("original")
                self.assertEqual(module.main(["--binary", str(binary), "--output", str(existing)]), 2)
                collect.assert_not_called()
                self.assertEqual(existing.read_text(), "original")
            self.assertEqual(binary.read_bytes(), b"original")

    def test_cli_writes_complete_json_and_cleans_up_failed_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "binary"
            binary.write_bytes(b"fixture")
            output = root / "session.json"
            with patch.object(module, "collect", return_value={"physicalHardwareQualified": False}):
                self.assertEqual(module.main(["--binary", str(binary), "--output", str(output)]), 0)
            self.assertIs(json.loads(output.read_text())["physicalHardwareQualified"], False)
            output.unlink()
            with patch.object(module, "collect", return_value={"physicalHardwareQualified": False}), patch.object(module.os, "replace", side_effect=OSError("fixture error")):
                self.assertEqual(module.main(["--binary", str(binary), "--output", str(output)]), 2)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
