import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-desktop-download.py"
MANIFEST_SCRIPT = ROOT / "scripts" / "desktop-artifact-manifest.py"


def load_script():
    spec = importlib.util.spec_from_file_location("verify_desktop_download", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopDownloadVerifierTests(unittest.TestCase):
    def make_bundle(self, directory: Path, signing: bool = True) -> Path:
        (directory / "StageMesh-setup.exe").write_bytes(b"installer")
        result = subprocess.run([
            sys.executable,
            str(MANIFEST_SCRIPT),
            "--directory", str(directory),
            "--platform", "Windows",
            "--distribution-channel", "offline",
            "--commit", "a" * 40,
            "--version", "0.1.0",
        ], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = directory / "desktop-artifacts.json"
        if signing:
            report = {
                "schemaVersion": 1,
                "product": "StageMesh",
                "status": "not-configured",
                "artifactManifest": {
                    "path": manifest.name,
                    "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                },
                "readyForPublication": False,
            }
            (directory / "signing-verification.json").write_text(
                json.dumps(report) + "\n", encoding="utf-8"
            )
        return manifest

    def test_valid_bundle_passes_and_binds_signing_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_bundle(directory)
            report = load_script().evaluate(directory)
            self.assertTrue(report["passed"])
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["distributionChannel"], "offline")
            self.assertEqual(report["filesVerified"], 1)
            self.assertEqual(report["signingVerificationStatus"], "not-configured")
            self.assertFalse(report["readyForPublication"])

            command = subprocess.run(
                [sys.executable, str(SCRIPT), "--directory", str(directory)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(command.returncode, 0, command.stdout)

    def test_tampered_artifact_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_bundle(directory)
            (directory / "StageMesh-setup.exe").write_bytes(b"tampered")
            report = load_script().evaluate(directory)
            self.assertFalse(report["passed"])
            self.assertIn("SHA-256 mismatch", " ".join(report["blockers"]))

    def test_checksum_disagreement_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_bundle(directory)
            checksum = directory / "SHA256SUMS"
            checksum.write_text("0" * 64 + "  StageMesh-setup.exe\n", encoding="utf-8")
            report = load_script().evaluate(directory)
            self.assertFalse(report["passed"])
            self.assertIn("checksum and manifest disagree", " ".join(report["blockers"]))

    def test_unexpected_file_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_bundle(directory)
            (directory / "injected.dll").write_bytes(b"unexpected")
            report = load_script().evaluate(directory)
            self.assertFalse(report["passed"])
            self.assertIn("unexpected files: injected.dll", " ".join(report["blockers"]))

    def test_signing_report_for_another_manifest_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_bundle(directory)
            report_path = directory / "signing-verification.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["artifactManifest"]["sha256"] = "0" * 64
            report_path.write_text(json.dumps(report), encoding="utf-8")
            result = load_script().evaluate(directory)
            self.assertFalse(result["passed"])
            self.assertEqual(result["signingVerificationStatus"], "invalid")
            self.assertIn("does not match", " ".join(result["blockers"]))

    def test_missing_signing_report_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.make_bundle(directory, signing=False)
            result = load_script().evaluate(directory)
            self.assertFalse(result["passed"])
            self.assertEqual(result["signingVerificationStatus"], "not-present")
            self.assertIn("signing verification report is missing", result["blockers"])

    def test_unsafe_manifest_path_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest_path = self.make_bundle(directory, signing=False)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][0]["path"] = "../StageMesh-setup.exe"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report = load_script().evaluate(directory)
            self.assertFalse(report["passed"])
            self.assertIn("unsafe relative path", " ".join(report["blockers"]))


if __name__ == "__main__":
    unittest.main()
