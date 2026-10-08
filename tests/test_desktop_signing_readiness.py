import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/desktop-signing-readiness.py"


def load_script():
    spec = importlib.util.spec_from_file_location("desktop_signing_readiness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesktopSigningReadinessTests(unittest.TestCase):
    def test_windows_pfx_reports_names_without_secret_values(self):
        secret = "never-print-this-certificate"
        environment = {
            "STAGEMESH_WINDOWS_SIGNING_MODE": "pfx",
            "WINDOWS_CERTIFICATE": secret,
            "WINDOWS_CERTIFICATE_PASSWORD": "password-secret",
            "STAGEMESH_WINDOWS_CERTIFICATE_THUMBPRINT": "A" * 40,
            "STAGEMESH_WINDOWS_TIMESTAMP_URL": "https://timestamp.example.test",
        }
        report = load_script().evaluate("Windows", environment, "offline")
        self.assertTrue(report["readyForPlatformSigning"])
        self.assertEqual(report["distributionChannel"], "offline")
        self.assertEqual(report["missingInputs"], [])
        self.assertFalse(report["secretValuesIncluded"])
        self.assertNotIn(secret, json.dumps(report))

    def test_windows_requires_mode_and_complete_inputs(self):
        no_mode = load_script().evaluate("windows", {}, "online")
        self.assertFalse(no_mode["readyForPlatformSigning"])
        incomplete = load_script().evaluate("windows", {
            "STAGEMESH_WINDOWS_SIGNING_MODE": "azure-artifact-signing",
            "AZURE_CLIENT_ID": "configured",
        }, "online")
        self.assertFalse(incomplete["readyForPlatformSigning"])
        self.assertIn("AZURE_CLIENT_SECRET", incomplete["missingInputs"])

    def test_macos_accepts_either_complete_notarization_method(self):
        certificate = {
            "APPLE_CERTIFICATE": "certificate-secret",
            "APPLE_CERTIFICATE_PASSWORD": "certificate-password",
            "KEYCHAIN_PASSWORD": "keychain-password",
        }
        apple = load_script().evaluate("macOS", {
            **certificate,
            "APPLE_ID": "configured",
            "APPLE_PASSWORD": "configured",
            "APPLE_TEAM_ID": "configured",
        })
        self.assertTrue(apple["readyForPlatformSigning"])
        self.assertEqual(apple["notarizationMode"], "apple-id")
        api = load_script().evaluate("darwin", {
            **certificate,
            "APPLE_API_KEY": "configured",
            "APPLE_API_ISSUER": "configured",
            "APPLE_API_KEY_PATH": "/private/key.p8",
        })
        self.assertTrue(api["readyForPlatformSigning"])
        self.assertEqual(api["notarizationMode"], "app-store-connect-api")

    def test_unsigned_ci_report_does_not_fail_unless_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "readiness.json"
            normal = subprocess.run([
                sys.executable, str(SCRIPT), "--platform", "Linux", "--output", str(output)
            ], capture_output=True, text=True)
            self.assertEqual(normal.returncode, 0, normal.stderr)
            self.assertFalse(json.loads(output.read_text())["readyForPlatformSigning"])
            required = subprocess.run([
                sys.executable, str(SCRIPT), "--platform", "Linux", "--require-ready"
            ], capture_output=True, text=True)
            self.assertNotEqual(required.returncode, 0)

    def test_distribution_channel_matches_platform(self):
        script = load_script()
        with self.assertRaisesRegex(ValueError, "online or offline"):
            script.evaluate("Windows", {})
        with self.assertRaisesRegex(ValueError, "only Windows"):
            script.evaluate("Linux", {}, "offline")

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "readiness.json"
            result = subprocess.run([
                sys.executable,
                str(SCRIPT),
                "--platform", "Windows",
                "--distribution-channel", "online",
                "--output", str(output),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text())["distributionChannel"], "online")


if __name__ == "__main__":
    unittest.main()
