import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "desktop-release-readiness.py"
INVENTORY_SCRIPT = ROOT / "scripts" / "desktop-dependency-inventory.py"
SBOM_SCRIPT = ROOT / "scripts" / "desktop-sbom.py"
MANIFEST_SCRIPT = ROOT / "scripts" / "desktop-artifact-manifest.py"
VERSION_FILES = (
    "requirements-desktop.txt",
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
        self.assertEqual(report["windowsWebViewInstallMode"], "offlineInstaller")

    def test_windows_readiness_rejects_network_dependent_webview_bootstrapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            config_path = root / "desktop" / "src-tauri" / "tauri.conf.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["bundle"]["windows"]["webviewInstallMode"]["type"] = "downloadBootstrapper"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            report = load_script().evaluate(root, "v0.1.0")

            self.assertFalse(report["passed"])
            self.assertEqual(report["windowsWebViewInstallMode"], "downloadBootstrapper")
            self.assertIn("offlineInstaller", " ".join(report["blockers"]))

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
                "distributionChannel": "standard",
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
                "distributionChannel": "standard",
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

    def artifact_evidence(
        self,
        root: Path,
        commit: str = "a" * 40,
        *,
        platform: str = "test-os",
        distribution_channel: str = "standard",
    ):
        artifacts = root / "artifacts"
        artifacts.mkdir()
        inventory = artifacts / "desktop-dependencies.json"
        inventory_result = subprocess.run([
            sys.executable, str(INVENTORY_SCRIPT),
            "--root", str(root),
            "--output", str(inventory),
            "--commit", commit,
            "--version", "0.1.0",
        ], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(inventory_result.returncode, 0, inventory_result.stderr)
        sbom = artifacts / "desktop-sbom.cdx.json"
        sbom_result = subprocess.run([
            sys.executable, str(SBOM_SCRIPT),
            "--inventory", str(inventory),
            "--output", str(sbom),
        ], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(sbom_result.returncode, 0, sbom_result.stderr)
        (artifacts / "installer").write_bytes(b"installer")
        manifest_result = subprocess.run([
            sys.executable, str(MANIFEST_SCRIPT),
            "--directory", str(artifacts),
            "--platform", platform,
            "--distribution-channel", distribution_channel,
            "--commit", "a" * 40,
            "--version", "0.1.0",
        ], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(manifest_result.returncode, 0, manifest_result.stderr)
        return artifacts / "desktop-artifacts.json", inventory, sbom

    def test_windows_online_manifest_requires_download_bootstrapper_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            config_path = root / "desktop" / "src-tauri" / "tauri.conf.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["bundle"]["windows"]["webviewInstallMode"]["type"] = (
                "downloadBootstrapper"
            )
            config_path.write_text(json.dumps(config), encoding="utf-8")
            manifest, inventory, sbom = self.artifact_evidence(
                root,
                platform="Windows",
                distribution_channel="online",
            )
            report = load_script().evaluate(root, "v0.1.0", manifest, inventory, sbom)
            self.assertTrue(report["passed"], report["blockers"])
            self.assertEqual(report["windowsWebViewInstallMode"], "downloadBootstrapper")
            self.assertEqual(report["artifactManifest"]["distributionChannel"], "online")

            config["bundle"]["windows"]["webviewInstallMode"]["type"] = "offlineInstaller"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            mismatched = load_script().evaluate(
                root, "v0.1.0", manifest, inventory, sbom
            )
            self.assertFalse(mismatched["passed"])
            self.assertIn("downloadBootstrapper", " ".join(mismatched["blockers"]))

    def test_dependency_inventory_is_validated_and_bound_to_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            manifest, inventory, sbom = self.artifact_evidence(root)
            report = load_script().evaluate(root, "v0.1.0", manifest, inventory, sbom)
            self.assertTrue(report["passed"], report["blockers"])
            self.assertTrue(report["dependencyInventory"]["manifestBound"])
            self.assertGreater(report["dependencyInventory"]["componentCount"], 0)
            self.assertTrue(report["sbom"]["inventoryBound"])
            self.assertTrue(report["sbom"]["manifestBound"])
            self.assertEqual(report["sbom"]["specVersion"], "1.7")

    def test_dependency_inventory_tamper_fails_manifest_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            manifest, inventory, sbom = self.artifact_evidence(root)
            inventory.write_text(inventory.read_text(encoding="utf-8") + " ", encoding="utf-8")
            report = load_script().evaluate(root, "v0.1.0", manifest, inventory, sbom)
            self.assertFalse(report["passed"])
            self.assertIn("digest does not match", " ".join(report["blockers"]))

    def test_dependency_inventory_cannot_claim_legal_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            manifest, inventory, sbom = self.artifact_evidence(root)
            document = json.loads(inventory.read_text(encoding="utf-8"))
            document["reviewBoundary"]["ownerLegalReviewComplete"] = True
            inventory.write_text(json.dumps(document), encoding="utf-8")
            report = load_script().evaluate(root, "v0.1.0", manifest, inventory, sbom)
            self.assertFalse(report["passed"])
            self.assertIn("cannot claim", " ".join(report["blockers"]))

    def test_dependency_inventory_commit_must_match_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            manifest, inventory, sbom = self.artifact_evidence(root, "b" * 40)
            report = load_script().evaluate(root, "v0.1.0", manifest, inventory, sbom)
            self.assertFalse(report["passed"])
            self.assertIn("sourceCommit does not match", " ".join(report["blockers"]))

    def test_sbom_tamper_and_missing_sbom_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            manifest, inventory, sbom = self.artifact_evidence(root)
            document = json.loads(sbom.read_text(encoding="utf-8"))
            properties = document["metadata"]["component"]["properties"]
            boundary = next(
                item for item in properties
                if item["name"] == "org.stagemesh:dependencyLicensesVerified"
            )
            boundary["value"] = "true"
            sbom.write_text(json.dumps(document), encoding="utf-8")
            report = load_script().evaluate(root, "v0.1.0", manifest, inventory, sbom)
            self.assertFalse(report["passed"])
            self.assertIn("review boundary", " ".join(report["blockers"]))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            manifest, inventory, _ = self.artifact_evidence(root)
            report = load_script().evaluate(root, "v0.1.0", manifest, inventory)
            self.assertFalse(report["passed"])
            self.assertIn("requires a CycloneDX desktop SBOM", " ".join(report["blockers"]))


if __name__ == "__main__":
    unittest.main()
