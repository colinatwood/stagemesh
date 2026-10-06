import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from dev_server import StageMeshHandler, StageMeshHTTPServer
from http_authorization import authorization_policy, authorize_control_request
from persistence import StateRepository


class AuthorizationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'authorization.json'

    def write(self, value):
        replacement = self.path.with_suffix('.new')
        replacement.write_text(json.dumps(value), encoding='utf-8')
        replacement.chmod(0o600)
        replacement.replace(self.path)

    def env(self):
        return {'STAGEMESH_HTTP_AUTHORIZATION_FILE': str(self.path)}

    def test_private_policy_loads_fixed_roles_and_assignments(self):
        self.write({'version': 1, 'users': {
            'alex': {'roles': ['performer'], 'players': ['alex']},
            'foh': {'roles': ['operator', 'authority']},
        }})
        policy = authorization_policy(self.env())
        self.assertEqual(policy['users']['alex']['roles'], ('performer',))
        self.assertEqual(policy['users']['alex']['players'], frozenset({'alex'}))
        self.assertEqual(policy['users']['foh']['roles'], ('authority', 'operator'))

    def test_policy_rejects_permissions_unknown_roles_and_duplicate_keys(self):
        self.write({'version': 1, 'users': {'alex': {'roles': ['operator']}}})
        self.path.chmod(0o644)
        with self.assertRaises(PermissionError):
            authorization_policy(self.env())
        self.path.chmod(0o600)
        self.write({'version': 1, 'users': {'alex': {'roles': ['superuser']}}})
        with self.assertRaises(PermissionError):
            authorization_policy(self.env())
        self.path.write_text('{"version":1,"version":1,"users":{}}', encoding='utf-8')
        self.path.chmod(0o600)
        with self.assertRaises(PermissionError):
            authorization_policy(self.env())

    def test_performer_is_limited_to_assigned_player(self):
        policy = {'version': 1, 'users': {
            'alex': {'roles': ('performer',), 'players': frozenset({'alex'})}
        }}
        allowed = authorize_control_request(policy, 'alex', 'PATCH', '/api/v1/players/alex/monitor')
        denied = authorize_control_request(policy, 'alex', 'PATCH', '/api/v1/players/sam/monitor')
        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.reason, 'assigned-performer')
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, 'player-control-not-authorized')

    def test_operator_and_authority_roles_are_separate(self):
        policy = {'version': 1, 'users': {
            'ops': {'roles': ('operator',), 'players': frozenset()},
            'ha': {'roles': ('authority',), 'players': frozenset()},
        }}
        self.assertTrue(authorize_control_request(policy, 'ops', 'POST', '/api/v1/audio/scan').allowed)
        self.assertFalse(authorize_control_request(policy, 'ops', 'POST', '/api/v1/failover/promote').allowed)
        self.assertTrue(authorize_control_request(policy, 'ha', 'POST', '/api/v1/failover/promote').allowed)
        self.assertFalse(authorize_control_request(policy, 'ha', 'POST', '/api/v1/audio/scan').allowed)

    def test_machine_and_specialized_routes_keep_existing_credentials(self):
        policy = {'version': 1, 'users': {}}
        for path in ('/api/v1/replication/apply', '/api/v1/handoff/planned/peer-ready',
                     '/api/v1/handoff/execution/shadow', '/api/v1/venue/reconciliation/report',
                     '/api/v1/technology/conformance-receipt', '/api/v1/community/session',
                     '/api/v1/community/session/revoke', '/api/v1/community/public-record/reconcile'):
            with self.subTest(path=path):
                self.assertIsNone(authorize_control_request(policy, None, 'POST', path))

    def test_unknown_or_missing_users_fail_closed(self):
        policy = {'version': 1, 'users': {}}
        missing = authorize_control_request(policy, None, 'POST', '/api/v1/audio/scan')
        unknown = authorize_control_request(policy, 'nobody', 'POST', '/api/v1/audio/scan')
        self.assertFalse(missing.allowed)
        self.assertEqual(missing.reason, 'authenticated-user-required')
        self.assertFalse(unknown.allowed)
        self.assertEqual(unknown.reason, 'user-not-authorized')


class AuthorizationHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.policy_path = root / 'authorization.json'
        self.repository = StateRepository(root / 'runtime')
        self.api_token = 'a' * 32
        self.proxy_token = 'p' * 32
        self.env = {
            'STAGEMESH_REQUIRE_API_TOKEN': '1',
            'STAGEMESH_API_TOKEN': self.api_token,
            'STAGEMESH_AUTH_PROXY_TOKEN': self.proxy_token,
            'STAGEMESH_HTTP_AUTHORIZATION_FILE': str(self.policy_path),
        }

    def write_policy(self, users):
        replacement = self.policy_path.with_suffix('.new')
        replacement.write_text(json.dumps({'version': 1, 'users': users}), encoding='utf-8')
        replacement.chmod(0o600)
        replacement.replace(self.policy_path)

    def request(self, method, path, user, body=None):
        server = StageMeshHTTPServer(('127.0.0.1', 0), StageMeshHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        conn = http.client.HTTPConnection(*server.server_address, timeout=3)
        payload = json.dumps({} if body is None else body)
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': str(len(payload.encode('utf-8'))),
            'X-StageMesh-API-Token': self.api_token,
            'X-StageMesh-Auth-Proxy-Token': self.proxy_token,
            'X-StageMesh-Authenticated-User': user,
        }
        try:
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            data = json.loads(response.read().decode('utf-8'))
            return response.status, data
        finally:
            conn.close()
            server.shutdown()
            server.server_close()
            worker.join(2)

    def test_denied_role_is_audited_before_route_execution(self):
        self.write_policy({'viewer': {'roles': ['observer']}})
        with patch.dict(os.environ, self.env, clear=True), \
             patch('dev_server.RUNTIME.repository.append_authorization_audit', side_effect=self.repository.append_authorization_audit), \
             patch('dev_server.RUNTIME.timing_plan') as timing_plan:
            status, body = self.request('POST', '/api/v1/timing/plan', 'viewer')
        self.assertEqual(status, 403)
        timing_plan.assert_not_called()
        lines = self.repository.authorization_audit_path.read_text('utf-8').splitlines()
        self.assertEqual(len(lines), 1)
        event = json.loads(lines[0])['event']
        self.assertEqual(event['actor'], 'viewer')
        self.assertEqual(event['action'], 'timing.control')
        self.assertEqual(event['decision'], 'deny')
        self.assertNotIn('path', event)
        self.assertTrue(self.repository.verify_authorization_audit()['ok'])

    def test_allowed_operator_is_audited_and_reaches_route(self):
        self.write_policy({'foh': {'roles': ['operator']}})
        with patch.dict(os.environ, self.env, clear=True), \
             patch('dev_server.RUNTIME.repository.append_authorization_audit', side_effect=self.repository.append_authorization_audit), \
             patch('dev_server.RUNTIME.timing_plan', return_value={'ok': True}) as timing_plan:
            status, body = self.request('POST', '/api/v1/timing/plan', 'foh')
        self.assertEqual(status, 200)
        self.assertEqual(body, {'ok': True})
        timing_plan.assert_called_once()
        event = json.loads(self.repository.authorization_audit_path.read_text('utf-8'))['event']
        self.assertEqual(event['decision'], 'allow')
        self.assertEqual(event['roles'], ['operator'])

    def test_policy_rotation_changes_next_request(self):
        self.write_policy({'foh': {'roles': ['operator']}})
        with patch.dict(os.environ, self.env, clear=True), \
             patch('dev_server.RUNTIME.repository.append_authorization_audit', side_effect=self.repository.append_authorization_audit), \
             patch('dev_server.RUNTIME.timing_plan', return_value={'ok': True}):
            status, _ = self.request('POST', '/api/v1/timing/plan', 'foh')
            self.assertEqual(status, 200)
            self.write_policy({'foh': {'roles': ['observer']}})
            status, _ = self.request('POST', '/api/v1/timing/plan', 'foh')
            self.assertEqual(status, 403)
        self.assertEqual(self.repository.verify_authorization_audit()['records'], 2)

    def test_keepalive_connection_reloads_role_policy(self):
        self.write_policy({'foh': {'roles': ['operator']}})
        server = StageMeshHTTPServer(('127.0.0.1', 0), StageMeshHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        conn = http.client.HTTPConnection(*server.server_address, timeout=3)
        headers = {
            'Content-Type': 'application/json',
            'X-StageMesh-API-Token': self.api_token,
            'X-StageMesh-Auth-Proxy-Token': self.proxy_token,
            'X-StageMesh-Authenticated-User': 'foh',
        }
        try:
            with patch.dict(os.environ, self.env, clear=True), \
                 patch('dev_server.RUNTIME.repository.append_authorization_audit', side_effect=self.repository.append_authorization_audit), \
                 patch('dev_server.RUNTIME.timing_plan', return_value={'ok': True}):
                conn.request('POST', '/api/v1/timing/plan', body='{}', headers=headers)
                first = conn.getresponse(); first.read()
                self.assertEqual(first.status, 200)
                self.write_policy({'foh': {'roles': ['observer']}})
                conn.request('POST', '/api/v1/timing/plan', body='{}', headers=headers)
                second = conn.getresponse(); second.read()
                self.assertEqual(second.status, 403)
        finally:
            conn.close(); server.shutdown(); server.server_close(); worker.join(2)

    def test_hash_linked_authorization_audit_detects_tampering(self):
        self.repository.append_authorization_audit({'type': 'http-authorization', 'actor': 'a', 'decision': 'allow'})
        self.repository.append_authorization_audit({'type': 'http-authorization', 'actor': 'b', 'decision': 'deny'})
        self.assertTrue(self.repository.verify_authorization_audit()['ok'])
        records = self.repository.authorization_audit_path.read_text('utf-8').splitlines()
        first = json.loads(records[0])
        first['event']['actor'] = 'tampered'
        records[0] = json.dumps(first)
        self.repository.authorization_audit_path.write_text('\n'.join(records) + '\n', encoding='utf-8')
        result = self.repository.verify_authorization_audit()
        self.assertFalse(result['ok'])
        self.assertEqual(result['line'], 1)


if __name__ == '__main__':
    unittest.main()
