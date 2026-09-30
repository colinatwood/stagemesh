import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import StageMeshHandler, validate_http_boundary


class HealthCommandBoundaryTests(unittest.TestCase):
    def test_remote_health_requires_api_token(self):
        env = {'STAGEMESH_API_TOKEN': 'secret'}
        with self.assertRaises(PermissionError):
            validate_http_boundary({'Host': 'localhost'}, '192.0.2.1', '/healthz', 'GET', env)
        validate_http_boundary({'Host': 'localhost', 'X-StageMesh-API-Token': 'secret'},
                               '192.0.2.1', '/healthz', 'GET', env)

    def test_proxy_health_requires_api_token(self):
        with self.assertRaises(PermissionError):
            validate_http_boundary({'Host': 'localhost'}, '127.0.0.1', '/healthz', 'GET',
                                   {'STAGEMESH_REQUIRE_API_TOKEN': '1', 'STAGEMESH_API_TOKEN': 'secret'})

    def test_local_health_stays_available_in_development(self):
        validate_http_boundary({'Host': 'localhost'}, '127.0.0.1', '/healthz', 'GET', {})

    def test_command_ids_are_not_silently_aliased(self):
        handler = object.__new__(StageMeshHandler)
        prefix = 'a' * 128
        handler.headers = {'X-StageMesh-Command-Id': prefix}
        self.assertEqual(handler._command_id(), prefix)
        for suffix in ('x', 'y'):
            handler.headers = {'X-StageMesh-Command-Id': prefix + suffix}
            with self.assertRaises(ValueError):
                handler._command_id()
        handler.headers = {'X-StageMesh-Command-Id': '  '}
        self.assertIsNone(handler._command_id())
