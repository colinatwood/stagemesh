import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("device_health", ROOT / "backend" / "device_health.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def health(**overrides):
    value = {
        "schema": "stagemesh.device-health", "version": "1.0", "deviceId": "device-1",
        "observedAtMonotonicNs": 1000, "sequence": 1, "state": "safe", "quality": "good",
        "freshnessMs": 10, "latencyMs": 2, "jitterMs": 1,
        "authority": {"localAuthority": True, "leaseValid": True, "physicalInterlock": True, "emergencyStop": True},
        "faults": [], "physicalOutputsArmed": False,
    }
    value.update(overrides)
    return value


class DeviceHealthTests(unittest.TestCase):
    def test_healthy_telemetry_is_safe_to_use(self):
        self.assertEqual(module.validate_health(health()), [])
        self.assertEqual(module.assess_health(health())["status"], "healthy")
        self.assertTrue(module.assess_health(health())["safeToUse"])

    def test_replayed_or_regressed_telemetry_is_not_safe_to_use(self):
        previous = health(sequence=4, observedAtMonotonicNs=4000)
        replay = module.assess_health(health(sequence=4, observedAtMonotonicNs=5000), previous=previous)
        self.assertFalse(replay["safeToUse"])
        self.assertIn("telemetry sequence replayed or out of order", replay["reasons"])
        regressed = module.assess_health(health(sequence=5, observedAtMonotonicNs=4000), previous=previous)
        self.assertFalse(regressed["safeToUse"])
        self.assertIn("telemetry monotonic timestamp regressed", regressed["reasons"])

    def test_health_rejects_observation_from_a_different_device(self):
        result = module.assess_health(health(deviceId="device-2"), previous=health(deviceId="device-1"))
        self.assertFalse(result["safeToUse"])
        self.assertIn("telemetry device identity changed", result["reasons"])

    def test_stale_fault_and_missing_authority_fail_closed(self):
        self.assertEqual(module.assess_health(health(freshnessMs=3000))["status"], "stale")
        self.assertEqual(module.assess_health(health(state="faulted"))["status"], "fault")
        value = health(authority={"localAuthority": False, "leaseValid": True, "physicalInterlock": True, "emergencyStop": True})
        self.assertFalse(module.assess_health(value)["safeToUse"])

    def test_two_hundred_fifty_boundary_slices(self):
        cases = []
        for index, field in enumerate(("schema", "version", "deviceId", "observedAtMonotonicNs", "sequence", "state", "quality", "freshnessMs", "authority", "physicalOutputsArmed"), 1):
            value = health(); value[field] = None; cases.append((f"missing-{field}-{index}", value, True))
        for index in range(11, 41): cases.append((f"bad-schema-{index}", health(schema="bad"), True))
        for index in range(41, 81): cases.append((f"stale-{index}", health(freshnessMs=2501 + index), False))
        for index in range(81, 121): cases.append((f"fault-{index}", health(state="faulted", faults=[f"fault-{index}" ]), False))
        for index in range(121, 161): cases.append((f"authority-{index}", health(authority={"localAuthority": False, "leaseValid": True, "physicalInterlock": True, "emergencyStop": True}), False))
        for index in range(161, 201): cases.append((f"healthy-{index}", health(sequence=index, observedAtMonotonicNs=index * 1000), False))
        for index in range(201, 251): cases.append((f"invalid-quality-{index}", health(quality="not-a-quality"), True))
        self.assertEqual(len(cases), 250)
        for name, value, invalid in cases:
            with self.subTest(slice=name):
                self.assertEqual(bool(module.validate_health(value)), invalid)
                if not invalid: self.assertFalse(module.assess_health(value)["physicalOutputsArmed"])


if __name__ == "__main__":
    unittest.main()
