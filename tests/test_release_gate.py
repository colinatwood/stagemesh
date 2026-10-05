import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded

class ReleaseGateTests(unittest.TestCase):
    def test_sanitizer_gate_fails_closed_without_tools(self):
        gate = module("sanitizer-check")
        with patch.object(gate.shutil, "which", return_value=None), patch.object(gate.sys, "argv", ["sanitizer-check.py"]):
            self.assertEqual(gate.main(), 1)
    def test_missing_prerequisite_fails_closed(self):
        gate = module("release-check")
        with patch.object(gate.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "cmake, ctest, node"):
                gate.prerequisites()

    def test_present_prerequisites_accepted(self):
        gate = module("release-check")
        with patch.object(gate.shutil, "which", return_value="/tool"):
            gate.prerequisites()

    def test_every_public_schema_is_valid_json(self):
        schemas=list((ROOT/"schemas").glob("*.json"));self.assertGreater(len(schemas),0)
        for schema in schemas:
            with self.subTest(schema=schema.name):json.loads(schema.read_text())

    def test_missing_engine_cannot_silently_skip_native_tests(self):
        gate = module("release-python-tests")
        with patch.dict(gate.os.environ, {"STAGEMESH_NATIVE_ENGINE": ""}):
            self.assertEqual(gate.main(), 1)

    def test_automation_performance_report_matches_public_contract(self):
        gate = module("automation-performance")
        report = gate.run_gate(point_count=64, frames=512, block_size=64)
        schema = json.loads((ROOT / "schemas" / "automation-performance-report.schema.json").read_text())
        self.assertTrue(report["passed"])
        self.assertEqual(report["documentType"], schema["properties"]["documentType"]["const"])
        self.assertEqual(report["schemaVersion"], schema["properties"]["schemaVersion"]["const"])
        self.assertTrue(set(schema["required"]).issubset(report))
        self.assertEqual(report["preparedPointReads"], report["expectedPreparedPointReads"])
        self.assertEqual(report["blockEntrySearch"], "binary")
