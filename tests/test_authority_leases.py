import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from authority_leases import AuthorityLeaseRegistry
from runtime import StageForgeRuntime


class GeneralAuthorityLeaseRegistryTests(unittest.TestCase):
    def test_typed_scopes_do_not_conflict_and_resource_wins_resolution(self):
        registry = AuthorityLeaseRegistry()
        department = registry.grant({
            "scopeKind": "department", "scope": "audio", "context": "runtime",
            "grantee": "audio-dept", "ttlSeconds": 60,
        })
        resource = registry.grant({
            "scopeKind": "resource", "scope": "audio", "context": "runtime",
            "grantee": "foh-resource", "ttlSeconds": 60,
        })
        self.assertTrue(department["active"])
        self.assertTrue(resource["active"])
        self.assertEqual(len(registry.snapshot()["active"]), 2)
        self.assertEqual(registry.resolve("audio", "audio"), "foh-resource")
        self.assertEqual(registry.resolve("other", "audio"), "audio-dept")

    def test_same_typed_scope_replaces_predecessor(self):
        registry = AuthorityLeaseRegistry()
        first = registry.grant({"scopeKind": "resource", "scope": "lighting-network", "context": "runtime", "grantee": "a"})
        second = registry.grant({"scopeKind": "resource", "scope": "lighting-network", "context": "runtime", "grantee": "b"})
        self.assertNotEqual(first["leaseId"], second["leaseId"])
        active = registry.snapshot()["activeByKind"]["resource"]
        self.assertEqual([item["grantee"] for item in active], ["b"])

    def test_clear_context_preserves_unrelated_runtime_resource(self):
        registry = AuthorityLeaseRegistry()
        registry.grant({"scopeKind": "patch", "scope": "audio.foh", "context": "venue", "grantee": "foh"})
        registry.grant({"scopeKind": "resource", "scope": "lighting-network", "context": "runtime", "grantee": "lighting"})
        self.assertEqual(registry.clear_context("venue"), 1)
        self.assertEqual(registry.resolve("lighting-network", "lighting"), "lighting")
        self.assertNotIn("audio.foh", registry.authority_map())

    def test_expiry_fails_closed_without_revoke(self):
        with patch("authority_leases.monotonic", side_effect=[100.0, 100.0, 102.0, 102.0]):
            registry = AuthorityLeaseRegistry()
            lease = registry.grant({
                "scopeKind": "resource", "scope": "lighting-network", "context": "runtime",
                "grantee": "lighting", "ttlSeconds": 1,
            })
            self.assertTrue(lease["active"])
            self.assertIsNone(registry.resolve("lighting-network", "lighting"))


class GeneralAuthorityRuntimeTests(unittest.TestCase):
    def _runtime(self, root: str) -> StageForgeRuntime:
        return StageForgeRuntime(Path(root))

    def test_resource_and_department_scopes_work_without_active_venue_patch(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off"}, clear=False):
            runtime = self._runtime(tmp)
            try:
                dept = runtime.venue_authority_grant({
                    "scopeKind": "department", "scope": "lighting", "grantee": "lx", "ttlSeconds": 60,
                })
                self.assertEqual(dept["context"], "runtime")
                self.assertEqual(runtime.resource_authority("lighting-network"), "lx")
                resource = runtime.venue_authority_grant({
                    "scopeKind": "resource", "scope": "lighting-network", "grantee": "show-control", "ttlSeconds": 60,
                })
                self.assertEqual(resource["scopeKind"], "resource")
                self.assertEqual(runtime.resource_authority("lighting-network"), "show-control")
                authority_events = [event for event in runtime.state.events_since(0) if event.get("category") == "authority"]
                self.assertTrue(authority_events)
                self.assertTrue(any(event.get("payload", {}).get("scopeKind") == "resource" for event in authority_events))
                with self.assertRaises(ValueError):
                    runtime.venue_authority_grant({"scopeKind": "resource", "scope": "not-real", "grantee": "nobody"})
            finally:
                runtime.close()

    def test_venue_commit_clears_legacy_venue_scope_but_preserves_runtime_resource(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off"}, clear=False):
            runtime = self._runtime(tmp)
            try:
                venue = {
                    "documentType": "org.upp.venue-profile", "schemaVersion": 1,
                    "id": "lease-venue", "name": "Lease Venue", "capabilities": ["audio.transport", "authority.fence"],
                    "devices": [{"id": "audio-a", "status": "expected", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"], "latency": {"fixedMs": 5, "jitterMs": 1, "timestamped": True}}],
                    "patch": {
                        "audio.foh": {"target": "audio-a:out-1-2", "authority": "foh"},
                        "audio.live-input": {"target": "audio-a:in-1-4"},
                        "audio.monitor": {"target": "audio-a:out-3-6"},
                    },
                }
                runtime.save_venue_profile(venue)
                tx = runtime.venue_adaptation_propose({})
                runtime.venue_adaptation_validate(tx["transactionId"])
                runtime.venue_adaptation_commit(tx["transactionId"], {"mode": "immediate"})
                legacy = runtime.venue_authority_grant({"scope": "audio.foh", "grantee": "production", "ttlSeconds": 60})
                runtime_lease = runtime.venue_authority_grant({
                    "scopeKind": "resource", "scope": "lighting-network", "grantee": "lighting", "ttlSeconds": 60,
                })
                self.assertEqual(legacy["context"], "venue")
                self.assertEqual(runtime_lease["context"], "runtime")
                # Recommitting a fresh adaptation invalidates venue-local leases only.
                tx2 = runtime.venue_adaptation_propose({})
                runtime.venue_adaptation_validate(tx2["transactionId"])
                runtime.venue_adaptation_commit(tx2["transactionId"], {"mode": "immediate"})
                active_ids = {item["leaseId"] for item in runtime.venue_authority_status()["active"]}
                self.assertNotIn(legacy["leaseId"], active_ids)
                self.assertIn(runtime_lease["leaseId"], active_ids)
            finally:
                runtime.close()

    def test_demotion_clears_all_operational_authority_leases(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off"}, clear=False):
            runtime = self._runtime(tmp)
            try:
                lease = runtime.venue_authority_grant({
                    "scopeKind": "resource", "scope": "lighting-network", "grantee": "lighting", "ttlSeconds": 60,
                })
                self.assertTrue(lease["active"])
                runtime.set_node_role({"role": "standby", "acknowledgeAuthorityChange": True})
                self.assertEqual(runtime.venue_authority_status()["active"], [])
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
