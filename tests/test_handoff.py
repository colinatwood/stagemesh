import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from handoff import HandoffExecutionRegistry, HandoffFacts, evaluate_handoff
from replication import make_envelope
from runtime import StageMeshRuntime
from state import ShowState


class HandoffLogicTests(unittest.TestCase):
    def test_live_input_requires_declared_duplicate_when_policy_requires_it(self):
        facts = HandoffFacts(
            role="standby", replica_age_ms=100, source_node_id="a",
            source_program_cursor_ns=1_000_000_000, handoff_target_show_ns=1_000_000_000,
            local_show_ns=995_000_000, active_live_input_slots=(0,),
            source_outputs_active=True, transport_running=True,
        )
        blocked = evaluate_handoff(facts, policy=None, live_inputs=None, deterministic_sources=None)
        self.assertTrue(blocked["authorityReady"])
        self.assertFalse(blocked["programLogicReady"])
        self.assertEqual(blocked["missingLiveInputSlots"], [0])
        self.assertEqual(blocked["recommendedAction"], "authority-transfer-only")

        ready = evaluate_handoff(
            facts,
            policy=None,
            live_inputs=[{"slot": 0, "mode": "network", "ready": True, "sourceId": "aes67-vocal-a"}],
            deterministic_sources=None,
        )
        self.assertTrue(ready["programLogicReady"])
        self.assertEqual(ready["missingLiveInputSlots"], [])
        self.assertEqual(ready["recommendedAction"], "authority-transfer-ready-live-feeds")
        self.assertFalse(ready["readyForProgramTakeover"])  # Execution acknowledgement still required.

    def test_deterministic_sources_must_be_declared_and_local(self):
        facts = HandoffFacts(
            role="standby", replica_age_ms=50, source_node_id="a",
            source_program_cursor_ns=2_000_000_000, handoff_target_show_ns=2_000_000_000,
            local_show_ns=1_995_000_000, active_live_input_slots=(),
            source_outputs_active=True, transport_running=True,
        )
        undeclared = evaluate_handoff(facts, policy=None, live_inputs=None, deterministic_sources=[])
        self.assertFalse(undeclared["programLogicReady"])
        self.assertIn("deterministic program sources are not declared", undeclared["programBlockers"])

        declared = evaluate_handoff(
            facts, policy=None, live_inputs=None,
            deterministic_sources=[{
                "id": "tracks-main", "kind": "track", "required": True,
                "shadowCapable": True, "localAssetReady": True, "contentHash": "sha256:abc",
            }],
        )
        self.assertTrue(declared["shadowRenderReady"])
        self.assertTrue(declared["programLogicReady"])
        self.assertEqual(declared["recommendedAction"], "start-shadow-prebuffer")
        self.assertFalse(declared["prebufferReady"])

    def test_execution_ack_turns_logical_readiness_into_program_takeover_readiness(self):
        facts = HandoffFacts(
            role="standby", replica_age_ms=40, source_node_id="a",
            source_program_cursor_ns=2_000_000_000, handoff_target_show_ns=2_000_000_000,
            local_show_ns=1_998_000_000, active_live_input_slots=(),
            source_outputs_active=True, transport_running=True,
        )
        source = {
            "id": "tracks-main", "kind": "track", "required": True,
            "shadowCapable": True, "localAssetReady": True, "contentHash": "sha256:abc",
        }
        decision = evaluate_handoff(
            facts, policy={"requiredPrebufferMs": 250}, live_inputs=None, deterministic_sources=[source],
            execution={"shadowSources": [{
                "sourceId": "tracks-main", "bufferedUntilShowNs": 2_300_000_000,
                "contentHash": "sha256:abc", "healthy": True, "ageMs": 20,
                "executionVerified": True, "renderedFrames": 14400,
            }]},
        )
        self.assertTrue(decision["prebufferReady"])
        self.assertTrue(decision["readyForProgramTakeover"])
        self.assertEqual(decision["recommendedAction"], "program-takeover-ready")

        wrong_hash = evaluate_handoff(
            facts, policy={"requiredPrebufferMs": 250}, live_inputs=None, deterministic_sources=[source],
            execution={"shadowSources": [{
                "sourceId": "tracks-main", "bufferedUntilShowNs": 2_300_000_000,
                "contentHash": "sha256:wrong", "healthy": True, "ageMs": 20,
                "executionVerified": True, "renderedFrames": 14400,
            }]},
        )
        self.assertFalse(wrong_hash["prebufferReady"])
        self.assertFalse(wrong_hash["readyForProgramTakeover"])

    def test_lag_policy_blocks_program_but_can_allow_authority_transfer(self):
        facts = HandoffFacts(
            role="standby", replica_age_ms=50, source_node_id="a",
            source_program_cursor_ns=1_000_000_000, handoff_target_show_ns=1_000_000_000,
            local_show_ns=900_000_000, active_live_input_slots=(),
            source_outputs_active=False, transport_running=False,
        )
        decision = evaluate_handoff(facts, policy={"maxLocalLagMs": 20}, live_inputs=None, deterministic_sources=None)
        self.assertFalse(decision["programLogicReady"])
        self.assertTrue(decision["readyForAuthorityTransfer"])
        self.assertIn("standby show clock trails handoff target beyond policy", decision["programBlockers"])


class HandoffStateTests(unittest.TestCase):
    def test_handoff_configuration_is_revisioned_and_persistent(self):
        state = ShowState()
        before = state.snapshot()
        rr = before["resourceRevisions"]["handoff"]
        updated = state.patch_handoff({
            "policy": {"maxLocalLagMs": 12.5},
            "liveInputs": [{"slot": 0, "mode": "split", "ready": True, "sourceId": "split-a", "latencyMs": 1.2}],
            "deterministicSources": [{"id": "tracks", "kind": "track", "shadowCapable": True, "localAssetReady": True}],
        }, expected_resource_revision=rr)
        self.assertEqual(updated["handoff"]["policy"]["maxLocalLagMs"], 12.5)
        self.assertTrue(updated["handoff"]["liveInputs"][0]["ready"])
        self.assertEqual(updated["handoff"]["deterministicSources"][0]["id"], "tracks")
        self.assertGreater(updated["resourceRevisions"]["handoff"], rr)

        restored = ShowState(state.persistence_snapshot())
        snap = restored.snapshot()
        self.assertEqual(snap["handoff"]["policy"]["maxLocalLagMs"], 12.5)
        self.assertEqual(snap["handoff"]["liveInputs"][0]["sourceId"], "split-a")


class HandoffRuntimeTests(unittest.TestCase):
    def test_runtime_decision_uses_persisted_live_feed_declaration(self):
        env = {"STAGEMESH_NATIVE_ENGINE": "off"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime.state.patch_handoff({
                    "liveInputs": [{"slot": 0, "mode": "network", "ready": True, "sourceId": "net-vocal"}]
                })
                snapshot = runtime.state.persistence_snapshot()
                runtime.set_node_role({"role": "standby", "acknowledgeAuthorityChange": True})
                envelope = make_envelope(
                    snapshot, node_id="primary-a", epoch=4, sequence=1,
                    execution_telemetry={
                        "showTimeNs": 2_000_000_000, "transportRunning": True,
                        "audioOutputs": [{"slot": 0, "lastBlockEndShowNs": 1_995_000_000}],
                        "activeAudioInputSlots": [0],
                    },
                )
                runtime.apply_replica(envelope)
                decision = runtime.handoff_decision_status()
                self.assertTrue(decision["programLogicReady"])
                self.assertEqual(decision["missingLiveInputSlots"], [])
                self.assertEqual(decision["recommendedAction"], "authority-transfer-ready-live-feeds")
            finally:
                runtime.close()

    def test_runtime_live_feed_execution_ack_enables_program_takeover(self):
        env = {"STAGEMESH_NATIVE_ENGINE": "off"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime.state.patch_handoff({
                    "liveInputs": [{"slot": 0, "mode": "network", "ready": True, "sourceId": "net-vocal"}]
                })
                snapshot = runtime.state.persistence_snapshot()
                runtime.set_node_role({"role": "standby", "acknowledgeAuthorityChange": True})
                runtime.apply_replica(make_envelope(
                    snapshot, node_id="primary-a", epoch=5, sequence=1,
                    execution_telemetry={
                        "showTimeNs": 3_000_000_000, "transportRunning": True,
                        "audioOutputs": [{"slot": 0, "lastBlockEndShowNs": 2_995_000_000}],
                        "activeAudioInputSlots": [0],
                    },
                ))
                before = runtime.handoff_decision_status()
                self.assertFalse(before["readyForProgramTakeover"])
                after = runtime.report_live_feed_ready({
                    "slot": 0, "sourceId": "net-vocal", "healthy": True, "latencyMs": 3.0,
                    "firstShowNs": 2_990_000_000, "lastShowNs": 3_000_000_000,
                    "frames": 480, "sequence": 1,
                })
                self.assertTrue(after["readyForProgramTakeover"])
                self.assertEqual(after["recommendedAction"], "program-takeover-ready-live-feeds")
            finally:
                runtime.close()

    def test_live_feed_health_only_report_does_not_prove_execution(self):
        registry = HandoffExecutionRegistry()
        registry.report_live(0, source_id="net-vocal", healthy=True, latency_ms=2.0)
        snap = registry.snapshot()
        self.assertFalse(snap["liveInputs"][0]["executionVerified"])
        self.assertEqual(snap["liveInputs"][0]["evidenceType"], "feed-health-report")

    def test_shadow_block_gap_invalidates_verified_horizon(self):
        registry = HandoffExecutionRegistry()
        registry.report_shadow("tracks", start_show_ns=1_000, buffered_until_show_ns=2_000, rendered_frames=48, healthy=True)
        first = registry.snapshot()["shadowSources"][0]
        self.assertTrue(first["executionVerified"])
        registry.report_shadow("tracks", start_show_ns=3_000, buffered_until_show_ns=4_000, rendered_frames=48, healthy=True)
        second = registry.snapshot()["shadowSources"][0]
        self.assertFalse(second["executionVerified"])
        self.assertEqual(second["discontinuities"], 1)

    def test_execution_evidence_clears_when_replication_authority_changes(self):
        env = {"STAGEMESH_NATIVE_ENGINE": "off"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime.state.patch_handoff({
                    "liveInputs": [{"slot": 0, "mode": "network", "ready": True, "sourceId": "net-vocal"}]
                })
                snapshot = runtime.state.persistence_snapshot()
                runtime.set_node_role({"role": "standby", "acknowledgeAuthorityChange": True})
                runtime.apply_replica(make_envelope(snapshot, node_id="primary-a", epoch=5, sequence=1, execution_telemetry={
                    "showTimeNs": 1_000_000_000, "transportRunning": True,
                    "audioOutputs": [{"slot":0,"lastBlockEndShowNs":995_000_000}], "activeAudioInputSlots":[0],
                }))
                runtime.report_live_feed_ready({"slot":0,"sourceId":"net-vocal","healthy":True})
                self.assertTrue(runtime.handoff_execution_status()["liveInputs"])
                runtime.apply_replica(make_envelope(snapshot, node_id="primary-b", epoch=6, sequence=1, execution_telemetry={
                    "showTimeNs": 1_100_000_000, "transportRunning": True,
                    "audioOutputs": [{"slot":0,"lastBlockEndShowNs":1_095_000_000}], "activeAudioInputSlots":[0],
                }))
                self.assertEqual(runtime.handoff_execution_status()["liveInputs"], [])
                self.assertFalse(runtime.handoff_decision_status()["readyForProgramTakeover"])
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
