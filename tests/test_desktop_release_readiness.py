import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "desktop-release-readiness.py"
VERSION_FILES = (
    "desktop/package.json",
    "desktop/package-lock.json",
    "desktop/src-tauri/tauri.conf.json",
    "desktop/src-tauri/Cargo.toml",
    "desktop/src-tauri/Cargo.lock",
)


def load_script():
    spec = importlib.util.spec_from_file_location("desktop_release_readiness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopReleaseReadinessTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        for relative in VERSION_FILES:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        for relative in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            shutil.copy2(ROOT / relative, root / relative)

    def test_repository_is_ready_for_unsigned_testing_but_not_publication(self):
        report = load_script().evaluate(ROOT, "v0.1.0")
        self.assertTrue(report["passed"])
        self.assertTrue(report["readyForUnsignedTesting"])
        self.assertFalse(report["readyForPublication"])
        self.assertEqual(report["version"], "0.1.0")

    def test_missing_distribution_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / "LICENSE").unlink()
            report = load_script().evaluate(root, "v0.1.0")
            self.assertFalse(report["passed"])
            self.assertIn("LICENSE", " ".join(report["blockers"]))

    def test_manifest_cannot_claim_external_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            manifest = root / "desktop-artifacts.json"
            manifest.write_text(json.dumps({
                "schemaVersion": 1,
                "product": "StageMesh",
                "version": "0.1.0",
                "platform": "test-os",
                "sourceCommit": "a" * 40,
                "signed": False,
                "qualification": {
                    "softwarePackageBuilt": True,
                    "cleanHostInstallQualified": True,
                    "physicalHardwareQualified": False,
                },
                "files": [{"path": "installer", "bytes": 1, "sha256": "b" * 64}],
            }), encoding="utf-8")
            report = load_script().evaluate(root, "v0.1.0", manifest)
            self.assertFalse(report["passed"])
            self.assertIn("cleanHostInstallQualified", " ".join(report["blockers"]))

    def test_signed_manifest_is_not_accepted_by_unsigned_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            manifest = root / "desktop-artifacts.json"
            manifest.write_text(json.dumps({
                "schemaVersion": 1,
                "product": "StageMesh",
                "version": "0.1.0",
                "platform": "test-os",
                "sourceCommit": "a" * 40,
                "signed": True,
                "qualification": {
                    "softwarePackageBuilt": True,
                    "cleanHostInstallQualified": False,
                    "physicalHardwareQualified": False,
                },
                "files": [{"path": "installer", "bytes": 1, "sha256": "b" * 64}],
            }), encoding="utf-8")
            report = load_script().evaluate(root, "v0.1.0", manifest)
            self.assertFalse(report["passed"])
            self.assertIn("signed=false", " ".join(report["blockers"]))


if __name__ == "__main__":
    unittest.main()
