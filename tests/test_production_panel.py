import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProductionPanelTests(unittest.TestCase):
    def test_dom_workflow(self):
        subprocess.run(["node", str(Path(__file__).with_name("production_panel_test.js"))], check=True)

    def test_openapi_contract_is_parseable_and_covers_routes(self):
        contract = json.loads((ROOT / "frontend" / "openapi.json").read_text())
        self.assertEqual(contract["openapi"], "3.1.0")
        self.assertEqual(set(contract["paths"]), {
            "/api/v1/witness/recover",
            "/api/v1/advisor/recommendations",
            "/api/v1/audio/overload/plan",
            "/api/v1/audio/overload/prepare",
            "/api/v1/daw/production", "/api/v1/daw/playback",
            "/api/v1/daw/temp-resources", "/api/v1/daw/temp-resources/cleanup",
            "/api/v1/daw/plugin-hosts/lifecycle",
            "/api/v1/daw/plugin-delay-graph",
            "/api/v1/daw/capture", "/api/v1/daw/capture/recovery",
            "/api/v1/daw/edit",
            "/api/v1/daw/markers",
            "/api/v1/daw/automation",
            "/api/v1/handoff/planned/peer-ready",
            "/api/v1/handoff/planned/release-authority",
            "/api/v1/hardware/audio-conversion-plan",
            "/api/v1/audio/identity/rebind",
            "/api/v1/technology/conformance-receipt",
        })
        self.assertFalse(contract["components"]["schemas"]["ProductionStatus"]["properties"]["physicalOutputsArmed"]["const"])


if __name__ == "__main__":
    unittest.main()
