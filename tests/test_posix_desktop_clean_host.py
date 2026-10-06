import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "posix-desktop-clean-host.py"


def load_script():
    spec = importlib.util.spec_from_file_location("posix_desktop_clean_host", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PosixDesktopCleanHostTests(unittest.TestCase):
    commit = "a" * 40

    def make_bundle(self, root: Path, platform: str, installer_name: str) -> tuple[Path, Path]:
        bundle = root / "bundle"
        installer = bundle / installer_name
        installer.parent.mkdir(parents=True)
        installer.write_bytes(f"exact {platform} installer".encode())
        manifest = {
            "schemaVersion": 1,
            "product": "StageMesh",
            "version": "0.1.0",
            "platform": platform,
            "sourceCommit": self.commit,
            "signed": False,
            "qualification": {
                "softwarePackageBuilt": True,
                "cleanHostInstallQualified": False,
                "physicalHardwareQualified": False,
            },
            "files": [{
                "path": installer_name,
                "bytes": installer.stat().st_size,
                "sha256": hashlib.sha256(installer.read_bytes()).hexdigest(),
            }],
        }
        (bundle / "desktop-artifacts.json").write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        return bundle, installer

    def snapshot(
        self,
        platform: str,
        *,
        installed: bool = False,
        package: bool = False,
        running: int = 0,
        version: str | None = None,
        runner: str = "1",
    ) -> dict:
        os_info = {
            "family": platform,
            "productName": "macOS" if platform == "macOS" else "Ubuntu",
            "version": "14.7" if platform == "macOS" else "24.04",
            "architecture": "arm64" if platform == "macOS" else "x86_64",
        }
        return {
            "runnerIdHash": "sha256:" + runner * 64,
            "os": os_info,
            "stageMesh": {
                "packageEntries": [{"package": "stagemesh", "version": version or "0.1.0"}] if package else [],
                "installedExecutables": [{
                    "pathHash": "sha256:" + "2" * 64,
                    "identityBytes": 123,
                    "identitySha256": "3" * 64,
                }] if installed else [],
                "runningProcessCount": running,
                "observedVersion": version,
            },
            "webview": {"detected": True, "provider": "test"},
            "appData": {"pathHash": "sha256:" + "4" * 64, "exists": installed},
        }

    def start(self, root: Path, platform: str = "Linux", installer_name: str = "deb/StageMesh.deb"):
        module = load_script()
        bundle, installer = self.make_bundle(root, platform, installer_name)
        report = module.start_evidence(
            bundle,
            installer,
            self.snapshot(platform),
            clean_host_attested=True,
            observed_at_utc="2026-10-06T00:00:00Z",
        )
        return module, bundle, installer, report

    def complete(self, module, report, platform: str, *, package: bool) -> dict:
        marker = "clean-host-template-canary"
        for phase, kwargs in (
            ("installed", {"runtime_ready_observed": True, "persistence_marker": marker}),
            ("restarted", {
                "runtime_ready_observed": True,
                "persistence_marker": marker,
                "save_restart_recovered": True,
            }),
            ("upgraded", {
                "runtime_ready_observed": True,
                "persistence_marker": marker,
                "save_restart_recovered": True,
                "previous_version": "0.0.9",
                "upgrade_observed": True,
            }),
        ):
            report = module.append_phase(
                report,
                phase,
                self.snapshot(platform, installed=True, package=package, running=1, version="0.1.0"),
                observed_at_utc="2026-10-06T00:05:00Z",
                **kwargs,
            )
        return module.append_phase(
            report,
            "uninstalled",
            self.snapshot(platform),
            observed_at_utc="2026-10-06T00:20:00Z",
            uninstall_observed=True,
        )

    def test_complete_deb_sequence_is_review_ready_but_not_qualified(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _, _, report = self.start(Path(temporary))
            report = self.complete(module, report, "Linux", package=True)
            self.assertTrue(report["summary"]["allRequiredPhasesPassed"])
            self.assertTrue(report["readiness"]["readyForQualificationReview"])
            self.assertFalse(report["readiness"]["cleanHostInstallQualified"])
            self.assertFalse(report["readiness"]["physicalHardwareQualified"])
            self.assertEqual(report["candidate"]["sourceCommit"], self.commit)
            self.assertNotIn("clean-host-template-canary", json.dumps(report))

    def test_complete_macos_sequence_accepts_dmg_without_package_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _, _, report = self.start(Path(temporary), "macOS", "dmg/StageMesh.dmg")
            report = self.complete(module, report, "macOS", package=False)
            self.assertTrue(report["readiness"]["readyForQualificationReview"])
            self.assertTrue(
                report["phases"][1]["checks"]["installerRegistrationDetectedWhenRequired"]
            )

    def test_appimage_sequence_requires_observed_version_but_not_registration(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _, _, report = self.start(Path(temporary), "Linux", "appimage/StageMesh.AppImage")
            installed = module.append_phase(
                report,
                "installed",
                self.snapshot("Linux", installed=True),
                observed_at_utc="2026-10-06T00:05:00Z",
                runtime_ready_observed=True,
                persistence_marker="marker",
            )
            self.assertFalse(installed["phases"][-1]["passed"])
            self.assertFalse(installed["phases"][-1]["checks"]["installedVersionMatchesCandidate"])
            self.assertTrue(installed["phases"][-1]["checks"]["installerRegistrationDetectedWhenRequired"])

    def test_tampering_and_cross_platform_installer_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            module = load_script()
            bundle, installer = self.make_bundle(Path(temporary), "Linux", "deb/StageMesh.deb")
            installer.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "does not match"):
                module.start_evidence(
                    bundle, installer, self.snapshot("Linux"),
                    clean_host_attested=True, observed_at_utc="2026-10-06T00:00:00Z",
                )

        with tempfile.TemporaryDirectory() as temporary:
            module = load_script()
            bundle, installer = self.make_bundle(Path(temporary), "macOS", "deb/StageMesh.deb")
            with self.assertRaisesRegex(ValueError, "macOS installer"):
                module.start_evidence(
                    bundle, installer, self.snapshot("macOS"),
                    clean_host_attested=True, observed_at_utc="2026-10-06T00:00:00Z",
                )

    def test_unsupported_host_and_runner_change_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _, _, report = self.start(Path(temporary))
            unsupported = self.snapshot("Linux")
            unsupported["os"]["version"] = "20.04"
            with self.assertRaisesRegex(ValueError, "Ubuntu 22.04 or 24.04"):
                module.start_evidence(
                    *self.make_bundle(Path(temporary) / "second", "Linux", "StageMesh.deb"),
                    unsupported,
                    clean_host_attested=True,
                    observed_at_utc="2026-10-06T00:00:00Z",
                )
            with self.assertRaisesRegex(ValueError, "baseline runner"):
                module.append_phase(
                    report,
                    "installed",
                    self.snapshot("Linux", installed=True, package=True, version="0.1.0", runner="5"),
                    observed_at_utc="2026-10-06T00:05:00Z",
                    runtime_ready_observed=True,
                    persistence_marker="marker",
                )

    def test_failed_restart_blocks_later_upgrade(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _, _, report = self.start(Path(temporary))
            report = module.append_phase(
                report,
                "installed",
                self.snapshot("Linux", installed=True, package=True, version="0.1.0"),
                observed_at_utc="2026-10-06T00:05:00Z",
                runtime_ready_observed=True,
                persistence_marker="marker",
            )
            report = module.append_phase(
                report,
                "restarted",
                self.snapshot("Linux", installed=True, package=True, version="0.1.0"),
                observed_at_utc="2026-10-06T00:10:00Z",
                runtime_ready_observed=True,
                persistence_marker="different",
                save_restart_recovered=True,
            )
            self.assertFalse(report["phases"][-1]["passed"])
            with self.assertRaisesRegex(ValueError, "prerequisites"):
                module.append_phase(
                    report,
                    "upgraded",
                    self.snapshot("Linux", installed=True, package=True, version="0.1.0"),
                    observed_at_utc="2026-10-06T00:15:00Z",
                )

    def test_desktop_workflow_packages_collector_for_macos_and_linux(self):
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
        self.assertIn('"scripts/posix-desktop-clean-host.py"', workflow)
        self.assertIn('"tests/test_posix_desktop_clean_host.py"', workflow)
        self.assertIn("Include macOS/Linux clean-host evidence collector", workflow)
        self.assertIn("if: runner.os != 'Windows'", workflow)
        self.assertIn("bundle/posix-clean-host.py", workflow)


if __name__ == "__main__":
    unittest.main()
