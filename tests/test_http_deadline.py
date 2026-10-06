import socket
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import StageMeshHTTPServer, StageMeshHandler


class DeadlineTests(unittest.TestCase):
    def run_trickle(self, prefix):
        class Server(StageMeshHTTPServer):
            request_read_timeout = 0.2
            socket_timeout = 1.0

        class Handler(StageMeshHandler):
            reached = False

            def do_POST(self):
                self._read_json()
                Handler.reached = True

        server = Server(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with socket.create_connection(server.server_address, timeout=2) as client:
                client.sendall(prefix)
                ended = threading.Event()

                def trickle():
                    while not ended.wait(0.025):
                        try:
                            client.sendall(b' ')
                        except OSError:
                            return

                sender = threading.Thread(target=trickle)
                sender.start()
                start = time.monotonic()
                try:
                    self.assertEqual(client.recv(1), b'')
                    self.assertLess(time.monotonic() - start, 0.9)
                    self.assertFalse(Handler.reached)
                finally:
                    ended.set()
                    sender.join(1)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)

    def test_trickled_headers_cannot_extend_total_deadline(self):
        self.run_trickle(b'POST / HTTP/1.1\r\nHost: localhost\r\nX-Slow: ')

    def test_trickled_body_cannot_extend_total_deadline(self):
        self.run_trickle(b'POST / HTTP/1.1\r\nHost: localhost\r\nContent-Length: 1000\r\n\r\n{')
