import http.client
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import StageMeshHTTPServer, StageMeshHandler


class EventCapacityTests(unittest.TestCase):
    def test_stream_failure_releases_slot_and_closes_connection(self):
        handler = object.__new__(StageMeshHandler)
        handler.server = Mock(_event_slots=threading.BoundedSemaphore(1))
        handler._stream_events = Mock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):
            handler._serve_events(0)
        self.assertTrue(handler.close_connection)
        self.assertTrue(handler.server._event_slots.acquire(False))

    def test_normal_stream_exit_releases_slot(self):
        handler = object.__new__(StageMeshHandler)
        handler.server = Mock(_event_slots=threading.BoundedSemaphore(1))
        handler._stream_events = Mock()
        handler._serve_events(17)
        handler._stream_events.assert_called_once_with(17)
        self.assertTrue(handler.close_connection)
        self.assertTrue(handler.server._event_slots.acquire(False))

    def test_saturated_stream_pool_preserves_http_control_capacity(self):
        entered, release = threading.Event(), threading.Event()

        class Server(StageMeshHTTPServer):
            max_connections = 3
            max_event_streams = 1

        class Handler(StageMeshHandler):
            def do_GET(self):
                if self.path == '/events':
                    self._serve_events(0)
                else:
                    self._json(200, {'control': 'available'})

            def _stream_events(self, after):
                self.send_response(200)
                self.end_headers()
                self.wfile.flush()
                entered.set()
                release.wait(3)

        server = Server(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        clients = []
        try:
            for path, status in (('/events', 200), ('/events', 503), ('/control', 200)):
                conn = http.client.HTTPConnection(*server.server_address, timeout=2)
                clients.append(conn)
                conn.request('GET', path)
                response = conn.getresponse()
                self.assertEqual(response.status, status)
                if status == 503:
                    self.assertEqual(response.getheader('Retry-After'), '5')
                    self.assertEqual(response.getheader('Connection'), 'close')
                if path == '/control':
                    self.assertIn(b'available', response.read())
                if len(clients) == 1:
                    self.assertTrue(entered.wait(1))
                else:
                    response.read()
                    conn.close()
        finally:
            release.set()
            for conn in clients:
                conn.close()
            server.shutdown()
            server.server_close()
            worker.join(2)
