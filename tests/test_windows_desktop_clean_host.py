import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "windows-desktop-clean-host.py"


def load_script():
    spec = importlib.util.spec_from_file_location("windows_desktop_clean_host", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsDesktopCleanHostTests(unittest.TestCase):
    commit = "a" * 40

    def make_bundle(self, root: Path) -> tuple[Path, Path]:
        bundle = root / "bundle"
        installer = bundle / "nsis" / "StageMesh_0.1.0_x64-setup.exe"
        installer.parent.mkdir(parents=True)
        installer.write_bytes(b"exact windows installer")
        manifest = {
            "schemaVersion": 1,
            "product": "StageMesh",
            "version": "0.1.0",
            "platform": "Windows",
            "distributionChannel": "offline",
            "sourceCommit": self.commit,
            "signed": False,
            "qualification": {
                "softwarePackageBuilt": True,
                "cleanHostInstallQualified": False,
                "physicalHardwareQualified": False,
            },
            "files": [{
                "path": "nsis/StageMesh_0.1.0_x64-setup.exe",
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
        *,
        installed: bool = False,
        running: int = 0,
        webview: bool = True,
        runner: str = "1",
    ) -> dict:
        return {
            "runnerIdHash": "sha256:" + runner * 64,
            "os": {
                "productName": "Windows 11 Pro",
                "displayVersion": "24H2",
                "buildNumber": 26100,
                "architecture": "AMD64",
            },
            "stageMesh": {
                "uninstallEntries": [{
                    "displayName": "StageMesh",
                    "displayVersion": "0.1.0",
                    "publisher": "StageMesh",
                }] if installed else [],
                "installedExecutables": [{
                    "pathHash": "sha256:" + "2" * 64,
                    "bytes": 123,
                    "sha256": "3" * 64,
                }] if installed else [],
                "runningProcessCount": running,
            },
            "webView2": {
                "detected": webview,
                "versions": ["140.0.3485.54"] if webview else [],
            },
            "appData": {
                "pathHash": "sha256:" + "4" * 64,
                "exists": installed,
            },
        }

    def start(self, root: Path):
        module = load_script()
        bundle, installer = self.make_bundle(root)
        report = module.start_evidence(
            bundle,
            installer,
            self.snapshot(),
            clean_host_attested=True,
            observed_at_utc="2026-10-06T00:00:00Z",
        )
        return module, bundle, installer, report

    def test_complete_phase_sequence_is_review_ready_but_not_qualified(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _, _, report = self.start(Path(temporary))
            marker = "clean-host-template-canary"
            report = module.append_phase(
                report,
                "installed",
                self.snapshot(installed=True, running=1),
                observed_at_utc="2026-10-06T00:05:00Z",
                runtime_ready_observed=True,
                persistence_marker=marker,
            )
            report = module.append_phase(
                report,
                "restarted",
                self.snapshot(installed=True, running=1),
                observed_at_utc="2026-10-06T00:10:00Z",
                runtime_ready_observed=True,
                persistence_marker=marker,
                save_restart_recovered=True,
            )
            report = module.append_phase(
                report,
                "upgraded",
                self.snapshot(installed=True, running=1),
                observed_at_utc="2026-10-06T00:15:00Z",
                runtime_ready_observed=True,
                persistence_marker=marker,
                save_restart_recovered=True,
                previous_version="0.0.9",
                upgrade_observed=True,
            )
            report = module.append_phase(
                report,
                "uninstalled",
                self.snapshot(),
                observed_at_utc="2026-10-06T00:20:00Z",
                uninstall_observed=True,
            )

            self.assertTrue(report["summary"]["allRequiredPhasesPassed"])
            self.assertTrue(report["readiness"]["readyForQualificationReview"])
            self.assertFalse(report["readiness"]["cleanHostInstallQualified"])
            self.assertFalse(report["readiness"]["physicalHardwareQualified"])
            self.assertEqual(report["candidate"]["sourceCommit"], self.commit)
            self.assertEqual(report["candidate"]["distributionChannel"], "offline")
            self.assertNotIn(marker, json.dumps(report))

    def test_distribution_channel_is_required_and_limited_to_windows_channels(self):
        with tempfile.TemporaryDirectory() as temporary:
            module = load_script()
            bundle, installer = self.make_bundle(Path(temporary))
            manifest_path = bundle / "desktop-artifacts.json"
            original = json.loads(manifest_path.read_text(encoding="utf-8"))
            for channel in (None, "standard", "nightly"):
                manifest = dict(original)
                if channel is None:
                    manifest.pop("distributionChannel", None)
                else:
                    manifest["distributionChannel"] = channel
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "distribution channel"):
                    module.start_evidence(
                        bundle,
                        installer,
                        self.snapshot(),
                        clean_host_attested=True,
                        observed_at_utc="2026-10-06T00:00:00Z",
                    )

    def test_installer_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            module = load_script()
            bundle, installer = self.make_bundle(Path(temporary))
            installer.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "does not match"):
                module.start_evidence(
                    bundle,
                    installer,
                    self.snapshot(),
                    clean_host_attested=True,
                    observed_at_utc="2026-10-06T00:00:00Z",
                )

    def test_dirty_or_unattested_baseline_cannot_start_install_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            module = load_script()
            bundle, installer = self.make_bundle(Path(temporary))
            report = module.start_evidence(
                bundle,
                installer,
                self.snapshot(installed=True),
                clean_host_attested=False,
                observed_at_utc="2026-10-06T00:00:00Z",
            )
            self.assertFalse(report["phases"][0]["passed"])
            with self.assertRaisesRegex(ValueError, "prerequisites"):
                module.append_phase(
                    report,
                    "installed",
                    self.snapshot(installed=True),
                    observed_at_utc="2026-10-06T00:05:00Z",
                    runtime_ready_observed=True,
                    persistence_marker="marker",
                )

    def test_runner_change_and_missing_restart_recovery_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _, _, report = self.start(Path(temporary))
            with self.assertRaisesRegex(ValueError, "baseline runner"):
                module.append_phase(
                    report,
                    "installed",
                    self.snapshot(installed=True, runner="5"),
                    observed_at_utc="2026-10-06T00:05:00Z",
                    runtime_ready_observed=True,
                    persistence_marker="marker",
                )
            report = module.append_phase(
                report,
                "installed",
                self.snapshot(installed=True),
                observed_at_utc="2026-10-06T00:05:00Z",
                runtime_ready_observed=True,
                persistence_marker="marker",
            )
            report = module.append_phase(
                report,
                "restarted",
                self.snapshot(installed=True),
                observed_at_utc="2026-10-06T00:10:00Z",
                runtime_ready_observed=True,
                persistence_marker="different marker",
                save_restart_recovered=False,
            )
            restarted = report["phases"][-1]
            self.assertFalse(restarted["passed"])
            self.assertFalse(restarted["checks"]["persistenceMarkerMatches"])
            self.assertFalse(report["readiness"]["readyForQualificationReview"])

    def test_upgrade_must_be_from_a_different_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _, _, report = self.start(Path(temporary))
            marker = "marker"
            report = module.append_phase(
                report,
                "installed",
                self.snapshot(installed=True),
                observed_at_utc="2026-10-06T00:05:00Z",
                runtime_ready_observed=True,
                persistence_marker=marker,
            )
            report = module.append_phase(
                report,
                "restarted",
                self.snapshot(installed=True),
                observed_at_utc="2026-10-06T00:10:00Z",
                runtime_ready_observed=True,
                persistence_marker=marker,
                save_restart_recovered=True,
            )
            report = module.append_phase(
                report,
                "upgraded",
                self.snapshot(installed=True),
                observed_at_utc="2026-10-06T00:15:00Z",
                runtime_ready_observed=True,
                persistence_marker=marker,
                save_restart_recovered=True,
                previous_version="0.1.0",
                upgrade_observed=True,
            )
            self.assertFalse(report["phases"][-1]["passed"])
            self.assertFalse(report["phases"][-1]["checks"]["previousVersionIsDifferent"])

    def test_uninstall_can_be_recorded_before_upgrade_but_remains_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            module, _, _, report = self.start(Path(temporary))
            marker = "marker"
            report = module.append_phase(
                report,
                "installed",
                self.snapshot(installed=True),
                observed_at_utc="2026-10-06T00:05:00Z",
                runtime_ready_observed=True,
                persistence_marker=marker,
            )
            report = module.append_phase(
                report,
                "restarted",
                self.snapshot(installed=True),
                observed_at_utc="2026-10-06T00:10:00Z",
                runtime_ready_observed=True,
                persistence_marker=marker,
                save_restart_recovered=True,
            )
            report = module.append_phase(
                report,
                "uninstalled",
                self.snapshot(),
                observed_at_utc="2026-10-06T00:20:00Z",
                uninstall_observed=True,
            )
            self.assertTrue(report["phases"][-1]["passed"])
            self.assertFalse(report["readiness"]["readyForQualificationReview"])
            with self.assertRaisesRegex(ValueError, "after uninstall"):
                module.append_phase(
                    report,
                    "upgraded",
                    self.snapshot(installed=True),
                    observed_at_utc="2026-10-06T00:25:00Z",
                )

    def test_desktop_workflow_packages_the_collector_only_for_windows(self):
        workflow = (ROOT / ".github" / "workflows" / "desktop.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('"scripts/windows-desktop-clean-host.py"', workflow)
        self.assertIn('"tests/test_windows_desktop_clean_host.py"', workflow)
        self.assertIn("Include Windows clean-host evidence collector", workflow)
        self.assertIn("if: runner.os == 'Windows'", workflow)
        self.assertIn("bundle/windows-clean-host.py", workflow)


if __name__ == "__main__":
    unittest.main()
