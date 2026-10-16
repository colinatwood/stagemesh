import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/desktop-executable-binding.py"
spec = importlib.util.spec_from_file_location("desktop_executable_binding", SCRIPT)
binding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(binding)
SHA = "a" * 40


class DesktopExecutableBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.bundle = self.root / "download"
        self.bundle.mkdir()
        self.build = self.root / "build" / binding.EXECUTABLE
        self.build.parent.mkdir()
        self.selected = self.root / "installed" / binding.EXECUTABLE
        self.selected.parent.mkdir()
        for kind, name, content in (("msi", "StageMesh.msi", b"MSI installer"), ("nsis", "StageMesh-setup.exe", b"NSIS installer")):
            (self.bundle / kind).mkdir()
            (self.bundle / kind / name).write_bytes(content)
            self.build.write_bytes((kind + " executable").encode())
            binding.record(self.bundle, self.build, kind, SHA, "offline")
        self.selected.write_bytes(b"msi executable")
        self.seal()

    def seal(self):
        subprocess.run([sys.executable, str(ROOT / "scripts/desktop-artifact-manifest.py"),
                        "--directory", str(self.bundle), "--platform", "Windows",
                        "--distribution-channel", "offline", "--commit", SHA, "--version", "0.1.0"],
                       check=True, capture_output=True)
        manifest = self.bundle / "desktop-artifacts.json"
        (self.bundle / "signing-verification.json").write_text(json.dumps({
            "schemaVersion": 1, "product": "StageMesh", "status": "not-configured",
            "artifactManifest": {"path": manifest.name, "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()},
            "readyForPublication": False,
        }), encoding="utf-8")

    def check(self, installer="msi/StageMesh.msi", commit=SHA, channel="offline"):
        return binding.check(self.bundle, self.selected, installer, commit, channel)

    def change_reference(self, **changes):
        path = self.bundle / "executable-bindings/msi.json"
        value = json.loads(path.read_text())
        value.update(changes)
        path.write_text(json.dumps(value), encoding="utf-8")
        self.seal()

    def test_installer_variants_have_independent_executable_references(self):
        before = {p: p.read_bytes() for p in self.bundle.rglob("*") if p.is_file()}
        report = self.check()
        self.assertTrue(report["passed"], report)
        self.assertTrue(report["installedExecutableMatchesCandidateReference"])
        for key in ("sourceProvenanceVerified", "publisherAuthenticated", "installerPayloadExtracted",
                    "installedLocationVerified", "cleanHostInstallQualified", "physicalHardwareQualified"):
            self.assertIs(report[key], False)
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertFalse(self.check("nsis/StageMesh-setup.exe")["passed"])
        self.selected.write_bytes(b"nsis executable")
        self.assertTrue(self.check("nsis/StageMesh-setup.exe")["passed"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.bundle.rglob("*") if p.is_file()})

    def test_wrong_source_or_channel_fails_even_when_bytes_match(self):
        self.assertFalse(self.check(commit="b" * 40)["passed"])
        self.assertFalse(self.check(channel="online")["passed"])
        self.assertFalse(self.check(commit="main")["passed"])

    def test_installer_and_reference_tampering_fail_bundle_integrity(self):
        for path in (self.bundle / "msi/StageMesh.msi", self.bundle / "executable-bindings/msi.json"):
            original = path.read_bytes()
            path.write_bytes(b"tampered")
            report = self.check()
            self.assertFalse(report["passed"])
            self.assertFalse(report["candidateIntegrityVerified"])
            path.write_bytes(original)

    def test_reference_must_bind_the_exact_selected_installer(self):
        self.change_reference(installer={"path": "msi/other.msi", "bytes": 13, "sha256": "c" * 64})
        self.assertFalse(self.check()["passed"])

    def test_reference_installer_hash_must_match_verified_manifest(self):
        reference = json.loads((self.bundle / "executable-bindings/msi.json").read_text())
        reference["installer"]["sha256"] = "c" * 64
        self.change_reference(installer=reference["installer"])
        self.assertFalse(self.check()["passed"])

    def test_rehashed_reference_cannot_claim_attestation_or_mix_candidates(self):
        for changes in ({"sourceCommit": "b" * 40}, {"distributionChannel": "online"},
                        {"sourceProvenanceVerified": True}, {"installerPayloadExtracted": True},
                        {"schemaVersion": True}):
            original = (self.bundle / "executable-bindings/msi.json").read_bytes()
            self.change_reference(**changes)
            self.assertFalse(self.check()["passed"], changes)
            (self.bundle / "executable-bindings/msi.json").write_bytes(original)
            self.seal()

    def test_old_candidate_without_reference_fails(self):
        (self.bundle / "executable-bindings/msi.json").unlink()
        self.seal()
        self.assertFalse(self.check()["passed"])

    def test_duplicate_json_keys_fail_even_in_an_internally_rehashed_bundle(self):
        path = self.bundle / "executable-bindings/msi.json"
        path.write_text('{"schemaVersion":1,"schemaVersion":1}', encoding="utf-8")
        self.seal()
        self.assertFalse(self.check()["passed"])

    def test_installer_paths_cannot_escape_or_select_another_kind(self):
        for path in ("../StageMesh.msi", "/msi/StageMesh.msi", "msi/../StageMesh.msi", "msi\\StageMesh.msi",
                     "msi/C:StageMesh.msi", "msi/StageMesh.exe", "nsis/StageMesh.msi"):
            self.assertFalse(self.check(path)["passed"], path)

    def test_selected_file_cannot_be_inside_bundle_or_indirected(self):
        inside = self.bundle / binding.EXECUTABLE
        inside.write_bytes(b"msi executable")
        self.seal()
        self.assertFalse(binding.check(self.bundle, inside, "msi/StageMesh.msi", SHA, "offline")["passed"])
        self.selected.unlink()
        try:
            self.selected.symlink_to(self.build)
        except OSError:
            self.skipTest("symlink creation not permitted")
        self.assertFalse(self.check()["passed"])

    def test_record_rejects_duplicate_ambiguous_or_empty_inputs(self):
        with self.assertRaises(FileExistsError):
            binding.record(self.bundle, self.build, "msi", SHA, "offline")
        (self.bundle / "msi/other.msi").write_bytes(b"other")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            binding.record(self.bundle, self.build, "msi", SHA, "offline")
        self.selected.write_bytes(b"")
        self.assertFalse(self.check()["passed"])

    def test_file_changed_during_hashing_is_rejected(self):
        original = hashlib.sha256
        target = self.selected
        class MutatingDigest:
            def __init__(self):
                self.digest = original()
            def update(self, value):
                self.digest.update(value)
                target.write_bytes(b"changed while hashing")
            def hexdigest(self):
                return self.digest.hexdigest()
        with mock.patch.object(binding.hashlib, "sha256", MutatingDigest):
            with self.assertRaisesRegex(ValueError, "changed while"):
                binding.snapshot(target)

    def test_cli_and_packaged_companion_are_usable(self):
        command = [sys.executable, str(SCRIPT), "check", "--directory", str(self.bundle),
                   "--executable", str(self.selected), "--installer", "msi/StageMesh.msi",
                   "--commit", SHA, "--distribution-channel", "offline"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.selected.write_bytes(b"wrong executable")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["passed"])
        tools = self.root / "tools"
        tools.mkdir()
        (tools / "verify-installed-executable.py").write_bytes(SCRIPT.read_bytes())
        (tools / "verify-download.py").write_bytes((ROOT / "scripts/verify-desktop-download.py").read_bytes())
        self.selected.write_bytes(b"msi executable")
        command[1] = str(tools / "verify-installed-executable.py")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
