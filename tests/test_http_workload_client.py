import importlib.util
from pathlib import Path
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "stagemesh_http_workload", ROOT / "scripts" / "stagemesh-http-workload.py"
)
workload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workload)


class _Response:
    def __init__(self, status):
        self.status = status

    def read(self):
        return b""


class _Connection:
    instances = []
    lock = threading.Lock()

    def __init__(self, host, port, timeout):
        self.requests = 0
        self.closed = False
        with self.lock:
            self.instances.append(self)

    def request(self, method, path, body=None, headers=None):
        self.requests += 1

    def getresponse(self):
        return _Response(429 if self.requests % 3 == 0 else 200)

    def close(self):
        self.closed = True


class HttpWorkloadClientTests(unittest.TestCase):
    def setUp(self):
        _Connection.instances = []

    def test_parallel_client_reuses_one_connection_per_bounded_worker(self):
        with patch.object(workload.http.client, "HTTPConnection", _Connection):
            results = workload._run_parallel(1234, count=23, concurrency=4, abuse=True)
        self.assertEqual(len(results), 23)
        self.assertEqual(len(_Connection.instances), 4)
        self.assertEqual(sum(item.requests for item in _Connection.instances), 23)
        self.assertTrue(all(item.closed for item in _Connection.instances))
        self.assertEqual(sum(item["status"] == 429 for item in results), 7)

    def test_worker_count_never_exceeds_request_count(self):
        with patch.object(workload.http.client, "HTTPConnection", _Connection):
            results = workload._run_parallel(1234, count=3, concurrency=8, abuse=True)
        self.assertEqual(len(results), 3)
        self.assertEqual(len(_Connection.instances), 3)

    def test_live_summary_requires_observed_throttling_and_no_transport_errors(self):
        no_throttle = workload._summarize_observation(
            [{"status": 200, "latencyMs": 1.0}] * 4,
            2.0, {200, 429}, require_throttle=True,
        )
        self.assertFalse(no_throttle["passed"])
        self.assertEqual(no_throttle["observationStatus"], "no-throttling-observed")
        self.assertEqual(no_throttle["completedRequestsPerSecond"], 2.0)

        observed = workload._summarize_observation(
            [{"status": 200, "latencyMs": 1.0}, {"status": 429, "latencyMs": 2.0}],
            0.5, {200, 429}, require_throttle=True,
        )
        self.assertTrue(observed["passed"])
        self.assertEqual(observed["throttled"], 1)
        self.assertEqual(observed["observationStatus"], "throttling-observed")

        transport_error = workload._summarize_observation(
            [{"status": 429, "latencyMs": 1.0},
             {"status": None, "latencyMs": 5.0, "error": "TimeoutError"}],
            1.0, {200, 429}, require_throttle=True,
        )
        self.assertFalse(transport_error["passed"])
        self.assertEqual(transport_error["unexpected"], 1)


if __name__ == "__main__":
    unittest.main()
