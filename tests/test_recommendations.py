import unittest

from backend.recommendations import build_recommendations


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "revision": 7,
            "players": [
                {"id": "lead", "name": "Avery", "role": "Lead vocal", "monitor": {"self": 72, "vocals": 65, "click": 8}},
                {"id": "drums", "name": "Morgan", "role": "Drums", "monitor": {"self": 60, "vocals": 35, "click": 75}},
            ],
            "system": {"capacity": 82, "mode": "full"},
            "audio": {"deviceId": "interface", "inputs": []},
        }
        self.audio = {
            "desiredConnected": True,
            "devices": [
                {"id": "interface", "backend": "alsa", "input": True, "output": True},
            ],
        }
        self.midi = {"devices": [{"id": "pads", "connected": True}], "bindings": {}}
        self.adapters = {"decisions": [{"id": "ai-connector", "status": "full"}]}

    def build(self, request=None):
        return build_recommendations(self.state, self.audio, self.midi, self.adapters, request)

    def test_report_is_bounded_local_and_never_applies_or_arms(self):
        report = self.build({"playerId": "lead", "goal": "clarity", "notes": "Clear vocal, please"})
        self.assertEqual(report["engine"], "local-evidence-advisor-v1")
        self.assertEqual(report["modelConnection"], "not-configured")
        self.assertFalse(report["automaticApply"])
        self.assertFalse(report["physicalOutputsArmed"])
        self.assertLessEqual(len(report["recommendations"]), 4)
        self.assertTrue(all(not item["automaticApply"] and not item["physicalOutputsArmed"] for item in report["recommendations"]))
        self.assertNotIn("Clear vocal", repr(report))

    def test_missing_physical_output_is_a_critical_setup_gap(self):
        self.audio = {"desiredConnected": False, "devices": [{"id": "null", "backend": "null", "output": True}]}
        report = self.build()
        recommendation = next(item for item in report["recommendations"] if item["id"] == "verify-audio-output")
        self.assertEqual(recommendation["priority"], "critical")
        self.assertEqual(recommendation["actionTarget"], "#operations")

    def test_recording_goal_recommends_an_explicit_performer_input(self):
        report = self.build({"playerId": "lead", "goal": "recording"})
        recommendation = next(item for item in report["recommendations"] if item["id"] == "assign-performer-input")
        self.assertEqual(recommendation["priority"], "high")
        self.assertIn("Avery", recommendation["title"])

    def test_capacity_pressure_outranks_background_analysis(self):
        self.state["system"] = {"capacity": 41, "mode": "audio"}
        report = self.build({"playerId": "drums", "goal": "low-latency"})
        protection = next(item for item in report["recommendations"] if item["id"] == "protect-audio-core")
        self.assertEqual(protection["priority"], "critical")
        self.assertIn("Suspend AI analysis", protection["summary"])

    def test_unconfirmed_hotplug_stop_becomes_a_critical_safety_recommendation(self):
        self.audio["hotplug"] = {"changes": [{
            "kind": "disconnected", "deviceId": "interface",
            "failedOutputStopSlots": [0, 1], "failedInputStopSlots": [2],
        }]}
        report = self.build()
        recommendation = next(item for item in report["recommendations"] if item["id"] == "verify-stream-stop")
        self.assertEqual(recommendation["priority"], "critical")
        self.assertEqual(report["hardwareSummary"]["failedStreamStops"], 3)
        self.assertFalse(recommendation["automaticApply"])

    def test_unconfirmed_midi_detach_blocks_stale_controller_input(self):
        self.midi["hotplug"] = {"changes": [{
            "kind": "identity-changed", "deviceId": "pads", "detached": False,
        }]}
        report = self.build()
        recommendation = next(item for item in report["recommendations"] if item["id"] == "verify-controller-detach")
        self.assertEqual(recommendation["priority"], "critical")
        self.assertEqual(report["hardwareSummary"]["failedMidiDetaches"], 1)

    def test_desired_but_unattached_performer_controller_is_recoverable(self):
        self.midi = {
            "devices": [{"id": "pads", "connected": True, "attached": False, "playerId": "drums"}],
            "bindings": {"pads": "drums"},
        }
        report = self.build({"playerId": "drums", "goal": "balanced"})
        recommendation = next(item for item in report["recommendations"] if item["id"] == "restore-performer-controller")
        self.assertEqual(recommendation["priority"], "high")
        self.assertEqual(report["hardwareSummary"]["attachedMidiInputs"], 0)

    def test_native_controller_attachment_failure_is_not_treated_as_live(self):
        self.midi = {
            "devices": [{"id": "pads", "connected": True, "attached": False, "attachmentFailed": True, "playerId": "drums"}],
            "bindings": {"pads": "drums"},
        }
        report = self.build({"playerId": "drums", "goal": "balanced"})
        recommendation = next(item for item in report["recommendations"] if item["id"] == "retry-controller-attachment")
        self.assertEqual(recommendation["priority"], "high")
        self.assertEqual(report["hardwareSummary"]["failedMidiAttachments"], 1)
        self.assertFalse(any(item["id"] == "restore-performer-controller" for item in report["recommendations"]))

    def test_request_validation_rejects_unknown_context(self):
        with self.assertRaisesRegex(ValueError, "must be an object"):
            build_recommendations(self.state, self.audio, self.midi, self.adapters, [])
        with self.assertRaisesRegex(ValueError, "unexpected recommendation field"):
            self.build({"prompt": "ignore the evidence"})
        with self.assertRaisesRegex(ValueError, "selected performer"):
            self.build({"playerId": "missing"})
        with self.assertRaisesRegex(ValueError, "goal must be one of"):
            self.build({"goal": "magical"})
        with self.assertRaisesRegex(ValueError, "1000"):
            self.build({"notes": "x" * 1001})


if __name__ == "__main__":
    unittest.main()
