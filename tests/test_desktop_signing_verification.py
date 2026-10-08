import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/desktop-signing-verification.py"
MANIFEST_SCRIPT = ROOT / "scripts/desktop-artifact-manifest.py"


def load_script():
    spec = importlib.util.spec_from_file_location("desktop_signing_verification", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopSigningVerificationTests(unittest.TestCase):
    def make_manifest(
        self,
        directory: Path,
        filename: str = "StageMesh-setup.exe",
        *,
        platform: str = "Windows",
        distribution_channel: str = "offline",
    ) -> Path:
        (directory / filename).write_bytes(b"signed-artifact")
        result = subprocess.run([
            sys.executable,
            str(MANIFEST_SCRIPT),
            "--directory", str(directory),
            "--platform", platform,
            "--distribution-channel", distribution_channel,
            "--commit", "a" * 40,
            "--version", "0.1.0",
        ], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return directory / "desktop-artifacts.json"

    def fake_signtool(self, directory: Path) -> Path:
        tool = directory / "signtool"
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
        return tool

    def test_exact_file_is_bound_to_manifest_before_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = self.make_manifest(directory)
            tool = self.fake_signtool(directory)
            report = load_script().evaluate(
                "Windows",
                manifest,
                [directory / "StageMesh-setup.exe"],
                environment={
                    "STAGEMESH_SIGNING_VERIFICATION_MODE": "advisory",
                    "STAGEMESH_SIGNTOOL_PATH": str(tool),
                },
            )
            self.assertEqual(report["status"], "verified")
            self.assertEqual(report["exactArtifacts"][0]["verification"], "verified")
            self.assertEqual(report["exactArtifacts"][0]["path"], "StageMesh-setup.exe")
            self.assertNotIn(str(directory), json.dumps(report))
            self.assertEqual(report["artifactManifest"]["path"], "desktop-artifacts.json")
            self.assertEqual(
                report["artifactManifest"]["sha256"],
                hashlib.sha256(manifest.read_bytes()).hexdigest(),
            )
            self.assertFalse(report["readyForPublication"])
            self.assertFalse(report["secretValuesIncluded"])

            (directory / "StageMesh-setup.exe").write_bytes(b"changed-after-manifest")
            changed = load_script().evaluate(
                "Windows",
                manifest,
                [directory / "StageMesh-setup.exe"],
                environment={
                    "STAGEMESH_SIGNING_VERIFICATION_MODE": "advisory",
                    "STAGEMESH_SIGNTOOL_PATH": str(tool),
                },
            )
            self.assertEqual(changed["status"], "failed")
            self.assertTrue(any("digest mismatch" in blocker for blocker in changed["blockers"]))

    def test_unconfigured_unsigned_ci_is_advisory_but_required_mode_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = self.make_manifest(directory)
            normal = subprocess.run([
                sys.executable, str(SCRIPT),
                "--platform", "Windows",
                "--manifest", str(manifest),
                "--artifact", str(directory / "StageMesh-setup.exe"),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(normal.returncode, 0, normal.stderr)
            report = json.loads(normal.stdout)
            self.assertEqual(report["status"], "not-configured")
            self.assertIn("STAGEMESH_SIGNING_VERIFICATION_MODE", " ".join(report["blockers"]))

            required = subprocess.run([
                sys.executable, str(SCRIPT),
                "--platform", "Windows",
                "--manifest", str(manifest),
                "--artifact", str(directory / "StageMesh-setup.exe"),
                "--require-verified",
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(required.returncode, 0)

    def test_linux_keeps_package_policy_as_an_explicit_blocker(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = self.make_manifest(
                directory,
                "StageMesh.AppImage",
                platform="Linux",
                distribution_channel="standard",
            )
            report = load_script().evaluate(
                "Linux", manifest, [directory / "StageMesh.AppImage"], environment={}
            )
            self.assertEqual(report["status"], "not-configured")
            self.assertIn("Linux package/repository signing policy", " ".join(report["blockers"]))

    def test_selected_missing_artifact_fails_overall_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = self.make_manifest(directory)
            report = load_script().evaluate(
                "Windows", manifest, [directory / "missing.exe"], environment={}
            )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["exactArtifacts"][0]["status"], "failed")
            self.assertEqual(report["exactArtifacts"][0]["path"], "missing.exe")
            self.assertNotIn(str(directory), json.dumps(report))

    def test_artifact_outside_manifest_directory_fails_overall_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            manifest = self.make_manifest(artifacts)
            outside = root / "StageMesh-setup.exe"
            outside.write_bytes(b"signed-artifact")
            report = load_script().evaluate("Windows", manifest, [outside], environment={})
            self.assertEqual(report["status"], "failed")
            self.assertIn("outside manifest directory", " ".join(report["blockers"]))
            self.assertEqual(report["exactArtifacts"][0]["path"], "StageMesh-setup.exe")
            self.assertEqual(
                report["exactArtifacts"][0]["pathScope"], "outside-manifest-directory"
            )
            self.assertNotIn(str(root), json.dumps(report))


if __name__ == "__main__":
    unittest.main()
