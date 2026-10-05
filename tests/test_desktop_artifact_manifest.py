import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "desktop-artifact-manifest.py"


class DesktopArtifactManifestTests(unittest.TestCase):
    def run_manifest(self, directory: Path, version: str = "0.1.0"):
        return subprocess.run([
            sys.executable,
            str(SCRIPT),
            "--directory", str(directory),
            "--platform", "test-os",
            "--commit", "a" * 40,
            "--version", version,
        ], cwd=ROOT, text=True, capture_output=True)

    def test_records_deterministic_checksums_and_qualification_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = Path(temporary)
            (artifacts / "installer.msi").write_bytes(b"installer")
            nested = artifacts / "app"
            nested.mkdir()
            (nested / "stagemesh").write_bytes(b"binary")

            first = self.run_manifest(artifacts)
            self.assertEqual(first.returncode, 0, first.stderr)
            original_manifest = (artifacts / "desktop-artifacts.json").read_bytes()
            original_checksums = (artifacts / "SHA256SUMS").read_bytes()

            manifest = json.loads(original_manifest)
            self.assertEqual(manifest["schemaVersion"], 1)
            self.assertEqual(manifest["version"], "0.1.0")
            self.assertEqual(manifest["platform"], "test-os")
            self.assertFalse(manifest["signed"])
            self.assertFalse(manifest["qualification"]["cleanHostInstallQualified"])
            self.assertFalse(manifest["qualification"]["physicalHardwareQualified"])
            self.assertEqual(
                [item["path"] for item in manifest["files"]],
                ["app/stagemesh", "installer.msi"],
            )
            expected = hashlib.sha256(b"installer").hexdigest()
            self.assertIn(f"{expected}  installer.msi\n", original_checksums.decode())

            second = self.run_manifest(artifacts)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((artifacts / "desktop-artifacts.json").read_bytes(), original_manifest)
            self.assertEqual((artifacts / "SHA256SUMS").read_bytes(), original_checksums)

            (artifacts / "signing-verification.json").write_text(
                '{"status":"verified"}\n', encoding="utf-8"
            )
            third = self.run_manifest(artifacts)
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertEqual((artifacts / "desktop-artifacts.json").read_bytes(), original_manifest)
            self.assertEqual((artifacts / "SHA256SUMS").read_bytes(), original_checksums)

    def test_rejects_an_empty_artifact_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_manifest(Path(temporary))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("contains no files", result.stderr)

    def test_rejects_an_invalid_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = Path(temporary)
            (artifacts / "installer.msi").write_bytes(b"installer")
            result = self.run_manifest(artifacts, "latest")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("version must use", result.stderr)


if __name__ == "__main__":
    unittest.main()
