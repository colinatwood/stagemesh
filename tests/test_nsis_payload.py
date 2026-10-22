"""Fail-closed unit fixtures; real NSIS acceptance runs separately in Windows CI."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nsis_payload", ROOT / "tests/windows_nsis_payload.py")
nsis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nsis)


class NsisPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "nsis").mkdir()
        self.installer = self.root / "nsis/setup.exe"
        self.installer.write_bytes(b"temporary NSIS fixture")
        self.payload = b"MZtemporary desktop fixture"
        binary = self.root / nsis.binding.EXECUTABLE
        binary.write_bytes(self.payload)
        nsis.binding.record(self.root, binary, "nsis", "a" * 40, "online")
        self.listing = f"Type = Nsis\n\nPath = $INSTDIR\\stagemesh-desktop.exe\nSize = {len(self.payload)}\n\n"

    def verify(self, listing=None, payload=None):
        responses = [subprocess.CompletedProcess([], 0, (listing or self.listing).encode()),
                     subprocess.CompletedProcess([], 0, self.payload if payload is None else payload)]
        with mock.patch.object(nsis.subprocess, "run", side_effect=responses) as run:
            result = nsis.verify(self.root, Path(sys.executable).resolve(), "a" * 40, "online")
        return result, run

    def test_matching_payload_uses_only_decompressor_and_reports_narrow_boundary(self):
        result, run = self.verify()
        self.assertTrue(result["referenceMatchesExtractedPayload"])
        self.assertFalse(result["installerExecuted"])
        self.assertFalse(result["sourceProvenanceVerified"])
        for call in run.call_args_list:
            self.assertEqual(call.args[0][0], str(Path(sys.executable).resolve()))
            self.assertIn("--", call.args[0])
        self.assertIn("-so", run.call_args.args[0])
        self.assertEqual(run.call_args.args[0][-1], "$INSTDIR\\stagemesh-desktop.exe")

    def test_ambiguous_missing_or_unsafe_members_are_rejected(self):
        for listing in ("Type = Nsis\n", self.listing + self.listing.split("\n\n", 1)[1],
                        self.listing.replace("$INSTDIR\\", "..\\"),
                        self.listing.replace("$INSTDIR\\", "C:\\"),
                        self.listing.replace("Type = Nsis", "Type = zip"),
                        self.listing.replace(f"Size = {len(self.payload)}", "Size = 9999999999")):
            with self.subTest(listing=listing), self.assertRaises(ValueError):
                nsis.executable_member(listing)

    def test_size_mismatch_and_changed_executable_bytes_fail(self):
        for payload in (b"", b"MZ" + b"x" * (len(self.payload) - 2)):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.verify(payload=payload)

    def test_wrong_candidate_or_installer_never_invokes_decompressor(self):
        with mock.patch.object(nsis.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                nsis.verify(self.root, Path(sys.executable).resolve(), "b" * 40, "online")
            self.installer.write_bytes(b"changed installer")
            with self.assertRaises(ValueError):
                nsis.verify(self.root, Path(sys.executable).resolve(), "a" * 40, "online")
        run.assert_not_called()

    def test_installer_mutation_during_extraction_fails(self):
        def response(*args, **kwargs):
            if "-so" in args[0]:
                self.installer.write_bytes(b"changed during extraction")
                return subprocess.CompletedProcess([], 0, self.payload)
            return subprocess.CompletedProcess([], 0, self.listing.encode())
        with mock.patch.object(nsis.subprocess, "run", side_effect=response):
            with self.assertRaisesRegex(ValueError, "changed during"):
                nsis.verify(self.root, Path(sys.executable).resolve(), "a" * 40, "online")


if __name__ == "__main__":
    unittest.main()
