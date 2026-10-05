import http.client
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dev_server import StageForgeHandler, StageForgeHTTPServer


class DesktopSessionTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "STAGEMESH_RUNTIME_MODE": "desktop",
            "STAGEMESH_REQUIRE_API_TOKEN": "1",
            "STAGEMESH_API_TOKEN": "a" * 64,
            "STAGEMESH_DESKTOP_SESSION_TOKEN": "b" * 64,
        }, clear=False)
        self.environment.start()
        self.server = StageForgeHTTPServer(("127.0.0.1", 0), StageForgeHandler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)
        self.environment.stop()

    def request(self, method, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_bootstrap_exchanges_one_launch_token_for_http_only_cookie(self):
        status, headers, _ = self.request("POST", "/desktop/session", {
            "X-StageMesh-Desktop-Token": "b" * 64,
        })
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        status, _, _ = self.request("GET", "/healthz", {"Cookie": cookie.split(";", 1)[0]})
        self.assertEqual(status, 200)

    def test_missing_or_wrong_bootstrap_token_is_denied(self):
        for token in (None, "wrong"):
            headers = {} if token is None else {"X-StageMesh-Desktop-Token": token}
            status, _, _ = self.request("POST", "/desktop/session", headers)
            self.assertEqual(status, 403)

    def test_legacy_desktop_contract_is_not_accepted(self):
        status, _, _ = self.request("POST", "/desktop/session", {
            "X-StageForge" + "-Desktop-Token": "b" * 64,
        })
        self.assertEqual(status, 403)
        with patch.dict(os.environ, {
            "STAGEMESH_RUNTIME_MODE": "",
            "STAGEMESH_DESKTOP_SESSION_TOKEN": "",
            "STAGEFORGE" + "_RUNTIME_MODE": "desktop",
            "STAGEFORGE" + "_DESKTOP_SESSION_TOKEN": "b" * 64,
        }, clear=False):
            status, _, _ = self.request("POST", "/desktop/session", {
                "X-StageMesh-Desktop-Token": "b" * 64,
            })
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
