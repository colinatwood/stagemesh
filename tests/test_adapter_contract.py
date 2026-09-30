import importlib.util
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("adapter_contract", ROOT / "backend" / "adapter_contract.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

sys.path.insert(0, str(ROOT / "backend"))
from adapters import AdapterRegistry


def manifest(**overrides):
    value = {"id": "vendor.bridge", "name": "Vendor Bridge", "kind": "bridge", "priority": 1, "capabilities": ["lighting.state"], "fallbacks": ["full", "off"], "documentedInterface": True, "supportsSafeStop": True, "physicalOutput": False, "physicalOutputsArmed": False}
    value.update(overrides)
    return value


class AdapterContractTests(unittest.TestCase):
    def test_reference_manifest_is_valid(self):
        self.assertEqual(module.validate_manifest(manifest()), [])

    def test_physical_output_requires_safety_contract(self):
        value = manifest(physicalOutput=True)
        errors = module.validate_manifest(value)
        self.assertIn("physical-output adapters require the device safety contract", errors)

    def test_direct_physical_commands_are_rejected(self):
        self.assertIn("directPhysicalCommands is forbidden; adapters expose bounded intent only", module.validate_manifest(manifest(directPhysicalCommands=True)))

    def test_selection_is_deterministic_and_disarmed(self):
        result = module.select_capability([manifest(id="z", priority=2), manifest(id="a", priority=1)], ["lighting.state"])
        self.assertEqual(result["selected"], "a")
        self.assertFalse(result["physicalOutputsArmed"])

    def test_registry_snapshot_is_manifest_compatible(self):
        snapshots = AdapterRegistry().snapshot()
        self.assertEqual(len(snapshots), 17)
        self.assertEqual(module.validate_manifest(snapshots[6]), [])
        self.assertEqual(snapshots[6]["kind"], "midi")
        self.assertIn("estimatedCpu", snapshots[0])
        self.assertNotIn("estimated_cpu", snapshots[0])
        self.assertFalse(any(item["physicalOutputsArmed"] for item in snapshots))

    def test_one_hundred_adapter_boundary_slices(self):
        cases = []
        for index, field in enumerate(("id", "name", "kind", "priority", "capabilities", "fallbacks"), 1):
            value = manifest(); value.pop(field); cases.append((f"missing-{field}-{index}", value, True))
        for index in range(7, 27):
            cases.append((f"duplicate-capability-{index}", manifest(capabilities=["x", "x"]), True))
        for index in range(27, 47):
            cases.append((f"bad-priority-{index}", manifest(priority=6), True))
        for index in range(47, 67):
            cases.append((f"direct-command-{index}", manifest(directPhysicalCommands=True), True))
        for index in range(67, 87):
            cases.append((f"physical-no-contract-{index}", manifest(physicalOutput=True), True))
        for index in range(87, 101):
            cases.append((f"valid-simulator-{index}", manifest(kind="simulator", capabilities=[f"simulated.{index}"]), False))
        self.assertEqual(len(cases), 100)
        for name, value, invalid in cases:
            with self.subTest(slice=name):
                self.assertEqual(bool(module.validate_manifest(value)), invalid)


if __name__ == "__main__":
    unittest.main()
