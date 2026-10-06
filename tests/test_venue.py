import sys
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from venue import VenueProfileStore, inspect_venue_profile, merge_discovered_devices, normalize_venue_profile, venue_compatibility_plan, resolve_lighting_fixture_intent
from state import ShowState


class VenueCompatibilityTests(unittest.TestCase):
    def profile(self):
        return {
            "documentType": "org.upp.venue-profile",
            "schemaVersion": 1,
            "id": "club",
            "name": "Club",
            "capabilities": ["audio.transport", "authority.fence"],
            "devices": [
                {
                    "id": "audio-a",
                    "kind": "audio",
                    "status": "expected",
                    "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"],
                    "latency": {"fixedMs": 6, "jitterMs": 1, "timestamped": True},
                },
                {
                    "id": "lights-a",
                    "kind": "lighting",
                    "status": "expected",
                    "capabilities": ["lighting.state"],
                    "latency": {"fixedMs": 30, "jitterMs": 4, "timestamped": True},
                },
            ],
            "humans": [
                {"id": "lighting-op", "available": True, "capabilities": ["lighting.state"], "authority": ["lighting"]}
            ],
            "adapters": [
                {"from": "lighting.state", "to": "lighting.artnet.send", "quality": "degraded"}
            ],
            "patch": {
                "audio.foh": {"target": "audio-a:out-1-2"},
                "audio.live-input": {"target": "audio-a:in-1"},
                "audio.monitor": {"target": "audio-a:out-3-4"},
                "lighting.primary": {"target": "lights-a:universe-1"},
            },
            "futureVenueField": {"keep": True},
        }

    def requirements(self):
        return [
            {"id": "transport", "preferred": "audio.transport", "required": True, "domain": "audio"},
            {"id": "output", "preferred": "audio.output.multi", "required": True, "domain": "audio", "patchKey": "audio.foh",
             "timing": {"maxLatencyMs": 20, "maxJitterMs": 5}},
            {"id": "input", "preferred": "audio.input.capture", "required": True, "domain": "audio", "patchKey": "audio.live-input",
             "timing": {"maxLatencyMs": 10, "maxJitterMs": 3}},
            {"id": "lighting", "preferred": "lighting.artnet.send", "required": True, "domain": "lighting", "patchKey": "lighting.primary",
             "alternatives": [{"capability": "lighting.state", "quality": "degraded"}]},
            {"id": "monitor", "preferred": "audio.monitor", "required": False, "domain": "audio", "patchKey": "audio.monitor"},
        ]

    def test_future_venue_profile_can_be_forward_readable(self):
        profile = self.profile()
        profile["schemaVersion"] = 3
        profile["minimumReaderSchemaVersion"] = 1
        profile["futureSpatialTopology"] = {"dimensions": 7}
        report = inspect_venue_profile(profile)
        self.assertTrue(report["readable"])
        self.assertEqual(report["mode"], "forward-compatible")
        normalized = normalize_venue_profile(profile)
        self.assertEqual(normalized["futureSpatialTopology"]["dimensions"], 7)

    def test_future_venue_profile_can_require_newer_reader(self):
        profile = self.profile()
        profile["schemaVersion"] = 3
        profile["minimumReaderSchemaVersion"] = 2
        report = inspect_venue_profile(profile)
        self.assertFalse(report["readable"])
        with self.assertRaises(ValueError):
            venue_compatibility_plan(profile, self.requirements())

    def test_profile_preserves_unknown_fields(self):
        profile = normalize_venue_profile(self.profile())
        self.assertTrue(profile["futureVenueField"]["keep"])
        self.assertEqual(profile["documentType"], "org.upp.venue-profile")

    def test_discovery_marks_expected_missing_and_keeps_unprofiled(self):
        profile = normalize_venue_profile(self.profile())
        devices, warnings = merge_discovered_devices(profile, [
            {"id": "audio-a", "status": "online", "capabilities": ["audio.output.multi"]},
            {"id": "surprise-midi", "status": "online", "capabilities": ["midi.read"]},
        ])
        by_id = {item["id"]: item for item in devices}
        self.assertTrue(by_id["audio-a"]["discovered"])
        self.assertEqual(by_id["lights-a"]["status"], "offline")
        self.assertTrue(by_id["surprise-midi"]["unexpected"])
        self.assertTrue(any("expected device offline" in item for item in warnings))

    def test_discovery_alias_keeps_logical_device_identity(self):
        profile = self.profile()
        profile["devices"][0]["matchIds"] = ["alsa:hw:2,0"]
        normalized = normalize_venue_profile(profile)
        devices, _ = merge_discovered_devices(normalized, [
            {"id": "alsa:hw:2,0", "status": "online", "capabilities": ["audio.output.multi"]}
        ])
        audio = next(item for item in devices if item["id"] == "audio-a")
        self.assertTrue(audio["discovered"])
        self.assertEqual(audio["discoveredId"], "alsa:hw:2,0")

    def test_live_discovery_provider_exposes_concrete_execution_id(self):
        result = venue_compatibility_plan(self.profile(), self.requirements(), discovered_devices=[
            {"id": "audio-a", "status": "online", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"],
             "latency": {"fixedMs": 6, "jitterMs": 1, "timestamped": True}},
            {"id": "lights-a", "status": "online", "capabilities": ["lighting.state"], "latency": {"fixedMs": 30, "jitterMs": 4, "timestamped": True}},
        ])
        plan = {item["id"]: item for item in result["devicePlan"]}
        self.assertEqual(plan["output"]["provider"]["discoveredId"], "audio-a")
        self.assertTrue(plan["output"]["provider"]["discovered"])

    def test_human_fallback_is_visible_when_profiled_device_is_offline(self):
        result = venue_compatibility_plan(self.profile(), self.requirements(), discovered_devices=[
            {"id": "audio-a", "status": "online", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"],
             "latency": {"fixedMs": 6, "jitterMs": 1, "timestamped": True}}
        ])
        plan = {item["id"]: item for item in result["devicePlan"]}
        self.assertEqual(plan["lighting"]["provider"]["type"], "human")
        self.assertGreaterEqual(result["humanAssistedRequirements"], 1)

    def test_plan_uses_explicit_adapter_and_patch(self):
        result = venue_compatibility_plan(self.profile(), self.requirements(), discovered_devices=[
            {"id": "audio-a", "status": "online", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"],
             "latency": {"fixedMs": 6, "jitterMs": 1, "timestamped": True}},
            {"id": "lights-a", "status": "online", "capabilities": ["lighting.state"], "latency": {"fixedMs": 30, "jitterMs": 4}},
        ])
        self.assertTrue(result["compatible"])
        self.assertEqual(result["grade"], "degraded")
        self.assertEqual(result["readiness"], "ready")
        plan = {item["id"]: item for item in result["devicePlan"]}
        self.assertEqual(plan["lighting"]["decision"]["status"], "adapter")
        self.assertEqual(plan["output"]["provider"]["id"], "audio-a")
        self.assertEqual(plan["output"]["patchStatus"], "mapped")
        departments = {item["domain"]: item for item in result["departments"]}
        self.assertIn("audio", departments)
        self.assertTrue(any(item["type"] == "verify-adapter" for item in result["actions"]))

    def test_timing_can_block_capable_device(self):
        profile = self.profile()
        profile["devices"][0]["latency"] = {"fixedMs": 35, "jitterMs": 8}
        result = venue_compatibility_plan(profile, self.requirements())
        self.assertFalse(result["compatible"])
        self.assertEqual(result["readiness"], "blocked")
        self.assertTrue(any("timing blocked: output" in item for item in result["blockers"]))

    def test_missing_patch_is_preparation_issue_not_capability_failure(self):
        profile = self.profile()
        del profile["patch"]["audio.foh"]
        result = venue_compatibility_plan(profile, self.requirements())
        self.assertTrue(result["compatible"])
        self.assertEqual(result["readiness"], "needs-patch")
        self.assertIn("output", result["unmappedRequired"])

    def test_offline_adaptation_preview_uses_same_transaction_logic(self):
        with tempfile.TemporaryDirectory() as tmp:
            show_path = Path(tmp) / "show.json"
            venue_path = Path(tmp) / "venue.json"
            show_path.write_text(json.dumps(ShowState().persistence_snapshot()), "utf-8")
            venue_path.write_text(json.dumps(self.profile()), "utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "stagemesh-venue-adapt.py"), str(show_path), str(venue_path)],
                cwd=ROOT, text=True, capture_output=True, check=True,
            )
            transaction = json.loads(result.stdout)
            self.assertTrue(transaction["offlinePreview"])
            self.assertEqual(transaction["venueId"], "club")
            self.assertIn("audio.foh", transaction["mappings"])

    def test_venue_profile_store_is_separate_and_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = VenueProfileStore(Path(tmp) / "venue-profile.json")
            saved = store.save(self.profile())
            loaded = store.load()
            self.assertEqual(saved["id"], "club")
            self.assertEqual(loaded["id"], "club")
            self.assertTrue(loaded["futureVenueField"]["keep"])

    def test_semantic_lighting_fixture_intent_resolves_through_active_patch(self):
        mapping = {
            "patch": {
                "execution": {
                    "protocol": "sacn",
                    "target": "127.0.0.1",
                    "universeBase": 101,
                    "fixtures": {
                        "front-wash-left": {
                            "universe": 2,
                            "address": 17,
                            "parameters": {
                                "intensity": 0,
                                "red": {"offset": 1, "minimum": 10, "maximum": 210},
                                "shutter": {"offset": 4, "minimum": 0, "maximum": 255, "invert": True},
                            },
                        }
                    },
                }
            }
        }
        intensity = resolve_lighting_fixture_intent(mapping, "front-wash-left", "intensity", 0.5)
        self.assertEqual(intensity["universe"], 2)
        self.assertEqual(intensity["channel"], 17)
        self.assertEqual(intensity["value"], 128)
        red = resolve_lighting_fixture_intent(mapping, "front-wash-left", "red", 0.25)
        self.assertEqual(red["channel"], 18)
        self.assertEqual(red["value"], 60)
        shutter = resolve_lighting_fixture_intent(mapping, "front-wash-left", "shutter", 1.0)
        self.assertEqual(shutter["channel"], 21)
        self.assertEqual(shutter["value"], 0)

    def test_semantic_lighting_fixture_intent_rejects_unmapped_or_unsafe_channels(self):
        mapping = {"patch": {"execution": {"fixtures": {"edge": {"universe": 0, "address": 512, "parameters": {"intensity": 1}}}}}}
        with self.assertRaises(ValueError):
            resolve_lighting_fixture_intent(mapping, "missing", "intensity", 0.5)
        with self.assertRaises(ValueError):
            resolve_lighting_fixture_intent(mapping, "edge", "intensity", 0.5)
        with self.assertRaises(ValueError):
            resolve_lighting_fixture_intent(mapping, "edge", "missing", 0.5)
        with self.assertRaises(ValueError):
            resolve_lighting_fixture_intent(mapping, "edge", "intensity", 1.1)


if __name__ == "__main__":
    unittest.main()
