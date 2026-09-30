import http.client
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import RequestRateLimiter, StageMeshHTTPServer, StageMeshHandler


class RateTests(unittest.TestCase):
    def make_limiter(self, **kwargs):
        self.now = 0.0
        return RequestRateLimiter(clock=lambda: self.now, peer_rate=1, peer_burst=2,
                                  total_rate=1, total_burst=3, **kwargs)

    def test_peer_limit_recovers_with_monotonic_refill(self):
        limiter = self.make_limiter()
        self.assertTrue(limiter.allow('a'))
        self.assertTrue(limiter.allow('a'))
        self.assertFalse(limiter.allow('a'))
        self.now = 1
        self.assertTrue(limiter.allow('a'))

    def test_aggregate_limit_applies_across_peers(self):
        limiter = self.make_limiter()
        self.assertTrue(all(limiter.allow(peer) for peer in ['a', 'b', 'c']))
        self.assertFalse(limiter.allow('d'))

    def test_full_identity_table_does_not_reset_depleted_buckets(self):
        limiter = self.make_limiter(max_peers=1)
        self.assertTrue(limiter.allow('a'))
        self.assertFalse(limiter.allow('b'))
        self.assertEqual(len(limiter.peers), 1)
        self.now = 2
        self.assertTrue(limiter.allow('b'))
        self.assertEqual(set(limiter.peers), {'b'})

    def test_http_rejection_closes_unread_body_and_ignores_forwarded_ip(self):
        server = StageMeshHTTPServer(('127.0.0.1', 0), StageMeshHandler)
        server.request_limiter = RequestRateLimiter(clock=lambda: 0.0, peer_rate=1, peer_burst=1)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        conn = http.client.HTTPConnection(*server.server_address, timeout=2)
        try:
            conn.request('GET', '/')
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            conn.request('POST', '/api/v1/show', body='{}', headers={
                'Content-Type': 'application/json', 'X-Forwarded-For': '192.0.2.99'})
            response = conn.getresponse()
            self.assertEqual(response.status, 429)
            self.assertEqual(response.getheader('Connection'), 'close')
            self.assertEqual(response.getheader('Retry-After'), '2')
            response.read()
        finally:
            conn.close()
            server.shutdown()
            server.server_close()
            worker.join(2)
