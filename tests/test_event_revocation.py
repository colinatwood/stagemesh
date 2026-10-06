import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import StageMeshHandler


class EventRevocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'credentials.json'
        self.replace('a' * 32)
        self.handler = object.__new__(StageMeshHandler)
        self.handler._credential_snapshot = {'STAGEMESH_HTTP_CREDENTIAL_FILE': str(self.path)}
        self.handler.headers = {'Host': 'localhost', 'X-StageMesh-API-Token': 'a' * 32}
        self.handler.client_address = ('127.0.0.1', 1234)
        self.handler.path = '/api/v1/events?after=0'
        self.handler.wfile = io.BytesIO()
        self.handler.server = Mock(_event_slots=threading.BoundedSemaphore(1))
        for name in ('send_response', 'send_header', '_security_headers', 'end_headers'):
            setattr(self.handler, name, Mock())

    def replace(self, token):
        temporary = self.path.with_suffix('.new')
        temporary.write_text(json.dumps({'STAGEMESH_API_TOKEN': token}))
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def test_rotation_during_wait_drops_fetched_batch_and_releases_slot(self):
        def wait(*args, **kwargs):
            self.assertEqual(kwargs['timeout'], 1.0)
            self.replace('b' * 32)
            return [{'eventId': 1, 'revision': 1, 'secret': 'never send'}]
        with patch('dev_server.RUNTIME.state.wait_for_events', side_effect=wait):
            self.handler._serve_events(0)
        self.assertEqual(self.handler.wfile.getvalue(), b'')
        self.assertTrue(self.handler.close_connection)
        self.assertTrue(self.handler.server._event_slots.acquire(False))
        self.handler.send_response.assert_called_once_with(200)

    def test_invalid_file_during_idle_wait_closes_without_heartbeat(self):
        def wait(*args, **kwargs):
            self.path.write_text('invalid')
            return []
        with patch('dev_server.RUNTIME.state.wait_for_events', side_effect=wait):
            self.handler._serve_events(0)
        self.assertEqual(self.handler.wfile.getvalue(), b'')
        self.assertTrue(self.handler.close_connection)

    def test_unchanged_credentials_deliver_events_and_keepalive(self):
        with patch('dev_server.RUNTIME.state.wait_for_events', side_effect=[
                [{'eventId': 7, 'revision': 2}], [], BrokenPipeError()]):
            self.handler._serve_events(0)
        data = self.handler.wfile.getvalue()
        self.assertIn(b'id: 7\nevent: stagemesh', data)
        self.assertIn(b': keepalive', data)
        self.assertTrue(self.handler.close_connection)
