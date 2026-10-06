import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from adaptation import AdaptationRevisionConflict, VenueAdaptationManager, build_transaction
from runtime import StageMeshRuntime


class VenueAdaptationTests(unittest.TestCase):
    def requirements(self):
        return [
            {"id": "transport", "preferred": "audio.transport", "required": True, "domain": "audio"},
            {"id": "output", "preferred": "audio.output.multi", "required": True, "domain": "audio", "patchKey": "audio.foh"},
        ]

    def plan(self):
        return {
            "compatible": True,
            "grade": "direct",
            "readiness": "ready",
            "venue": {"id": "club", "name": "Club"},
            "devicePlan": [
                {"id": "transport", "decision": {"status": "direct", "capability": "audio.transport", "preferred": "audio.transport", "required": True, "quality": "direct", "qualityScore": 100}, "provider": None, "timing": {"status": "not-specified"}, "patch": None, "patchStatus": "unmapped"},
                {"id": "output", "decision": {"status": "direct", "capability": "audio.output.multi", "preferred": "audio.output.multi", "required": True, "quality": "direct", "qualityScore": 100}, "provider": {"type": "device", "id": "audio-a", "name": "Audio A"}, "timing": {"status": "compatible"}, "patch": {"target": "audio-a:out-1-2"}, "patchStatus": "mapped"},
            ],
            "departments": [{"domain": "audio", "grade": "direct"}],
            "actions": [],
            "unmappedRequired": [],
            "blockers": [],
            "discoveryWarnings": [],
        }

    def test_transaction_preserves_show_intent_and_commits_patch_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = VenueAdaptationManager(Path(tmp) / "adaptations.json")
            tx = manager.propose(self.plan(), self.requirements())
            self.assertEqual(tx["status"], "proposed")
            self.assertEqual(tx["mappings"]["audio.foh"]["target"], "audio-a:out-1-2")
            validated = manager.validate(tx["transactionId"], self.plan(), self.requirements())
            self.assertTrue(validated["validation"]["valid"])
            committed = manager.schedule_commit(tx["transactionId"], mode="immediate", show_seconds=12.5, bpm=120)
            self.assertEqual(committed["status"], "committed")
            active = manager.snapshot()["active"]
            self.assertEqual(active["venueId"], "club")
            self.assertEqual(active["mappings"]["audio.foh"]["target"], "audio-a:out-1-2")
            self.assertTrue(committed["receipt"]["intentPreserved"])

    def test_next_bar_waits_until_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = VenueAdaptationManager(Path(tmp) / "adaptations.json")
            tx = manager.propose(self.plan(), self.requirements())
            manager.validate(tx["transactionId"], self.plan(), self.requirements())
            pending = manager.schedule_commit(tx["transactionId"], mode="next-bar", show_seconds=1.1, bpm=120)
            self.assertEqual(pending["status"], "pending-commit")
            self.assertAlmostEqual(pending["commit"]["targetShowSeconds"], 2.0)
            self.assertEqual(manager.tick(1.999), [])
            committed = manager.tick(2.001)
            self.assertEqual(len(committed), 1)
            self.assertEqual(committed[0]["commitBoundary"]["type"], "bar")

    def test_named_cue_commit_and_rollback_restore_previous_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = VenueAdaptationManager(Path(tmp) / "adaptations.json")
            first = manager.propose(self.plan(), self.requirements())
            manager.validate(first["transactionId"], self.plan(), self.requirements())
            manager.schedule_commit(first["transactionId"], mode="immediate", show_seconds=0, bpm=120)

            plan2 = self.plan()
            plan2["venue"] = {"id": "hall", "name": "Hall"}
            plan2["devicePlan"][1]["patch"] = {"target": "audio-b:out-1-2"}
            plan2["devicePlan"][1]["provider"] = {"type": "device", "id": "audio-b", "name": "Audio B"}
            second = manager.propose(plan2, self.requirements())
            manager.validate(second["transactionId"], plan2, self.requirements())
            pending = manager.schedule_commit(second["transactionId"], mode="cue", show_seconds=3.0, bpm=120, cue_id="scene-14")
            self.assertEqual(pending["status"], "pending-commit")
            self.assertEqual(manager.trigger_cue("scene-13", 4.0), [])
            committed = manager.trigger_cue("scene-14", 5.0)
            self.assertEqual(committed[0]["venueId"], "hall")
            rolled = manager.rollback(second["transactionId"], show_seconds=6.0)
            self.assertEqual(rolled["status"], "rolled-back")
            self.assertEqual(manager.snapshot()["active"]["venueId"], "club")

    def test_only_one_commit_can_be_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = VenueAdaptationManager(Path(tmp) / "adaptations.json")
            first = manager.propose(self.plan(), self.requirements())
            second = manager.propose(self.plan(), self.requirements())
            manager.validate(first["transactionId"], self.plan(), self.requirements())
            manager.validate(second["transactionId"], self.plan(), self.requirements())
            manager.schedule_commit(first["transactionId"], mode="next-bar", show_seconds=0.1, bpm=120)
            with self.assertRaises(ValueError):
                manager.schedule_commit(second["transactionId"], mode="cue", show_seconds=0.1, bpm=120, cue_id="scene")

    def test_committed_patch_can_supply_explicit_execution_device_without_rewriting_show(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off"}, clear=False):
            runtime = StageMeshRuntime(Path(tmp))
            try:
                venue = {
                    "documentType": "org.upp.venue-profile",
                    "schemaVersion": 1,
                    "id": "exec-venue",
                    "name": "Execution Venue",
                    "capabilities": ["audio.transport", "authority.fence"],
                    "devices": [{"id": "audio-logical", "status": "expected", "capabilities": ["audio.output.multi", "audio.monitor"],
                                 "latency": {"fixedMs": 5, "jitterMs": 1, "timestamped": True}}],
                    "patch": {
                        "audio.foh": {"target": "audio-logical:out-1-2", "execution": {"deviceId": "hw:VenueFOH,0"}},
                        "audio.monitor": {"target": "audio-logical:out-3-4"}
                    }
                }
                runtime.save_venue_profile(venue)
                tx = runtime.venue_adaptation_propose({})
                validated = runtime.venue_adaptation_validate(tx["transactionId"])
                self.assertTrue(validated["validation"]["valid"])
                runtime.venue_adaptation_commit(tx["transactionId"], {"mode": "immediate"})
                self.assertEqual(runtime._mapped_execution_device("audio.foh"), "hw:VenueFOH,0")
                self.assertEqual(runtime.state.snapshot()["audio"]["outputs"][0]["deviceId"], "null-audio")
            finally:
                runtime.close()

    def test_future_transaction_can_be_preserved_but_not_executed_when_reader_is_too_old(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = VenueAdaptationManager(Path(tmp) / "adaptations.json")
            tx = manager.propose(self.plan(), self.requirements())
            with manager._lock:
                manager._state["transactions"][tx["transactionId"]]["schemaVersion"] = 3
                manager._state["transactions"][tx["transactionId"]]["minimumReaderSchemaVersion"] = 2
                manager._state["transactions"][tx["transactionId"]]["futureField"] = {"preserve": True}
                manager._persist()
            reloaded = VenueAdaptationManager(Path(tmp) / "adaptations.json")
            preserved = reloaded.get(tx["transactionId"])
            self.assertTrue(preserved["futureField"]["preserve"])
            with self.assertRaises(ValueError):
                reloaded.validate(tx["transactionId"], self.plan(), self.requirements())

    def test_adaptation_revision_rejects_stale_control_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = VenueAdaptationManager(Path(tmp) / "adaptations.json")
            revision = manager.snapshot()["revision"]
            manager.propose(self.plan(), self.requirements(), expected_revision=revision)
            with self.assertRaises(AdaptationRevisionConflict):
                manager.propose(self.plan(), self.requirements(), expected_revision=revision)

    def test_plan_change_invalidates_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = VenueAdaptationManager(Path(tmp) / "adaptations.json")
            tx = manager.propose(self.plan(), self.requirements())
            changed = self.plan()
            changed["devicePlan"][1]["patch"] = {"target": "audio-new:out"}
            invalid = manager.validate(tx["transactionId"], changed, self.requirements())
            self.assertFalse(invalid["validation"]["valid"])
            self.assertIn("venue compatibility plan changed since proposal", invalid["validation"]["blockers"])


if __name__ == "__main__":
    unittest.main()
