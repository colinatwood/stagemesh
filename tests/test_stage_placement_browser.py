"""Optional real-browser acceptance for the production stage placement flow."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import re
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Playwright is optional")
class StagePlacementBrowserTests(unittest.TestCase):
    def test_context_placement_reopen_rotation_cancel_and_failed_save(self):
        from playwright.sync_api import sync_playwright

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(ROOT / "frontend")))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                if not Path(p.chromium.executable_path).exists():
                    self.skipTest("Playwright Chromium is not installed")
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 1200})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{server.server_port}/styles.css")
                    html = (ROOT / "frontend/app.html").read_text()
                    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S)
                    page.set_content(html)
                    page.add_style_tag(content=(ROOT / "frontend/styles.css").read_text())
                    page.route("**/api/v1/templates", lambda route: route.fulfill(json={"templates": []}))
                    for name in ("stage-placement.js", "stage-template.js"):
                        page.add_script_tag(content=(ROOT / "frontend" / name).read_text())
                    page.locator('[data-template-kind="performer"]').click(button="right")
                    panel = page.get_by_role("dialog", name="Stage object options")
                    self.assertTrue(panel.is_visible())
                    self.assertIsNone(page.evaluate("localStorage.getItem('stagemesh.stage-template.v1')"))
                    panel.get_by_role("button", name="Place on stage", exact=True).click()
                    canvas = page.locator("#templateCanvas")
                    canvas.click(position={"x": 200, "y": 200})
                    self.assertIsNone(page.evaluate("localStorage.getItem('stagemesh.stage-template.v1')"))
                    panel.get_by_label("Orientation (degrees)").fill("90")
                    panel.get_by_label("Orientation (degrees)").press("Tab")
                    canvas.click(position={"x": 250, "y": 250})
                    saved = page.evaluate("JSON.parse(localStorage.getItem('stagemesh.stage-template.v1'))")
                    self.assertEqual(saved["objects"][0]["rotation"], 90)
                    self.assertFalse(panel.is_visible())
                    page.locator(".templateObject").click()
                    self.assertTrue(panel.is_visible())
                    box = page.locator(".templateObject").bounding_box()
                    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    page.mouse.down()
                    page.mouse.move(box["x"] + box["width"] / 2 + 30, box["y"] + box["height"] / 2 + 20, steps=3)
                    page.mouse.up()
                    self.assertTrue(panel.is_visible())
                    self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('stagemesh.stage-template.v1'))"), saved)
                    panel.get_by_label("Orientation (degrees)").fill("180")
                    panel.get_by_label("Orientation (degrees)").press("Tab")
                    # All replacement/export/server operations refuse an active preview.
                    page.locator("#templateExport").click()
                    self.assertIn("save or cancel", page.locator("#templateHint").inner_text())
                    page.evaluate("() => { Storage.prototype.setItem = function() { throw Error('disk full'); }; }")
                    panel.get_by_role("button", name="Save placement").click()
                    self.assertIn("disk full", page.locator("#templateHint").inner_text())
                    self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('stagemesh.stage-template.v1'))"), saved)
                    page.keyboard.press("Escape")
                    self.assertEqual(page.locator(".templateObject").evaluate("node => node.style.transform"), "translate(-50%, -50%) rotate(90deg)")
                    # Context options open beneath layout cards; cancelling preserves the stage.
                    page.locator(".templatePreset").first.click(button="right")
                    self.assertTrue(panel.is_visible())
                    panel.get_by_role("button", name="Cancel", exact=True).click()
                    self.assertEqual(page.locator(".templateObject").count(), 1)
                    self.assertEqual(errors, [])
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
