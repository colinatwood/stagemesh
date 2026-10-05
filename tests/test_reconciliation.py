import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reconciliation import RealizationEvidenceRegistry, evaluate_realization
from runtime import StageForgeRuntime


class VenueReconciliationTests(unittest.TestCase):
    def active(self):
        return {
            "transactionId": "adapt-a",
            "patchRevision": 2,
            "venueId": "club",
            "venueName": "Club",
            "mappings": {
                "audio.foh": {
                    "target": "audio-a:out-1-2",
                    "provider": {"type": "device", "id": "audio-a"},
                    "patch": {"target": "audio-a:out-1-2", "authority": "foh"},
                }
            },
        }

    def requirements(self):
        return [{"id": "output", "preferred": "audio.output.multi", "required": True, "domain": "audio", "patchKey": "audio.foh"}]

    def plan(self, provider="audio-a", target="audio-a:out-1-2", blocked=False):
        return {
            "compatible": not blocked,
            "grade": "direct" if not blocked else "blocked",
            "readiness": "ready" if not blocked else "blocked",
            "devicePlan": [{
                "id": "output",
                "decision": {"status": "blocked" if blocked else "direct", "capability": "audio.output.multi", "required": True},
                "provider": None if blocked else {"type": "device", "id": provider},
                "timing": {"status": "blocked" if blocked else "compatible"},
                "patch": {"target": target},
            }],
            "blockers": ["output unavailable"] if blocked else [],
        }

    def test_no_active_patch_is_not_an_error(self):
        report = evaluate_realization(None, {}, [], {"reports": []})
        self.assertEqual(report["status"], "no-active-patch")
        self.assertTrue(report["safeToContinue"])

    def test_compatible_mapping_without_runtime_evidence_is_unverified(self):
        report = evaluate_realization(self.active(), self.plan(), self.requirements(), {"reports": []}, authority={"audio.foh": "foh"})
        self.assertEqual(report["status"], "unverified")
        self.assertTrue(report["safeToContinue"])
        self.assertFalse(report["realized"])

    def test_fresh_matching_evidence_proves_realization(self):
        registry = RealizationEvidenceRegistry()
        registry.report({"patchKey": "audio.foh", "providerId": "audio-a", "target": "audio-a:out-1-2", "healthy": True, "authorityHolder": "foh"})
        report = evaluate_realization(self.active(), self.plan(), self.requirements(), registry.snapshot(), authority={"audio.foh": "foh"})
        self.assertEqual(report["status"], "realized")
        self.assertTrue(report["realized"])

    def test_provider_drift_is_detected_without_guessing_equivalence(self):
        registry = RealizationEvidenceRegistry()
        registry.report({"patchKey": "audio.foh", "providerId": "audio-b", "target": "audio-b:out", "healthy": True})
        report = evaluate_realization(self.active(), self.plan(provider="audio-b", target="audio-b:out"), self.requirements(), registry.snapshot())
        self.assertEqual(report["status"], "drift")
        self.assertEqual(report["suggestedAction"], "propose-repair")

    def test_authority_mismatch_blocks_reconciliation(self):
        registry = RealizationEvidenceRegistry()
        registry.report({"patchKey": "audio.foh", "providerId": "audio-a", "target": "audio-a:out-1-2", "healthy": True, "authorityHolder": "production"})
        report = evaluate_realization(self.active(), self.plan(), self.requirements(), registry.snapshot(), authority={"audio.foh": "foh"})
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["safeToContinue"])
        self.assertIn("authority holder", report["blockers"][0])

    def test_runtime_accepts_adapter_evidence_only_for_active_mapping(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off"}, clear=False):
            runtime = StageForgeRuntime(Path(tmp))
            try:
                venue = {
                    "documentType": "org.upp.venue-profile", "schemaVersion": 1,
                    "id": "club", "name": "Club", "capabilities": ["audio.transport", "authority.fence"],
                    "devices": [{"id": "audio-a", "status": "expected", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"], "latency": {"fixedMs": 5, "jitterMs": 1, "timestamped": True}}],
                    "patch": {
                        "audio.foh": {"target": "audio-a:out-1-2", "authority": "foh"},
                        "audio.live-input": {"target": "audio-a:in-1-4"},
                        "audio.monitor": {"target": "audio-a:out-3-8"}
                    },
                }
                runtime.save_venue_profile(venue)
                tx = runtime.venue_adaptation_propose({})
                runtime.venue_adaptation_validate(tx["transactionId"])
                runtime.venue_adaptation_commit(tx["transactionId"], {"mode": "immediate"})
                accepted = runtime.venue_reconciliation_report_execution({
                    "patchKey": "audio.foh", "providerId": "audio-a", "target": "audio-a:out-1-2", "healthy": True, "authorityHolder": "foh"
                })
                self.assertTrue(accepted["accepted"])
                self.assertIn(accepted["reconciliation"]["status"], {"unverified", "realized"})
                with self.assertRaises(ValueError):
                    runtime.venue_reconciliation_report_execution({"patchKey": "not.active", "healthy": True})
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()

class VenueAuthorityLeaseTests(unittest.TestCase):
    def test_lease_replaces_scope_and_expires_fail_closed(self):
        from authority_leases import VenueAuthorityLeaseRegistry
        registry = VenueAuthorityLeaseRegistry()
        first = registry.grant({"scope": "lighting", "grantee": "lighting-op", "ttlSeconds": 30})
        self.assertTrue(first["active"])
        second = registry.grant({"scope": "lighting", "grantee": "production", "ttlSeconds": 30})
        snapshot = registry.snapshot()
        active = snapshot["active"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["leaseId"], second["leaseId"])
        self.assertEqual(registry.authority_map()["lighting"], "production")
        revoked = registry.revoke(second["leaseId"], "stage-manager")
        self.assertFalse(revoked["active"])
        self.assertNotIn("lighting", registry.authority_map())

    def test_runtime_authority_lease_changes_reconciliation_expected_holder(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off"}, clear=False):
            runtime = StageForgeRuntime(Path(tmp))
            try:
                venue = {
                    "documentType": "org.upp.venue-profile", "schemaVersion": 1,
                    "id": "lease-venue", "name": "Lease Venue", "capabilities": ["audio.transport", "authority.fence"],
                    "devices": [{"id": "audio-a", "status": "expected", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"], "latency": {"fixedMs": 5, "jitterMs": 1, "timestamped": True}}],
                    "patch": {
                        "audio.foh": {"target": "audio-a:out-1-2", "authority": "foh"},
                        "audio.live-input": {"target": "audio-a:in-1-4"},
                        "audio.monitor": {"target": "audio-a:out-3-6"}
                    }
                }
                runtime.save_venue_profile(venue)
                tx = runtime.venue_adaptation_propose({})
                runtime.venue_adaptation_validate(tx["transactionId"])
                runtime.venue_adaptation_commit(tx["transactionId"], {"mode": "immediate"})
                lease = runtime.venue_authority_grant({"scope": "audio.foh", "grantee": "production", "ttlSeconds": 60, "grantedBy": "foh"})
                runtime.venue_reconciliation_report_execution({"patchKey": "audio.foh", "providerId": "audio-a", "target": "audio-a:out-1-2", "healthy": True, "authorityHolder": "production"})
                report = runtime.venue_reconciliation_report({})
                row = next(item for item in report["mappings"] if item["patchKey"] == "audio.foh")
                self.assertEqual(row["expectedAuthority"], "production")
                runtime.venue_authority_revoke(lease["leaseId"], {"requestedBy": "foh"})
                report = runtime.venue_reconciliation_report({})
                row = next(item for item in report["mappings"] if item["patchKey"] == "audio.foh")
                self.assertEqual(row["status"], "blocked")
            finally:
                runtime.close()
