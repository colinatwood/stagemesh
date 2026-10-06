import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Tests are runnable both from repository root discovery and directly.
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from technology import evaluate_technology_extension, evaluate_technology_registry, normalize_technology_extension, negotiate_technology_capabilities
from state import ShowState
from runtime import StageMeshRuntime


def implementation(impl_id, group, *, conformance=True, peers=()):
    return {
        "id": impl_id,
        "organization": group,
        "independentGroup": group,
        "conformancePass": conformance,
        "interopPeers": list(peers),
    }


def standard_extension(extension_id="upp.community.motion-performance.v1", groups=2):
    impls = []
    for index in range(groups):
        peer = f"impl-{(index + 1) % groups}" if groups > 1 else ""
        impls.append(implementation(f"impl-{index}", f"group-{index}", peers=[peer] if peer else []))
    return {
        "id": extension_id,
        "maturity": "standard",
        "publicSpec": True,
        "conformanceTests": True,
        "interoperabilityEvidence": True,
        "fallbackDefined": True,
        "backwardCompatible": True,
        "unknownPreservationTested": True,
        "implementations": impls,
    }


class TechnologyLogicTests(unittest.TestCase):
    def test_experimental_extension_requires_no_permission(self):
        assessment = evaluate_technology_extension({"id": "artist.strange-controller.v1", "maturity": "experimental"}, ecosystem_participants=10000)
        self.assertTrue(assessment["declaredMaturityValid"])
        self.assertEqual(assessment["highestEligibleMaturity"], "experimental")
        self.assertEqual(assessment["scaleTier"], "infrastructure")

    def test_standard_requires_independent_interoperable_evidence(self):
        ext = standard_extension(groups=2)
        assessment = evaluate_technology_extension(ext, ecosystem_participants=5)
        self.assertTrue(assessment["declaredMaturityValid"])
        self.assertEqual(assessment["highestEligibleMaturity"], "standard")
        self.assertGreaterEqual(assessment["interopPairCount"], 1)

        ext["implementations"][1]["independentGroup"] = ext["implementations"][0]["independentGroup"]
        assessment = evaluate_technology_extension(ext, ecosystem_participants=5)
        self.assertFalse(assessment["declaredMaturityValid"])

    def test_scale_increases_standardization_bar_not_experiment_bar(self):
        ext = standard_extension(groups=2)
        small = evaluate_technology_extension(ext, ecosystem_participants=5)
        ext["adoptionRecordRef"] = "upp-public-record:standard-42"
        large = evaluate_technology_extension(ext, ecosystem_participants=75)
        experimental = evaluate_technology_extension({"id": "lab.future-surface.v9", "maturity": "experimental"}, ecosystem_participants=75)
        self.assertTrue(small["declaredMaturityValid"])
        self.assertTrue(large["declaredMaturityValid"])  # Existing standard remains recognized.
        self.assertFalse(large["currentScaleStandardReady"])
        self.assertTrue(large["scaleRevalidationNeeded"])
        self.assertEqual(large["standardIndependentGroupsRequired"], 4)
        self.assertTrue(experimental["declaredMaturityValid"])

    def test_large_scale_standard_needs_current_evidence_or_adoption_record(self):
        ext = standard_extension(groups=2)
        without_record = evaluate_technology_extension(ext, ecosystem_participants=100)
        self.assertFalse(without_record["declaredMaturityValid"])
        self.assertFalse(without_record["grandfatheredStandard"])
        ext["adoptionRecordRef"] = "upp-public-record:standard-17"
        with_record = evaluate_technology_extension(ext, ecosystem_participants=100)
        self.assertTrue(with_record["declaredMaturityValid"])
        self.assertTrue(with_record["grandfatheredStandard"])
        self.assertTrue(with_record["scaleRevalidationNeeded"])

    def test_vendor_cloud_or_ai_lock_blocks_standard(self):
        for dependency in (
            {"mandatoryVendor": "ExampleCorp"},
            {"cloudRequired": True},
            {"aiRequired": True},
        ):
            ext = standard_extension(groups=2)
            ext["dependencies"] = dependency
            assessment = evaluate_technology_extension(ext, ecosystem_participants=5)
            self.assertFalse(assessment["declaredMaturityValid"])

    def test_unknown_fields_are_preserved(self):
        ext = normalize_technology_extension({
            "id": "artist.quantum-banjo.v7",
            "maturity": "experimental",
            "futureQuantumField": {"banjos": 4, "phase": "mostly"},
        })
        self.assertEqual(ext["futureQuantumField"]["banjos"], 4)

    def test_core_promotion_has_higher_independence_threshold(self):
        ext = standard_extension(groups=3)
        ext["requestedCore"] = True
        emerging = evaluate_technology_extension(ext, ecosystem_participants=5)
        self.assertTrue(emerging["coreEligible"])
        large = evaluate_technology_extension(ext, ecosystem_participants=100)
        self.assertFalse(large["coreEligible"])
        self.assertEqual(large["coreIndependentGroupsRequired"], 5)

    def test_capability_negotiation_preserves_unknown_without_coercion(self):
        result = negotiate_technology_capabilities(
            ["upp.audio.output/1", "artist.quantum-banjo/7"],
            ["upp.audio.output/1", "vendor.hologram-stage/3"],
        )
        self.assertEqual(result["common"], ["upp.audio.output/1"])
        self.assertIn("artist.quantum-banjo/7", result["localOnly"])
        self.assertIn("vendor.hologram-stage/3", result["remoteOnly"])
        self.assertTrue(result["executeCommonOnly"])
        self.assertFalse(result["implicitCoercion"])
        self.assertEqual(len(result["preservedUnknown"]), 3)

    def test_deprecated_standard_requires_migration_safe_replacement(self):
        ext = standard_extension(groups=2)
        ext.update({"deprecated": True, "replacementId": "upp.community.motion-performance.v2", "migrationBridge": False})
        assessment = evaluate_technology_extension(ext, ecosystem_participants=5)
        self.assertFalse(assessment["deprecationSafe"])
        ext["migrationBridge"] = True
        assessment = evaluate_technology_extension(ext, ecosystem_participants=5)
        self.assertTrue(assessment["deprecationSafe"])

    def test_core_budget_flags_core_bloat_without_blocking_experimentation(self):
        extensions = []
        for i in range(3):
            ext = standard_extension(f"upp.core.extra-{i}.v1", groups=3)
            ext.update({"mandatoryCore": True, "requestedCore": True})
            extensions.append(ext)
        assessment = evaluate_technology_registry(extensions, policy={"maxMandatoryCoreExtensions": 2}, ecosystem_participants=5)
        self.assertTrue(assessment["coreBudgetExceeded"])
        self.assertIn("mandatory core extension budget is exceeded; new capabilities should remain profiles/extensions", assessment["policyFailures"])

    def test_registry_reports_openness_policy_failures(self):
        assessment = evaluate_technology_registry([], policy={
            "preserveUnknownCapabilities": False,
            "allowUnregisteredExperimentalNamespaces": False,
            "allowNoAiParticipant": False,
        }, ecosystem_participants=500)
        self.assertEqual(assessment["openness"], "at-risk")
        self.assertEqual(len(assessment["policyFailures"]), 3)


class TechnologyStateTests(unittest.TestCase):
    def test_registry_is_revisioned_persistent_and_preserves_future_fields(self):
        state = ShowState()
        before = state.snapshot()
        revision = before["resourceRevisions"]["technology"]
        changed = state.patch_technology({
            "ecosystemParticipants": 75,
            "policy": {"futureConsensusModel": {"kind": "rough-running-code-v9"}},
            "extensions": [{
                "id": "artist.future-stage.v1",
                "maturity": "experimental",
                "futureRendererContract": {"version": 22},
            }],
        }, expected_resource_revision=revision)
        self.assertEqual(changed["technology"]["ecosystemParticipants"], 75)
        self.assertEqual(changed["technology"]["extensions"][0]["futureRendererContract"]["version"], 22)
        self.assertEqual(changed["technology"]["policy"]["futureConsensusModel"]["kind"], "rough-running-code-v9")
        self.assertGreater(changed["resourceRevisions"]["technology"], revision)
        restored_state = ShowState(state.persistence_snapshot())
        restored = restored_state.technology_snapshot()
        self.assertEqual(restored["extensions"][0]["futureRendererContract"]["version"], 22)
        self.assertEqual(restored["policy"]["futureConsensusModel"]["kind"], "rough-running-code-v9")

    def test_standard_cannot_be_silently_deleted(self):
        state = ShowState()
        state.patch_technology({"extensions": [standard_extension(groups=2)]})
        extension_id = state.technology_snapshot()["extensions"][0]["id"]
        with self.assertRaises(ValueError):
            state.patch_technology({"removeExtensionIds": [extension_id]})
        state.patch_technology({"extensions": [{"id": extension_id, "deprecated": True, "replacementId": "upp.community.motion-performance.v2", "migrationBridge": True}]})
        self.assertTrue(state.technology_snapshot()["extensions"][0]["deprecated"])

    def test_live_show_snapshot_keeps_technology_registry_bounded(self):
        state = ShowState()
        state.patch_technology({"extensions": [{"id": "artist.future.v1", "maturity": "experimental", "largeFuturePayload": "x" * 1000}]})
        live = state.snapshot()
        self.assertEqual(live["technology"]["extensionCount"], 1)
        self.assertNotIn("extensions", live["technology"])
        self.assertEqual(len(state.technology_snapshot()["extensions"]), 1)
        self.assertEqual(len(state.persistence_snapshot()["technology"]["extensions"]), 1)

    def test_replication_snapshot_excludes_catalog_and_replica_preserves_local_catalog(self):
        primary = ShowState()
        primary.patch_technology({"extensions": [{"id": "vendor.primary-tech.v1", "maturity": "experimental"}]})
        replica = primary.replication_snapshot()
        self.assertNotIn("technology", replica)
        self.assertNotIn("technology", replica["resourceRevisions"])

        standby = ShowState()
        standby.patch_technology({"extensions": [{"id": "venue.local-tech.v1", "maturity": "experimental"}]})
        standby.apply_replica_snapshot(replica)
        ids = [item["id"] for item in standby.technology_snapshot()["extensions"]]
        self.assertEqual(ids, ["venue.local-tech.v1"])

    def test_technology_revision_does_not_invalidate_monitor(self):
        state = ShowState()
        first = state.snapshot()
        monitor_revision = first["resourceRevisions"]["monitor:alex"]
        state.patch_technology({"ecosystemParticipants": 20}, expected_resource_revision=first["resourceRevisions"]["technology"])
        changed = state.patch_monitor("alex", {"self": 81}, expected_resource_revision=monitor_revision)
        self.assertEqual(changed["players"][0]["monitor"]["self"], 81)


class TechnologyRuntimeTests(unittest.TestCase):
    def test_runtime_assessment_uses_verified_persisted_scale_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off"}, clear=False):
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime.state.patch_technology({"ecosystemParticipants": 5, "extensions": [standard_extension(groups=2)]})
                receipt = runtime.technology_publish_conformance({"extensionId": "upp.community.motion-performance.v1"})
                runtime.state.patch_technology({
                    "ecosystemParticipants": 80,
                    "extensions": [{"id": "upp.community.motion-performance.v1", "adoptionRecordRef": receipt["adoptionRecordRef"]}],
                })
                assessment = runtime.technology_assessment()
                item = assessment["extensions"][0]
                self.assertEqual(assessment["scaleTier"], "large")
                self.assertTrue(item["conformanceReceiptVerified"])
                self.assertNotIn("upp.community.motion-performance.v1", assessment["invalidDeclaredMaturityIds"])
                self.assertIn("upp.community.motion-performance.v1", assessment["scaleRevalidationIds"])
            finally:
                runtime.close()

    def test_runtime_rejects_fake_or_stale_standard_receipt(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off"}, clear=False):
            runtime = StageMeshRuntime(Path(tmp))
            try:
                ext = standard_extension(groups=2)
                runtime.state.patch_technology({"ecosystemParticipants": 5, "extensions": [ext]})
                assessment = runtime.technology_assessment(); item = assessment["extensions"][0]
                self.assertFalse(item["declaredMaturityValid"]); self.assertEqual(item["conformanceReceiptReason"], "signed-conformance-receipt-required")
                receipt = runtime.technology_publish_conformance({"extensionId": ext["id"]})
                runtime.state.patch_technology({"extensions": [{"id": ext["id"], "adoptionRecordRef": receipt["adoptionRecordRef"]}]})
                self.assertTrue(runtime.technology_assessment()["extensions"][0]["conformanceReceiptVerified"])
                runtime.state.patch_technology({"extensions": [{"id": ext["id"], "productionDeployments": 7}]})
                stale = runtime.technology_assessment()["extensions"][0]
                self.assertFalse(stale["declaredMaturityValid"]); self.assertEqual(stale["conformanceReceiptReason"], "signed-conformance-receipt-stale")
                runtime.state.patch_technology({"extensions": [{"id": ext["id"], "adoptionRecordRef": "upp-public-record:fake:" + "0" * 64}]})
                fake = runtime.technology_assessment()["extensions"][0]
                self.assertFalse(fake["declaredMaturityValid"]); self.assertEqual(fake["conformanceReceiptReason"], "signed-conformance-receipt-unavailable")
            finally:
                runtime.close()

    def test_core_receipt_must_match_current_scale_threshold(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off"}, clear=False):
            runtime = StageMeshRuntime(Path(tmp))
            try:
                ext = standard_extension(groups=3); ext["requestedCore"] = True
                runtime.state.patch_technology({"ecosystemParticipants": 5, "extensions": [ext]})
                receipt = runtime.technology_publish_conformance({"extensionId": ext["id"]})
                runtime.state.patch_technology({"extensions": [{"id": ext["id"], "adoptionRecordRef": receipt["adoptionRecordRef"]}]})
                emerging = runtime.technology_assessment()["extensions"][0]
                self.assertTrue(emerging["coreEligible"])
                runtime.state.patch_technology({"ecosystemParticipants": 75})
                large = runtime.technology_assessment()["extensions"][0]
                self.assertFalse(large["coreEligible"]); self.assertIn("current-scale-signed-core-conformance-receipt-required", large["coreBlockers"])
                with self.assertRaises(ValueError):
                    runtime.technology_publish_conformance({"extensionId": ext["id"]})
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
