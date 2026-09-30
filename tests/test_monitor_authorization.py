import sys
import unittest
import http.client
import threading
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import validate_http_boundary, MONITOR_READ_PATHS, StageMeshHTTPServer, StageMeshHandler


class MonitorAuthorizationTests(unittest.TestCase):
    def test_http_monitor_cannot_dispatch_hardware_mutation(self):
        server = StageMeshHTTPServer(('127.0.0.1', 0), StageMeshHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        conn = http.client.HTTPConnection(*server.server_address, timeout=2)
        env = {'STAGEMESH_REQUIRE_API_TOKEN': '1', 'STAGEMESH_API_TOKEN': 'control',
               'STAGEMESH_MONITOR_API_TOKEN': 'monitor'}
        try:
            with patch.dict('os.environ', env), patch('dev_server.RUNTIME.health', return_value={'healthy': True}) as health:
                conn.request('GET', '/healthz', headers={'X-StageMesh-API-Token': 'monitor'})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                health.assert_called_once()
                with patch.object(StageMeshHandler, '_read_json') as read_body:
                    conn.request('POST', '/api/v1/audio/activate', body='{}', headers={
                        'X-StageMesh-API-Token': 'monitor', 'Content-Type': 'application/json'})
                    response = conn.getresponse()
                    self.assertEqual(response.status, 403)
                    self.assertEqual(response.getheader('Connection'), 'close')
                    response.read()
                    read_body.assert_not_called()
        finally:
            conn.close()
            server.shutdown()
            server.server_close()
            worker.join(2)

    def check(self, path, method='GET', token='monitor', peer='192.0.2.1', **changes):
        env = {'STAGEMESH_API_TOKEN': 'control', 'STAGEMESH_MONITOR_API_TOKEN': 'monitor', **changes}
        validate_http_boundary({'Host': 'localhost', 'Content-Type': 'application/json',
                                'X-StageMesh-API-Token': token}, peer, path, method, env)

    def test_exact_monitor_routes_are_allowed(self):
        self.assertEqual(MONITOR_READ_PATHS, {'/healthz', '/api/v1/native', '/api/v1/node'})
        for path in MONITOR_READ_PATHS:
            self.check(path)

    def test_monitor_denied_mutations_and_unlisted_reads(self):
        for path, method in (('/api/v1/audio/activate', 'POST'), ('/api/v1/show', 'PATCH'),
                             ('/api/v1/node', 'POST'), ('/api/v1/replication/export', 'GET'),
                             ('/api/v1/state', 'GET'), ('/api/v1/node/extra', 'GET')):
            for peer in ('127.0.0.1', '192.0.2.1'):
                with self.subTest(path=path, peer=peer), self.assertRaises(PermissionError):
                    self.check(path, method, peer=peer)

    def test_control_access_preserved_and_wrong_token_denied(self):
        self.check('/api/v1/show', 'PATCH', token='control')
        with self.assertRaises(PermissionError):
            self.check('/healthz', token='wrong')

    def test_identical_monitor_control_secrets_fail_closed(self):
        for token in ('control', 'monitor'):
            with self.assertRaises(PermissionError):
                self.check('/healthz', token=token, STAGEMESH_MONITOR_API_TOKEN='control')
