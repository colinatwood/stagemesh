import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "desktop-release-index.py"
MANIFEST_SCRIPT = ROOT / "scripts" / "desktop-artifact-manifest.py"


def load_script():
    spec = importlib.util.spec_from_file_location("desktop_release_index", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopReleaseIndexTests(unittest.TestCase):
    commit = "a" * 40

    def make_bundle(
        self,
        root: Path,
        name: str,
        platform: str,
        *,
        version: str = "0.1.0",
        commit: str | None = None,
        signing_status: str = "not-configured",
    ) -> Path:
        bundle = root / name
        bundle.mkdir()
        (bundle / f"StageMesh-{platform}.installer").write_bytes(
            f"{platform}-installer".encode("utf-8")
        )
        result = subprocess.run(
            [
                sys.executable,
                str(MANIFEST_SCRIPT),
                "--directory",
                str(bundle),
                "--platform",
                platform,
                "--commit",
                commit or self.commit,
                "--version",
                version,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = bundle / "desktop-artifacts.json"
        signing = {
            "schemaVersion": 1,
            "product": "StageMesh",
            "platform": platform.lower(),
            "status": signing_status,
            "artifactManifest": {
                "path": manifest.name,
                "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            },
            "readyForPublication": False,
            "secretValuesIncluded": False,
            "exactArtifacts": [
                {
                    "path": f"StageMesh-{platform}.installer",
                    "status": "bound",
                    "verification": "verified",
                }
            ] if signing_status == "verified" else [],
            "blockers": [],
        }
        (bundle / "signing-verification.json").write_text(
            json.dumps(signing, sort_keys=True) + "\n", encoding="utf-8"
        )
        return bundle

    def make_candidate(self, root: Path, *, signing_status: str = "not-configured") -> None:
        self.make_bundle(root, "stagemesh-desktop-ubuntu-22.04", "Linux", signing_status=signing_status)
        self.make_bundle(root, "stagemesh-desktop-macos-14", "macOS", signing_status=signing_status)
        self.make_bundle(root, "stagemesh-desktop-windows-2022", "Windows", signing_status=signing_status)

    def test_binds_all_platforms_without_claiming_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_candidate(root)

            report = load_script().build_index(
                root, version="0.1.0", source_commit=self.commit
            )

            self.assertEqual(report["documentType"], "org.stagemesh.desktop-release-candidate")
            self.assertEqual(report["candidateId"], "stagemesh-0.1.0-aaaaaaaaaaaa")
            self.assertEqual(
                [item["platform"] for item in report["platforms"]],
                ["Linux", "macOS", "Windows"],
            )
            self.assertTrue(report["summary"]["allBundlesIntegrityVerified"])
            self.assertFalse(report["summary"]["allSignaturesVerified"])
            self.assertTrue(report["readiness"]["readyForUnsignedTesting"])
            self.assertFalse(report["readiness"]["readyForPublication"])
            self.assertFalse(report["readiness"]["ownerLegalReviewComplete"])
            for item in report["platforms"]:
                self.assertTrue(item["downloadVerification"]["passed"])
                self.assertEqual(len(item["artifactManifest"]["sha256"]), 64)
                self.assertFalse(item["qualification"]["cleanHostInstallQualified"])
                self.assertFalse(item["qualification"]["physicalHardwareQualified"])

    def test_verified_signatures_do_not_override_external_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_candidate(root, signing_status="verified")
            report = load_script().build_index(
                root, version="0.1.0", source_commit=self.commit
            )
            self.assertTrue(report["summary"]["allSignaturesVerified"])
            self.assertFalse(report["readiness"]["readyForPublication"])
            self.assertFalse(report["readiness"]["cleanHostInstallQualified"])

    def test_missing_and_duplicate_platforms_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_bundle(root, "linux", "Linux")
            self.make_bundle(root, "mac", "macOS")
            with self.assertRaisesRegex(ValueError, "missing platform bundles: Windows"):
                load_script().build_index(root, version="0.1.0", source_commit=self.commit)
            self.make_bundle(root, "windows-one", "Windows")
            self.make_bundle(root, "windows-two", "Windows")
            with self.assertRaisesRegex(ValueError, "duplicate Windows"):
                load_script().build_index(root, version="0.1.0", source_commit=self.commit)

    def test_version_and_commit_mismatches_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_bundle(root, "linux", "Linux", version="0.1.1")
            self.make_bundle(root, "mac", "macOS")
            self.make_bundle(root, "windows", "Windows")
            with self.assertRaisesRegex(ValueError, "artifact version does not match"):
                load_script().build_index(root, version="0.1.0", source_commit=self.commit)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_bundle(root, "linux", "Linux", commit="b" * 40)
            self.make_bundle(root, "mac", "macOS")
            self.make_bundle(root, "windows", "Windows")
            with self.assertRaisesRegex(ValueError, "source commit does not match"):
                load_script().build_index(root, version="0.1.0", source_commit=self.commit)

    def test_tampered_bundle_fails_download_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_candidate(root)
            installer = root / "stagemesh-desktop-windows-2022" / "StageMesh-Windows.installer"
            installer.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "download verification failed"):
                load_script().build_index(root, version="0.1.0", source_commit=self.commit)

    def test_additional_qualification_claim_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_candidate(root)
            bundle = root / "stagemesh-desktop-macos-14"
            manifest_path = bundle / "desktop-artifacts.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["qualification"]["audibleQualityQualified"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            signing_path = bundle / "signing-verification.json"
            signing = json.loads(signing_path.read_text(encoding="utf-8"))
            signing["artifactManifest"]["sha256"] = hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest()
            signing_path.write_text(json.dumps(signing), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "qualification boundary is invalid"):
                load_script().build_index(root, version="0.1.0", source_commit=self.commit)

    def test_cli_output_is_deterministic_and_rejects_input_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            candidate = workspace / "candidate"
            candidate.mkdir()
            self.make_candidate(candidate)
            output = workspace / "desktop-release-index.json"
            command = [
                sys.executable,
                str(SCRIPT),
                "--directory",
                str(candidate),
                "--version",
                "0.1.0",
                "--commit",
                self.commit,
                "--output",
                str(output),
            ]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = output.read_bytes()
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(json.loads(first.stdout), json.loads(original))

            manifest = candidate / "stagemesh-desktop-ubuntu-22.04" / "desktop-artifacts.json"
            overwrite = subprocess.run(
                command[:-1] + [str(manifest)], cwd=ROOT, capture_output=True, text=True
            )
            self.assertEqual(overwrite.returncode, 2)
            self.assertIn("cannot overwrite", overwrite.stderr)

    def test_desktop_workflow_aggregates_only_after_platform_builds(self):
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("release-candidate:", workflow)
        self.assertIn("needs: build", workflow)
        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn("include-hidden-files: true", workflow)
        self.assertIn("scripts/desktop-release-index.py", workflow)
        self.assertIn("stagemesh-desktop-release-index-${{ github.sha }}", workflow)


if __name__ == "__main__":
    unittest.main()
