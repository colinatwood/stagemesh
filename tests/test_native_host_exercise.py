import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_host_exercise", ROOT / "scripts/native-host-exercise.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class NativeHostExerciseTests(unittest.TestCase):
    def make_program(self, root: Path, body: str | None = None) -> tuple[Path, list[str]]:
        program = root / "smoke.py"
        program.write_text(
            body or
            "import os, sys\n"
            "print('stdout:' + sys.argv[1])\n"
            "print('control:' + os.environ.get('STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST', ''))\n"
            "print('secret:' + os.environ.get('STAGEMESH_AUTH_TOKEN', ''), file=sys.stderr)\n"
        )
        return Path(sys.executable).resolve(), [str(program)]

    def test_binds_execution_transcript_and_removes_inherited_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary, arguments = self.make_program(Path(temporary))
            source = {"commit": "1" * 40, "worktreeDirty": False}
            with patch.object(module.collector, "source_observation", return_value=source), patch.object(
                module.collector, "diagnose_hardware", return_value={"scanStatus": "complete"}
            ), patch.dict(
                os.environ, {"STAGEMESH_AUTH_TOKEN": "must-not-leak"}, clear=False
            ):
                report, transcript = module.exercise(
                    binary, [*arguments, "argument"], {"STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST": "1"}, 10
                )
            self.assertIn(b"stdout:argument", transcript)
            self.assertIn(b"control:1", transcript)
            self.assertIn(b"secret:\n", transcript)
            self.assertNotIn(b"must-not-leak", transcript)
            self.assertEqual(report["execution"]["exitCode"], 0)
            self.assertEqual(report["hardwareInventory"]["scanStatus"], "complete")
            self.assertTrue(report["execution"]["processExitedSuccessfully"])
            self.assertTrue(report["evidenceBoundary"]["transcriptCapturedByRunner"])
            self.assertFalse(report["evidenceBoundary"]["binarySourceBindingVerified"])
            self.assertFalse(report["evidenceBoundary"]["physicalHardwareQualified"])

    def test_rejects_unknown_duplicate_empty_and_excessive_controls(self):
        for values in (["STAGEMESH_AUTH_TOKEN=secret"], ["STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST="],
                       ["STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST=1", "STAGEMESH_ALLOW_SILENT_ENDPOINT_TEST=1"]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                module.parse_opt_ins(values)
        with self.assertRaisesRegex(ValueError, "3600"):
            module.exercise(Path("missing"), [], {}, 3601)

    def test_refuses_dirty_source_by_default_and_labels_explicit_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary, arguments = self.make_program(Path(temporary))
            source = {"commit": "4" * 40, "worktreeDirty": True}
            with patch.object(module.collector, "source_observation", return_value=source), patch.object(
                module.collector, "diagnose_hardware", return_value={"scanStatus": "complete"}
            ):
                with self.assertRaisesRegex(ValueError, "worktree is dirty"):
                    module.exercise(binary, arguments, {}, 10)
                report, _ = module.exercise(binary, arguments, {}, 10, allow_dirty=True)
            self.assertFalse(report["evidenceBoundary"]["cleanSourceSnapshotObserved"])
            self.assertTrue(report["evidenceBoundary"]["dirtySourceExplicitlyAllowed"])

    def test_timeout_is_evidence_not_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary, arguments = self.make_program(
                Path(temporary), "import time\nprint('before-timeout', flush=True)\ntime.sleep(2)\n"
            )
            with patch.object(module.collector, "source_observation", return_value={"commit": "2" * 40, "worktreeDirty": False}), patch.object(
                module.collector, "diagnose_hardware", return_value={"scanStatus": "complete"}
            ):
                report, transcript = module.exercise(binary, arguments, {}, 0.05)
            self.assertTrue(report["execution"]["timedOut"])
            self.assertIsNone(report["execution"]["exitCode"])
            self.assertFalse(report["execution"]["processExitedSuccessfully"])
            self.assertIn(b"before-timeout", transcript)

    def test_refuses_binary_change_during_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary, arguments = self.make_program(Path(temporary))
            observed = module.collector.file_observation(binary)
            changed = dict(observed, sha256="0" * 64)
            with patch.object(module.collector, "file_observation", side_effect=[observed, changed]), patch.object(
                module.collector, "source_observation", return_value={"commit": "3" * 40, "worktreeDirty": False}
            ), patch.object(
                module.collector, "diagnose_hardware", return_value={"scanStatus": "complete"}
            ):
                with self.assertRaisesRegex(ValueError, "binary changed"):
                    module.exercise(binary, arguments, {}, 10)

    def test_writes_atomic_non_overwriting_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "session"
            report = {"physicalHardwareQualified": False}
            transcript = b"evidence\n"
            module.write_bundle(output, report, transcript)
            saved = json.loads((output / "report.json").read_text())
            self.assertEqual(saved["transcript"]["sha256"], hashlib.sha256(transcript).hexdigest())
            with self.assertRaisesRegex(ValueError, "already exists"):
                module.write_bundle(output, report, transcript)


if __name__ == "__main__":
    unittest.main()
