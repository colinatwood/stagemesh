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

    def assert_cli_failure(self, directory):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--directory", str(directory)],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertFalse(report["passed"])
        self.assertFalse(report["readyForPublication"])
        self.assertTrue(report["blockers"])
        self.assertNotIn(str(directory), result.stdout)
        return report

    def test_malformed_channel_and_signing_status_return_failed_json(self):
        for name, field in (("desktop-artifacts.json", "distributionChannel"),
                            ("signing-verification.json", "status")):
            for invalid in ([], {}, 0, None):
                with self.subTest(name=name, invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    self.make_bundle(directory)
                    path = directory / name
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value[field] = invalid
                    path.write_text(json.dumps(value), encoding="utf-8")
                    self.assert_cli_failure(directory)

    def test_schema_version_requires_an_integer_in_both_sidecars(self):
        for name in ("desktop-artifacts.json", "signing-verification.json"):
            for invalid in (True, 1.0, "1"):
                with self.subTest(name=name, invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    self.make_bundle(directory)
                    path = directory / name
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["schemaVersion"] = invalid
                    path.write_text(json.dumps(value), encoding="utf-8")
                    if name == "desktop-artifacts.json":
                        signing_path = directory / "signing-verification.json"
                        signing = json.loads(signing_path.read_text(encoding="utf-8"))
                        signing["artifactManifest"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                        signing_path.write_text(json.dumps(signing), encoding="utf-8")
                    self.assert_cli_failure(directory)

    def test_duplicate_json_fields_are_rejected_at_every_depth(self):
        for name in ("desktop-artifacts.json", "signing-verification.json"):
            for addition in ('"schemaVersion":1,', '"extra":{"key":1,"key":2},'):
                with self.subTest(name=name, addition=addition), tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    self.make_bundle(directory)
                    path = directory / name
                    path.write_text("{" + addition + path.read_text(encoding="utf-8")[1:], encoding="utf-8")
                    report = self.assert_cli_failure(directory)
                    self.assertIn("duplicate", " ".join(report["blockers"]))

    def test_nonfinite_json_values_fail_even_in_unused_fields(self):
        for name in ("desktop-artifacts.json", "signing-verification.json"):
            for value in ("NaN", "Infinity", "-Infinity", "1e10000", "-1e10000"):
                with self.subTest(name=name, value=value), tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    self.make_bundle(directory)
                    path = directory / name
                    path.write_text('{"extra":' + value + ',' + path.read_text(encoding="utf-8")[1:], encoding="utf-8")
                    report = self.assert_cli_failure(directory)
                    self.assertIn("non-finite", " ".join(report["blockers"]))

    def test_invalid_encoding_and_excessive_nesting_return_failed_json(self):
        for payload in (b"\xff", b'{"extra":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"):
            for name in ("desktop-artifacts.json", "signing-verification.json", "SHA256SUMS"):
                with self.subTest(name=name, prefix=payload[:20]), tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    self.make_bundle(directory)
                    (directory / name).write_bytes(payload)
                    self.assert_cli_failure(directory)

    def test_metadata_size_limit_returns_failed_json(self):
        module = load_script()
        for name in ("desktop-artifacts.json", "signing-verification.json", "SHA256SUMS"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                self.make_bundle(directory)
                (directory / name).write_bytes(b" " * (module.MAX_METADATA_BYTES + 1))
                report = self.assert_cli_failure(directory)
                self.assertIn("size limit", " ".join(report["blockers"]))


if __name__ == "__main__":
    unittest.main()

