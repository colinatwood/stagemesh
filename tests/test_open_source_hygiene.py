import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "open-source-hygiene.py"


def load_script():
    spec = importlib.util.spec_from_file_location("open_source_hygiene", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpenSourceHygieneTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        module = load_script()
        for relative in (*module.REQUIRED_TEXT, "LICENSE"):
            source = ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def test_repository_hygiene_passes(self):
        self.assertEqual(load_script().validate(ROOT), [])
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(ROOT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("9 required files", result.stdout)

    def test_missing_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / "SECURITY.md").unlink()
            errors = load_script().validate(root)
            self.assertIn("SECURITY.md must be a regular file", errors)

    def test_retired_name_and_missing_boundary_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            support = root / "SUPPORT.md"
            support.write_text(
                support.read_text(encoding="utf-8").replace(
                    "physical-hardware compatibility", "Stage" + "forge compatibility"
                ),
                encoding="utf-8",
            )
            errors = load_script().validate(root)
            self.assertTrue(any("physical-hardware compatibility" in item for item in errors))
            self.assertTrue(any("retired project name" in item for item in errors))

    def test_release_gate_invokes_hygiene_check(self):
        source = (ROOT / "scripts" / "release-check.py").read_text(encoding="utf-8")
        self.assertIn("open-source-hygiene.py", source)


if __name__ == "__main__":
    unittest.main()
