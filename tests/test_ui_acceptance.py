import threading
import unittest
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import urlopen

from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


class MarkupInventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.elements.append((tag, attributes))
        if attributes.get("id"):
            self.ids.append(attributes["id"])


class UiAccessibilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "app.html").read_text()
        cls.css = (ROOT / "frontend" / "styles.css").read_text()
        cls.inventory = MarkupInventory()
        cls.inventory.feed(cls.html)

    def test_document_has_unique_targets_and_keyboard_bypass(self):
        self.assertEqual(len(self.inventory.ids), len(set(self.inventory.ids)))
        html = next(attrs for tag, attrs in self.inventory.elements if tag == "html")
        main = next(attrs for tag, attrs in self.inventory.elements if tag == "main")
        skip = next(attrs for tag, attrs in self.inventory.elements if tag == "a" and "skipLink" in attrs.get("class", "").split())
        self.assertEqual(html.get("lang"), "en")
        self.assertEqual(main.get("id"), "main-content")
        self.assertEqual(main.get("tabindex"), "-1")
        self.assertEqual(skip.get("href"), "#main-content")

    def test_all_buttons_declare_non_submitting_type(self):
        buttons = [attrs for tag, attrs in self.inventory.elements if tag == "button"]
        self.assertGreater(len(buttons), 25)
        self.assertEqual([attrs.get("id", "<dynamic>") for attrs in buttons if attrs.get("type") != "button"], [])

    def test_operator_feedback_is_a_polite_live_region(self):
        by_id = {attrs.get("id"): attrs for _, attrs in self.inventory.elements if attrs.get("id")}
        for target in ("launcherStatus", "dawAutomationStatus", "dawProductionStatus", "recoveryStatus"):
            self.assertEqual(by_id[target].get("role"), "status", target)
            self.assertEqual(by_id[target].get("aria-live"), "polite", target)

    def test_focus_is_visible_and_skip_link_only_appears_on_focus(self):
        self.assertIn(".skipLink:focus{transform:translateY(0)}", self.css)
        self.assertIn(":focus-visible{outline:3px solid var(--accent);outline-offset:3px}", self.css)

    def test_keyboard_transport_failures_are_not_silenced(self):
        app = (ROOT / "frontend" / "app.js").read_text()
        self.assertNotIn(".catch(()=>{})", app)
        self.assertIn('const report=(error)=>q("#launcherStatus")', app)

    def test_small_viewport_grid_children_can_shrink(self):
        self.assertIn(".layout>*{min-width:0}", self.css)
        self.assertIn(".pair>*{min-width:0}", self.css)
        self.assertIn(".pair input,.pair select{max-width:100%;width:100%}", self.css)


class ServedUiAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.dev_server import StageMeshHandler

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StageMeshHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def fetch(self, path):
        with urlopen(self.base + path, timeout=5) as response:
            return response.status, response.headers, response.read()

    def test_page_assets_and_read_only_api_share_hardened_origin(self):
        for path, expected_type in (("/", "text/html"), ("/styles.css", "text/css"), ("/app.js", "text/javascript"), ("/api/v1/state", "application/json")):
            status, headers, body = self.fetch(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(headers["Content-Type"].startswith(expected_type), (path, headers["Content-Type"]))
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
            self.assertTrue(body, path)


if __name__ == "__main__":
    unittest.main()
