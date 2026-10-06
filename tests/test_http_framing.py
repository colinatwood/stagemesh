import socket
import sys
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import StageMeshHandler


class FramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), StageMeshHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def exchange(self, request):
        with socket.create_connection(self.server.server_address, timeout=2) as sock:
            sock.sendall(request)
            sock.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                part = sock.recv(65536)
                if not part:
                    return b''.join(chunks)
                chunks.append(part)

    def test_rejected_framing_closes_before_pipeline_dispatch(self):
        for headers in (b'Content-Length: 2\r\nContent-Length: 2\r\n',
                        b'Transfer-Encoding: chunked\r\n',
                        b'Content-Length: +2\r\n', b'Host: localhost\r\n',
                        b'Content-Length: ' + b'9' * 5000 + b'\r\n'):
            with self.subTest(headers=headers):
                reply = self.exchange(b'POST /api/v1/show HTTP/1.1\r\nHost: localhost\r\n' + headers +
                                      b'Content-Type: application/json\r\n\r\n{}GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
                self.assertIn(b'400 Bad Request', reply)
                self.assertIn(b'Connection: close', reply)
                self.assertEqual(reply.count(b'HTTP/1.1 '), 1)

    def test_boundary_rejection_closes_unread_body(self):
        reply = self.exchange(b'POST /api/v1/show HTTP/1.1\r\nHost: attacker.example\r\nContent-Length: 2\r\n\r\n{}GET / HTTP/1.1\r\nHost: localhost\r\n\r\n')
        self.assertIn(b'403 Forbidden', reply)
        self.assertEqual(reply.count(b'HTTP/1.1 '), 1)

    def test_expect_is_rejected_without_interim_continue(self):
        reply = self.exchange(b'POST /api/v1/show HTTP/1.1\r\nHost: localhost\r\nExpect: 100-continue\r\nContent-Length: 2\r\n\r\n')
        self.assertIn(b'417 Expectation Failed', reply)
        self.assertNotIn(b'100 Continue', reply)

    def test_get_body_is_rejected(self):
        reply = self.exchange(b'GET / HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}')
        self.assertIn(b'400 Bad Request', reply)

    def test_duplicate_security_headers_are_rejected(self):
        for name in ('Origin', 'Content-Type', 'X-StageMesh-API-Token',
                     'X-StageMesh-Desktop-Token',
                     'X-StageMesh-Admin-Token', 'X-StageMesh-Adapter-Token',
                     'X-StageMesh-Authenticated-User', 'X-StageMesh-Auth-Proxy-Token',
                     'X-StageMesh-Command-Id'):
            with self.subTest(name=name):
                fields = f'{name}: first\r\n{name}: second\r\n'.encode()
                reply = self.exchange(b'GET / HTTP/1.1\r\nHost: localhost\r\n' + fields + b'\r\n')
                self.assertIn(b'400 Bad Request', reply)

    def test_truncated_json_is_rejected(self):
        reply = self.exchange(b'POST /api/v1/show HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 10\r\n\r\n{}')
        self.assertIn(b'incomplete request body', reply)

    def test_valid_keepalive_pipeline_remains_supported(self):
        reply = self.exchange(b'GET / HTTP/1.1\r\nHost: localhost\r\n\r\nGET /styles.css HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        self.assertEqual(reply.count(b'HTTP/1.1 200 OK'), 2)
