import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from runtime import MAX_API_FRAME, _api_frame


class DawTransportContractTests(unittest.TestCase):
    def test_frame_accepts_only_bounded_json_integers(self):
        self.assertEqual(_api_frame({}, "frame", 256), 256)
        self.assertEqual(_api_frame({"frame": MAX_API_FRAME}, "frame"), MAX_API_FRAME)
        for value in (True, False, 1.0, "1", None, -1, MAX_API_FRAME + 1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "frame"):
                _api_frame({"frame": value}, "frame")

    def test_production_controls_are_accessible_and_nested(self):
        html = (ROOT / "frontend" / "app.html").read_text()
        for control in ("dawPlaybackBegin", "dawPlaybackEnd", "dawPlaybackLoop", "dawCaptureAbort", "dawProductionRefresh"):
            self.assertIn(f'id="{control}"', html)
        self.assertIn('id="dawProductionStatus" class="hint" role="status" aria-live="polite"', html)
        production_start = html.index('<div class="subPanel"><strong>Production</strong>')
        recovery_start = html.index('<strong>Interrupted recordings</strong>')
        self.assertLess(production_start, html.index('id="captureFinishName"'))
        self.assertLess(html.index('id="captureFinishName"'), recovery_start)


if __name__ == "__main__":
    unittest.main()
