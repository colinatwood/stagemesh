import contextlib
import io
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch


class FenceEvidenceFailureTests(unittest.TestCase):
    def test_native_failure_is_visible_and_cannot_publish_pass(self):
        script = Path(__file__).resolve().parents[1] / "ci/device_fence_evidence.py"
        for code in (1, 7):
            with self.subTest(code=code):
                completed = subprocess.CompletedProcess(
                    ["fixture"], code, "partial native output\n", "CoreAudio fence removal failed\n"
                )
                errors = io.StringIO()

                def native_run(*args, **kwargs):
                    if kwargs.get("check"):
                        completed.check_returncode()
                    return completed

                with patch.object(sys, "argv", [str(script), "fixture"]), \
                     patch("subprocess.run", side_effect=native_run), \
                     patch("subprocess.check_output") as git, \
                     patch.object(Path, "write_text") as write, \
                     contextlib.redirect_stderr(errors):
                    with self.assertRaises(SystemExit) as stopped:
                        runpy.run_path(str(script), run_name="__main__")
                self.assertEqual(stopped.exception.code, code)
                self.assertIn("partial native output", errors.getvalue())
                self.assertIn("CoreAudio fence removal failed", errors.getvalue())
                write.assert_not_called()
                git.assert_not_called()


if __name__ == "__main__":
    unittest.main()
