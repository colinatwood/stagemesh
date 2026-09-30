import http.client
import json
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from dev_server import OperationCostLimiter, StageMeshHTTPServer, StageMeshHandler, expensive_operation_class


class OperationCostLimiterTests(unittest.TestCase):
    def test_exact_expensive_route_classes_are_bounded(self):
        self.assertEqual(expensive_operation_class("POST", "/api/v1/checkpoint"), "maintenance")
        self.assertEqual(expensive_operation_class("POST", "/api/v1/audio/scan"), "discovery")
        self.assertEqual(expensive_operation_class("POST", "/api/v1/compatibility/show-plan"), "planning")
        self.assertEqual(expensive_operation_class("POST", "/api/v1/daw/render"), "storage")
        self.assertEqual(expensive_operation_class("POST", "/api/v1/community/proposals/p-1/email-voters"), "external")
        self.assertIsNone(expensive_operation_class("POST", "/api/v1/transport"))

    def test_class_limit_rejects_without_consuming_other_classes(self):
        limiter = OperationCostLimiter(total_limit=3, class_limits={"maintenance": 1, "discovery": 1})
        self.assertTrue(limiter.acquire("maintenance"))
        self.assertFalse(limiter.acquire("maintenance"))
        self.assertTrue(limiter.acquire("discovery"))
        status = limiter.status()
        self.assertEqual(status["active"], {"maintenance": 1, "discovery": 1})
        self.assertEqual(status["rejected"]["maintenance"], 1)
        limiter.release("discovery")
        limiter.release("maintenance")
        self.assertEqual(limiter.status()["active"], {"maintenance": 0, "discovery": 0})


class OperationCostHttpTests(unittest.TestCase):
    class Server(StageMeshHTTPServer):
        max_connections = 4
        max_expensive_operations = 1
        expensive_class_limits = {"maintenance": 1, "discovery": 1, "planning": 1, "storage": 1, "external": 1}

    class Handler(StageMeshHandler):
        body_reads = 0
        fail_once = False

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if not self._guard_request(path):
                return
            type(self).body_reads += 1
            self._read_json()
            if type(self).fail_once:
                type(self).fail_once = False
                raise RuntimeError("injected route failure")
            self._json(200, {"ok": True, "path": path})

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if not self._guard_request(path):
                return
            self._json(200, {"ok": True, "path": path})

    def setUp(self):
        self.Handler.body_reads = 0
        self.Handler.fail_once = False
        self.server = self.Server(("127.0.0.1", 0), self.Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(2)

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=2)
        payload = None if body is None else json.dumps(body)
        headers = {}
        if payload is not None:
            headers = {"Content-Type": "application/json", "Content-Length": str(len(payload.encode()))}
        try:
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            parsed = json.loads(raw.decode()) if raw else {}
            return response.status, dict(response.getheaders()), parsed
        finally:
            conn.close()

    def test_saturated_expensive_budget_rejects_before_body_and_preserves_cheap_request(self):
        self.assertTrue(self.server.operation_limiter.acquire("maintenance"))
        try:
            status, headers, body = self.request("POST", "/api/v1/checkpoint", {})
            self.assertEqual(status, 503)
            self.assertEqual(headers.get("Retry-After"), "1")
            self.assertEqual(body["operationClass"], "maintenance")
            self.assertEqual(self.Handler.body_reads, 0)

            status, _, body = self.request("GET", "/healthz")
            self.assertEqual(status, 200)
            self.assertTrue(body["ok"])
        finally:
            self.server.operation_limiter.release("maintenance")

        status, _, body = self.request("POST", "/api/v1/checkpoint", {})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(self.Handler.body_reads, 1)

    def test_handler_failure_releases_expensive_slot(self):
        self.Handler.fail_once = True
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=2)
        try:
            conn.request("POST", "/api/v1/checkpoint", body="{}", headers={"Content-Type": "application/json"})
            with self.assertRaises(http.client.RemoteDisconnected):
                conn.getresponse()
        finally:
            conn.close()
        # The handler's finally path must return the admission slot even when the
        # route crashes after body consumption.
        for _ in range(20):
            if self.server.operation_limiter.status()["active"]["maintenance"] == 0:
                break
            time.sleep(0.01)
        self.assertEqual(self.server.operation_limiter.status()["active"]["maintenance"], 0)
        status, _, _ = self.request("POST", "/api/v1/checkpoint", {})
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
