import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_SCRIPT = ROOT / "scripts" / "desktop-dependency-inventory.py"
SCRIPT = ROOT / "scripts" / "desktop-sbom.py"


def load_script():
    spec = importlib.util.spec_from_file_location("desktop_sbom", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopSbomTests(unittest.TestCase):
    def inventory(self, root: Path) -> Path:
        path = root / "desktop-dependencies.json"
        result = subprocess.run([
            sys.executable,
            str(INVENTORY_SCRIPT),
            "--output", str(path),
            "--commit", "a" * 40,
            "--version", "0.1.0",
        ], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return path

    def test_generates_deterministic_cyclonedx_17_document(self):
        with tempfile.TemporaryDirectory() as temporary:
            inventory = self.inventory(Path(temporary))
            module = load_script()
            first = module.build_sbom(inventory)
            second = module.build_sbom(inventory)

            self.assertEqual(first, second)
            self.assertEqual(first["$schema"], "https://cyclonedx.org/schema/bom-1.7.schema.json")
            self.assertEqual(first["bomFormat"], "CycloneDX")
            self.assertEqual(first["specVersion"], "1.7")
            self.assertEqual(first["version"], 1)
            self.assertTrue(first["serialNumber"].startswith("urn:uuid:"))
            uuid.UUID(first["serialNumber"].removeprefix("urn:uuid:"))

            product = first["metadata"]["component"]
            self.assertEqual(product["type"], "application")
            self.assertEqual(product["name"], "StageMesh")
            self.assertEqual(product["version"], "0.1.0")
            self.assertEqual(product["purl"], "pkg:generic/stagemesh@0.1.0")
            properties = {item["name"]: item["value"] for item in product["properties"]}
            self.assertEqual(properties["org.stagemesh:sourceCommit"], "a" * 40)
            self.assertEqual(properties["org.stagemesh:payloadInclusionVerified"], "false")
            self.assertEqual(properties["org.stagemesh:dependencyLicensesVerified"], "false")
            self.assertEqual(properties["org.stagemesh:ownerLegalReviewComplete"], "false")

            inventory_document = json.loads(inventory.read_text(encoding="utf-8"))
            self.assertEqual(len(first["components"]), inventory_document["counts"]["total"])
            purls = [item["purl"] for item in first["components"]]
            self.assertEqual(first["dependencies"][0]["ref"], product["bom-ref"])
            self.assertEqual(first["dependencies"][0]["dependsOn"], purls)
            self.assertEqual(
                {item["ref"] for item in first["dependencies"][1:]},
                set(purls),
            )

            cargo = next(item for item in first["components"] if item["purl"].startswith("pkg:cargo/"))
            self.assertEqual(cargo["hashes"][0]["alg"], "SHA-256")
            npm = next(item for item in first["components"] if item["purl"] == "pkg:npm/%40tauri-apps/cli@2.12.1")
            self.assertEqual(npm["hashes"][0]["alg"], "SHA-512")
            self.assertEqual(len(npm["hashes"][0]["content"]), 128)

    def test_cli_is_deterministic_and_refuses_input_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = self.inventory(root)
            output = root / "desktop-sbom.cdx.json"
            command = [
                sys.executable, str(SCRIPT),
                "--inventory", str(inventory),
                "--output", str(output),
            ]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = output.read_bytes()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(output.read_bytes(), original)

            refused = subprocess.run([
                sys.executable, str(SCRIPT),
                "--inventory", str(inventory),
                "--output", str(inventory),
            ], capture_output=True, text=True)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("must not overwrite", refused.stderr)

    def test_invalid_boundary_duplicate_and_integrity_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = self.inventory(root)
            original = json.loads(inventory.read_text(encoding="utf-8"))
            original["reviewBoundary"]["dependencyLicensesVerified"] = True
            inventory.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "review boundary"):
                load_script().build_sbom(inventory)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = self.inventory(root)
            document = json.loads(inventory.read_text(encoding="utf-8"))
            document["components"].append(dict(document["components"][0]))
            document["counts"]["total"] += 1
            inventory.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate package"):
                load_script().build_sbom(inventory)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = self.inventory(root)
            document = json.loads(inventory.read_text(encoding="utf-8"))
            npm = next(item for item in document["components"] if "integrity" in item)
            npm["integrity"] = "sha512-not-base64!"
            inventory.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "valid base64"):
                load_script().build_sbom(inventory)

    def test_desktop_workflow_generates_and_tracks_sbom(self):
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
        self.assertIn('"scripts/desktop-sbom.py"', workflow)
        self.assertIn('"tests/test_desktop_sbom.py"', workflow)
        self.assertIn("Generate CycloneDX desktop SBOM", workflow)
        self.assertIn("bundle/desktop-sbom.cdx.json", workflow)

    def test_desktop_workflow_attests_bundle_checksums_and_sbom(self):
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
        self.assertIn("Attest desktop bundle provenance and SBOM", workflow)
        self.assertIn("uses: actions/attest@v4", workflow)
        self.assertIn("subject-checksums: desktop/src-tauri/target/release/bundle/SHA256SUMS", workflow)
        self.assertIn("sbom-path: desktop/src-tauri/target/release/bundle/desktop-sbom.cdx.json", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn("artifact-metadata: write", workflow)


if __name__ == "__main__":
    unittest.main()
