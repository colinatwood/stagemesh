import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "desktop-dependency-inventory.py"
INPUTS = (
    "desktop/package-lock.json",
    "desktop/src-tauri/Cargo.lock",
    "requirements-desktop.txt",
)


def load_script():
    spec = importlib.util.spec_from_file_location("desktop_dependency_inventory", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopDependencyInventoryTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        for relative in INPUTS:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)

    def test_records_all_locked_ecosystems_with_explicit_review_boundary(self):
        report = load_script().build_inventory(ROOT, "0.1.0", "a" * 40)
        self.assertEqual(report["documentType"], "org.stagemesh.desktop-dependency-inventory")
        self.assertGreater(report["counts"]["cargo"], 0)
        self.assertGreater(report["counts"]["npm"], 0)
        self.assertEqual(report["counts"]["pypi"], 1)
        self.assertEqual(report["counts"]["total"], len(report["components"]))
        packages = {
            (item["ecosystem"], item["name"], item["version"])
            for item in report["components"]
        }
        self.assertIn(("npm", "@tauri-apps/cli", "2.12.1"), packages)
        self.assertIn(("cargo", "tauri", "2.12.1"), packages)
        self.assertIn(("pypi", "pyinstaller", "6.16.0"), packages)
        tauri_cli = next(
            item for item in report["components"]
            if item["ecosystem"] == "npm" and item["name"] == "@tauri-apps/cli"
        )
        self.assertEqual(tauri_cli["purl"], "pkg:npm/%40tauri-apps/cli@2.12.1")
        self.assertFalse(report["reviewBoundary"]["standardSbom"])
        self.assertFalse(report["reviewBoundary"]["dependencyLicensesVerified"])
        self.assertFalse(report["reviewBoundary"]["ownerLegalReviewComplete"])

    def test_cli_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "desktop-dependencies.json"
            command = [
                sys.executable, str(SCRIPT),
                "--output", str(output),
                "--commit", "b" * 40,
                "--version", "0.1.0",
            ]
            first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = output.read_bytes()
            second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(json.loads(original)["sourceCommit"], "b" * 40)

    def test_rejects_unpinned_python_dependency(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / "requirements-desktop.txt").write_text("pyinstaller>=6\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact name==version pin"):
                load_script().build_inventory(root, "0.1.0", "c" * 40)

    def test_rejects_invalid_commit(self):
        with self.assertRaisesRegex(ValueError, "40-character"):
            load_script().build_inventory(ROOT, "0.1.0", "main")


if __name__ == "__main__":
    unittest.main()
