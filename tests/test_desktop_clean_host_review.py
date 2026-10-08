import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "desktop-clean-host-review.py"
TRACKS = (
    ("Windows", "exe"),
    ("Windows", "msi"),
    ("macOS", "dmg"),
    ("Linux", "deb"),
    ("Linux", "appimage"),
)


def load_script():
    spec = importlib.util.spec_from_file_location("desktop_clean_host_review", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DesktopCleanHostReviewTests(unittest.TestCase):
    commit = "1" * 40
    version = "0.1.0"

    def write_index(self, root: Path, *, channelled: bool = False) -> Path:
        platforms = []
        for position, platform in enumerate(("Linux", "macOS", "Windows"), start=1):
            platforms.append({
                "platform": platform,
                "artifactManifest": {
                    "path": f"{platform}/desktop-artifacts.json",
                    "bytes": 100 + position,
                    "sha256": str(position) * 64,
                },
                "qualification": {"cleanHostInstallQualified": False},
            })
        if channelled:
            for entry in platforms:
                entry["distributionChannel"] = "online" if entry["platform"] == "Windows" else "standard"
            platforms.append({
                "platform": "Windows",
                "distributionChannel": "offline",
                "artifactManifest": {"path": "Windows-offline/desktop-artifacts.json", "bytes": 104, "sha256": "4" * 64},
                "qualification": {"cleanHostInstallQualified": False},
            })
        value = {
            "documentType": "org.stagemesh.desktop-release-candidate",
            "schemaVersion": 1,
            "product": "StageMesh",
            "version": self.version,
            "sourceCommit": self.commit,
            "candidateId": f"stagemesh-{self.version}-{self.commit[:12]}",
            "platforms": platforms,
            "readiness": {"cleanHostInstallQualified": False},
        }
        path = root / "desktop-release-index.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def write_evidence(self, root: Path, platform: str, installer_format: str, *, suffix: str = "", channel: str | None = None) -> Path:
        index = json.loads((root / "desktop-release-index.json").read_text(encoding="utf-8"))
        manifest = next(item["artifactManifest"] for item in index["platforms"] if item["platform"] == platform and (channel is None or item.get("distributionChannel") == channel))
        document_type = (
            "org.stagemesh.windows-desktop-clean-host-evidence"
            if platform == "Windows"
            else "org.stagemesh.posix-desktop-clean-host-evidence"
        )
        candidate = {
            "version": self.version,
            "sourceCommit": self.commit,
            "manifest": {"bytes": manifest["bytes"], "sha256": manifest["sha256"]},
            "installer": {
                "name": f"StageMesh.{installer_format}",
                "format": installer_format,
                "bytes": 1234,
                "sha256": hashlib.sha256(f"{platform}/{installer_format}".encode()).hexdigest(),
            },
        }
        if platform != "Windows":
            candidate["platform"] = platform
        value = {
            "documentType": document_type,
            "schemaVersion": 1,
            "product": "StageMesh",
            "candidate": candidate,
            "runner": {
                "runnerIdHash": "sha256:" + hashlib.sha256(f"{platform}/{installer_format}".encode()).hexdigest(),
                "os": {"name": platform},
            },
            "phases": [
                {"phase": phase, "passed": True, "checks": {"fixture": True}}
                for phase in ("baseline", "installed", "restarted", "upgraded", "uninstalled")
            ],
            "summary": {
                "requiredPhases": ["baseline", "installed", "restarted", "upgraded", "uninstalled"],
                "passedPhases": ["baseline", "installed", "restarted", "upgraded", "uninstalled"],
                "allRequiredPhasesPassed": True,
            },
            "readiness": {
                "readyForQualificationReview": True,
                "cleanHostInstallQualified": False,
                "physicalHardwareQualified": False,
            },
        }
        path = root / f"{platform.lower()}-{installer_format}{suffix}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def complete_inputs(self, root: Path):
        index = self.write_index(root)
        evidence = [self.write_evidence(root, platform, installer_format) for platform, installer_format in TRACKS]
        return index, evidence

    def test_complete_matrix_is_owner_review_ready_but_never_qualified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index, evidence = self.complete_inputs(root)
            report = load_script().build_review(index, evidence)

            self.assertTrue(report["summary"]["allEvidenceBoundToCandidate"])
            self.assertEqual(report["summary"]["reviewReadyTrackCount"], 5)
            self.assertTrue(report["readiness"]["readyForOwnerReview"])
            self.assertFalse(report["readiness"]["ownerReviewComplete"])
            self.assertFalse(report["readiness"]["cleanHostInstallQualified"])
            self.assertFalse(report["readiness"]["accessibilityQualified"])
            self.assertFalse(report["readiness"]["physicalHardwareQualified"])
            self.assertEqual(
                [(item["platform"], item["installer"]["format"]) for item in report["evidence"]],
                list(TRACKS),
            )
            self.assertEqual(report["candidate"]["sourceCommit"], self.commit)

    def test_partial_matrix_stays_valid_and_reports_exact_missing_tracks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = self.write_index(root)
            evidence = [self.write_evidence(root, "Windows", "exe")]
            report = load_script().build_review(index, evidence)

            self.assertFalse(report["summary"]["allRequiredTracksReviewReady"])
            self.assertFalse(report["readiness"]["readyForOwnerReview"])
            self.assertIn("Windows/msi", report["readiness"]["blockers"][0])
            self.assertIn("Linux/appimage", report["readiness"]["blockers"][0])

    def test_mismatched_candidate_and_manifest_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = self.write_index(root)
            evidence = self.write_evidence(root, "Linux", "deb")
            value = json.loads(evidence.read_text(encoding="utf-8"))
            value["candidate"]["sourceCommit"] = "2" * 40
            evidence.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source commit"):
                load_script().build_review(index, [evidence])

            value["candidate"]["sourceCommit"] = self.commit
            value["candidate"]["manifest"]["sha256"] = "9" * 64
            evidence.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manifest does not match"):
                load_script().build_review(index, [evidence])

    def test_duplicate_track_and_incomplete_phases_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = self.write_index(root)
            first = self.write_evidence(root, "macOS", "dmg")
            second = self.write_evidence(root, "macOS", "dmg", suffix="-copy")
            with self.assertRaisesRegex(ValueError, "duplicate clean-host evidence track"):
                load_script().build_review(index, [first, second])

            value = json.loads(first.read_text(encoding="utf-8"))
            value["phases"] = value["phases"][:-1]
            first.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "all required phases"):
                load_script().build_review(index, [first])

    def test_false_qualification_claim_and_unsupported_track_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = self.write_index(root)
            evidence = self.write_evidence(root, "Windows", "exe")
            value = json.loads(evidence.read_text(encoding="utf-8"))
            value["readiness"]["cleanHostInstallQualified"] = True
            evidence.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "qualification boundary"):
                load_script().build_review(index, [evidence])

            value["readiness"]["cleanHostInstallQualified"] = False
            value["candidate"]["installer"]["format"] = "zip"
            evidence.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported clean-host evidence track"):
                load_script().build_review(index, [evidence])

    def test_cli_writes_deterministic_report_and_refuses_input_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index, evidence = self.complete_inputs(root)
            output = root / "clean-host-review.json"
            command = [sys.executable, str(SCRIPT), "--index", str(index)]
            for path in evidence:
                command.extend(["--evidence", str(path)])
            result = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), json.loads(output.read_text(encoding="utf-8")))

            refused = subprocess.run(
                command + ["--output", str(index)], capture_output=True, text=True
            )
            self.assertEqual(refused.returncode, 2)
            self.assertIn("must not overwrite", refused.stderr)

    def test_channel_matrix_requires_both_windows_installers_per_channel(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = self.write_index(root, channelled=True)
            evidence = [self.write_evidence(root, platform, fmt, channel=("online" if platform == "Windows" else "standard"))
                        for platform, fmt in TRACKS]
            script = load_script()
            partial = script.build_review(index, evidence)
            self.assertFalse(partial["readiness"]["readyForOwnerReview"])
            self.assertEqual(partial["summary"]["requiredTrackCount"], 7)
            self.assertIn("Windows/exe/offline", partial["readiness"]["blockers"][0])
            self.assertIn("Windows/msi/offline", partial["readiness"]["blockers"][0])
            evidence += [self.write_evidence(root, "Windows", fmt, suffix="-offline", channel="offline")
                         for fmt in ("exe", "msi")]
            report = script.build_review(index, evidence)
            self.assertTrue(report["readiness"]["readyForOwnerReview"])
            self.assertFalse(report["readiness"]["cleanHostInstallQualified"])
            self.assertEqual(report["summary"]["reviewReadyTrackCount"], 7)
            self.assertEqual({item["distributionChannel"] for item in report["evidence"]},
                             {"standard", "online", "offline"})
            value = json.loads(evidence[-1].read_text())
            value["candidate"]["distributionChannel"] = "online"
            evidence[-1].write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "distribution channel does not match"):
                script.build_review(index, evidence)

    def test_channel_index_rejects_missing_duplicate_and_ambiguous_bindings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = self.write_index(root, channelled=True)
            evidence = self.write_evidence(root, "Windows", "exe", channel="online")
            original = json.loads(index.read_text())
            script = load_script()
            for mutation in ("missing", "duplicate", "mixed", "ambiguous"):
                value = json.loads(json.dumps(original))
                if mutation == "missing":
                    value["platforms"].pop()
                elif mutation == "duplicate":
                    value["platforms"].append(value["platforms"][-1])
                elif mutation == "mixed":
                    del value["platforms"][0]["distributionChannel"]
                else:
                    value["platforms"][-1]["artifactManifest"] = value["platforms"][-2]["artifactManifest"]
                index.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    script.build_review(index, [evidence])

    def test_desktop_workflow_packages_reviewer_and_tracks_tests(self):
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
        self.assertIn('"scripts/desktop-clean-host-review.py"', workflow)
        self.assertIn('"tests/test_desktop_clean_host_review.py"', workflow)
        self.assertIn("Include cross-platform clean-host evidence reviewer", workflow)
        self.assertIn("bundle/review-clean-host.py", workflow)


if __name__ == "__main__":
    unittest.main()
