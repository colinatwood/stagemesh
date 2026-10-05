import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify-desktop-version.py"
VERSION_FILES = (
    "desktop/package.json",
    "desktop/package-lock.json",
    "desktop/src-tauri/tauri.conf.json",
    "desktop/src-tauri/Cargo.toml",
    "desktop/src-tauri/Cargo.lock",
)


class DesktopVersionTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        for relative in VERSION_FILES:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)

    def run_check(self, root: Path, tag: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root), "--tag", tag],
            capture_output=True,
            text=True,
        )

    def test_repository_versions_match_release_tag(self):
        result = self.run_check(ROOT, "v0.1.0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["passed"])
        self.assertEqual(report["version"], "0.1.0")
        self.assertEqual(len(report["manifests"]), 6)

    def test_mismatched_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture(root)
            path = root / "desktop/package.json"
            value = json.loads(path.read_text())
            value["version"] = "0.1.1"
            path.write_text(json.dumps(value))
            result = self.run_check(root, "v0.1.0")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("versions do not match", result.stdout)

    def test_mismatched_or_malformed_tag_fails_closed(self):
        mismatch = self.run_check(ROOT, "v0.2.0")
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("does not match", mismatch.stdout)
        malformed = self.run_check(ROOT, "desktop-latest")
        self.assertNotEqual(malformed.returncode, 0)
        self.assertIn("release tag must be", malformed.stdout)


if __name__ == "__main__":
    unittest.main()
