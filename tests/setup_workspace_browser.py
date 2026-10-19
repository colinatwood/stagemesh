"""Real Chromium exercise for the setup wizard and one-workspace-at-a-time menu."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading
import unittest

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class SetupWorkspaceBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(ROOT / "frontend")))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True, args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def fixture(self, width=1440, height=900):
        page = self.browser.new_page(viewport={"width": width, "height": height})
        page.set_default_timeout(5000)
        self.addCleanup(page.close)
        self.errors = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{self.server.server_port}/styles.css")
        html = (ROOT / "frontend/app.html").read_text()
        page.set_content(re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S))
        page.add_style_tag(content=(ROOT / "frontend/styles.css").read_text())
        page.route("**/api/v1/templates", lambda route: route.fulfill(json={"templates": []}))
        page.evaluate("""() => {
          const state = {audio:{inputDeviceId:'in',deviceId:'out',inputRoute:{output:0,gain:0},limiterCeilingDb:-1},players:[{id:'lead',name:'Lead vocal'}],lighting:{network:{protocol:'artnet',target:'127.0.0.1',port:6454,universeBase:1}}};
          window.setupData={state, audio:{available:true,desiredInputDeviceId:'in',desiredDeviceId:'out',devices:[{id:'in',name:'Test input',input:true,connected:true},{id:'out',name:'Test output',output:true,connected:true}]},midi:{available:true,bindings:{},devices:[{id:'midi',name:'Test controller',connected:true}]},lighting:{armed:false,desired:state.lighting.network},native:{available:true},inputs:{inputs:[{active:false}]},outputs:{outputs:[{active:false}]}};
          window.setupWrites=[];
          const paths={'/api/v1/state':'state','/api/v1/audio/devices':'audio','/api/v1/midi/devices':'midi','/api/v1/lighting/network':'lighting','/api/v1/native':'native','/api/v1/audio/inputs':'inputs','/api/v1/audio/outputs':'outputs'};
          window.StageMeshUI={
            async api(path,options={}) {
              if (options.method==='POST') {
                const body=JSON.parse(options.body); setupWrites.push({path,body});
                if(path==='/api/v1/audio/input/deactivate')setupData.inputs.inputs[0].active=false;
                else if(path==='/api/v1/audio/deactivate')setupData.outputs.outputs[0].active=false;
                else if(path==='/api/v1/lighting/network/arm' && body.armed===false)setupData.lighting.armed=false;
                else throw Error('unexpected mutation');
                return {};
              }
              if (!paths[path]) throw Error('unexpected read: '+path);
              return structuredClone(setupData[paths[path]]);
            },
            async configureAudio(body) {
              if(window.failSetupSave)throw Error('revision conflict');
              setupWrites.push({path:'/api/v1/audio',body});Object.assign(setupData.state.audio,body);
              if(body.inputDeviceId)setupData.audio.desiredInputDeviceId=body.inputDeviceId;
              if(body.deviceId)setupData.audio.desiredDeviceId=body.deviceId;
            },
            async configureLighting(body){setupWrites.push({path:'/api/v1/lighting/network',body});setupData.lighting.desired=body;},
            async bindMidi(deviceId,playerId){setupWrites.push({path:'/midi/attach',body:{deviceId,playerId}});setupData.midi.bindings[deviceId]=playerId;}
          };
        }""")
        for name in ("stage-placement.js", "stage-template.js", "workspace.js", "setup-wizard.js"):
            page.add_script_tag(content=(ROOT / "frontend" / name).read_text())
        return page

    def assert_one_workspace(self, page, target):
        self.assertEqual(page.locator('[data-workspace-page]:not([hidden])').count(), 1)
        self.assertTrue(page.locator(f'#{target}').is_visible())
        ids = page.locator('[id]').evaluate_all("nodes => nodes.map(node => node.id)")
        self.assertEqual(len(ids), len(set(ids)))

    def test_menus_and_setup_fit_reference_screens(self):
        for width, height in ((1440, 900), (1024, 768), (768, 1024), (390, 844)):
            with self.subTest(width=width):
                page = self.fixture(width, height)
                self.assert_one_workspace(page, "setup")
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - innerWidth"), 0)
                self.assertLessEqual(page.locator("#setupNext").bounding_box()["y"] + page.locator("#setupNext").bounding_box()["height"], height)
                self.assertEqual(page.evaluate("setupWrites.length"), 0)
                for caption, target in (("Stage Editor", "stage-editor"), ("Show Control", "show-control"), ("Studio", "studio"), ("Devices", "operations"), ("Reports", "activity-panel"), ("Setup", "setup")):
                    page.get_by_role("navigation", name="Primary navigation").get_by_role("link", name=caption).click()
                    self.assert_one_workspace(page, target)
                page.get_by_role("navigation", name="Primary navigation").get_by_role("link", name="Devices").click()
                for category in ("input", "output", "midi", "lighting", "preferences", "system", "compatibility", "advanced"):
                    page.locator("#deviceMenu").select_option(category)
                    self.assertEqual(page.locator('[data-device-panel]:not([hidden])').count(), 1)
                self.assertEqual(page.evaluate("setupWrites.length"), 0)
                self.assertEqual(self.errors, [])

    def test_setup_saves_only_explicit_configuration_and_rechecks_before_finish(self):
        page = self.fixture()
        page.locator("#setupNext").click()
        page.get_by_label("Recording input", exact=True).select_option("in")
        page.get_by_label("Performer / source", exact=True).select_option("lead")
        page.locator("#setupNext").click()
        page.get_by_label("Playback output", exact=True).wait_for()
        page.locator("#setupSkip").click()
        page.get_by_label("MIDI controller", exact=True).select_option("midi")
        page.get_by_label("Control performer", exact=True).select_option("lead")
        page.locator("#setupNext").click()
        page.get_by_label("Lighting protocol", exact=True).wait_for()
        page.locator("#setupSkip").click()
        page.get_by_text("Baseline reviewed:", exact=False).wait_for()
        writes = page.evaluate("setupWrites")
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[0]["body"], {"inputDeviceId": "in", "inputPlayerId": "lead", "inputRoute": {"output": 0, "gain": 0}})
        page.evaluate("setupData.outputs.outputs[0].active = true")
        page.locator("#setupNext").click()
        page.get_by_text("Audio output is active or unverified.", exact=False).wait_for()
        self.assertIsNone(page.evaluate("localStorage.getItem('stagemesh.setup.review.v1')"))
        self.assertTrue(page.locator("#setupNext").is_disabled())
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="Stop capture, audio output and lighting").click()
        page.get_by_text("Baseline reviewed:", exact=False).wait_for()
        page.locator("#setupNext").click()
        page.locator("#deviceMenu").wait_for(state="visible")
        self.assert_one_workspace(page, "operations")
        self.assertEqual(page.locator("#deviceMenu").input_value(), "input")
        writes = page.evaluate("setupWrites")
        self.assertEqual(len(writes), 5)
        self.assertFalse(writes[-1]["body"]["armed"])
        self.assertFalse(any("activate" in row["path"] and "deactivate" not in row["path"] for row in writes))
        self.assertTrue(page.evaluate("JSON.parse(localStorage.getItem('stagemesh.setup.review.v1')).reviewed"))
        page.get_by_role("navigation", name="Primary navigation").get_by_role("link", name="Stage Editor").click()
        page.locator("#stageToolsMenu").select_option("objects")
        page.locator("#templateAdd").click()
        page.get_by_role("navigation", name="Primary navigation").get_by_role("link", name="Setup").click()
        self.assert_one_workspace(page, "stage-editor")
        page.get_by_role("dialog").get_by_role("button", name="Cancel", exact=True).click()
        page.get_by_role("navigation", name="Primary navigation").get_by_role("link", name="Setup").click()
        self.assert_one_workspace(page, "setup")
        self.assertEqual(self.errors, [])

    def test_failed_save_stays_on_input_and_does_not_complete_setup(self):
        page = self.fixture()
        page.locator("#setupNext").click()
        page.get_by_label("Recording input", exact=True).select_option("in")
        page.evaluate("window.failSetupSave = true")
        page.locator("#setupNext").click()
        page.get_by_text("Settings were not confirmed:", exact=False).wait_for()
        self.assertIn("revision conflict", page.locator("#setupStatus").inner_text())
        self.assertEqual(page.locator("#setupProgress").inner_text(), "Step 2 of 6")
        self.assertEqual(page.evaluate("setupWrites.length"), 0)
        self.assertIsNone(page.evaluate("localStorage.getItem('stagemesh.setup.review.v1')"))
        self.assertEqual(self.errors, [])

    def test_compact_tools_preserve_controls_and_only_reveal_requested_options(self):
        for width, height in ((1440, 900), (1024, 768), (768, 1024), (390, 844)):
            with self.subTest(width=width):
                page = self.fixture(width, height)
                page.get_by_role("link", name="Stage Editor", exact=False).click()
                self.assertTrue(page.locator("#templateCanvas").is_visible())
                for selector in (".objectPalette", ".templateInspector", ".templateDock"):
                    self.assertFalse(page.locator(selector).is_visible())
                page.locator("#stageToolsMenu").select_option("objects")
                page.locator("#templateObjectLabel").fill("Lead vocal")
                page.locator("#stageToolsMenu").select_option("selection")
                self.assertFalse(page.locator(".objectPalette").is_visible())
                self.assertTrue(page.locator("#templateDelete").is_visible())
                page.locator("#stageToolsMenu").select_option("layouts")
                self.assertTrue(page.locator("#templatePresets").is_visible())
                page.locator("#stageToolsMenu").select_option("objects")
                self.assertEqual(page.locator("#templateObjectLabel").input_value(), "Lead vocal")
                page.get_by_role("link", name="Devices", exact=False).click()
                self.assertTrue(page.locator("#recoverAudioInput").is_visible())
                self.assertTrue(page.locator("#deactivateAudioInput").is_visible())
                self.assertFalse(page.locator("#audioInputRouteGain").is_visible())
                page.get_by_text("Input routing and diagnostics", exact=True).click()
                self.assertTrue(page.locator("#audioInputRouteGain").is_visible())
                page.locator("#audioInputRouteGain").fill("0.25")
                page.locator("#deviceMenu").select_option("output")
                self.assertTrue(page.locator("#deactivateAudio").is_visible())
                self.assertFalse(page.locator("#limiterCeiling").is_visible())
                page.get_by_text("Output settings and diagnostics", exact=True).click()
                self.assertTrue(page.locator("#limiterCeiling").is_visible())
                page.locator("#deviceMenu").select_option("input")
                self.assertEqual(page.locator("#audioInputRouteGain").input_value(), "0.25")
                self.assertEqual(page.evaluate("setupWrites.length"), 0)
                self.assertEqual(page.evaluate("document.documentElement.scrollWidth - innerWidth"), 0)
                self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
