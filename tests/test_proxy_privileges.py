import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import StageMeshHandler, token_matches


class ProxyPrivilegeTests(unittest.TestCase):
    def test_non_ascii_tokens_deny_without_type_error(self):
        self.assertFalse(token_matches('secret', 'secrét'))
        self.assertFalse(token_matches('secrét', 'secrét'))
        self.assertTrue(token_matches('secret', 'secret'))

    def test_oversized_proxy_identity_is_not_truncated_to_another_account(self):
        with patch.dict('os.environ', {'STAGEMESH_AUTH_PROXY_TOKEN': 'proxy'}, clear=True):
            handler = self.handler({'X-StageMesh-Authenticated-User': 'a' * 129,
                                    'X-StageMesh-Auth-Proxy-Token': 'proxy'})
            with self.assertRaises(PermissionError):
                handler._authenticated_user_id()

    def handler(self, headers=None):
        handler = object.__new__(StageMeshHandler)
        handler.client_address = ('127.0.0.1', 1234)
        handler.headers = headers or {}
        return handler

    def test_proxy_api_credential_does_not_grant_narrow_privileges(self):
        for value in ('1', 'true', 'YES', ' on '):
            with self.subTest(value=value), patch.dict('os.environ', {'STAGEMESH_REQUIRE_API_TOKEN': value}, clear=True):
                handler = self.handler({'X-StageMesh-API-Token': 'general'})
                for check in (handler._require_admin_auth, handler._require_adapter_report_auth):
                    with self.assertRaises(PermissionError):
                        check()

    def test_proxy_requires_correct_separate_credentials(self):
        env = {'STAGEMESH_REQUIRE_API_TOKEN': '1', 'STAGEMESH_ADMIN_API_TOKEN': 'admin',
               'STAGEMESH_ADAPTER_REPORT_TOKEN': 'adapter'}
        with patch.dict('os.environ', env, clear=True):
            good = self.handler({'X-StageMesh-Admin-Token': 'admin', 'X-StageMesh-Adapter-Token': 'adapter'})
            good._require_admin_auth()
            good._require_adapter_report_auth()
            bad = self.handler({'X-StageMesh-Admin-Token': 'adapter', 'X-StageMesh-Adapter-Token': 'admin'})
            for check in (bad._require_admin_auth, bad._require_adapter_report_auth):
                with self.assertRaises(PermissionError):
                    check()

    def test_local_development_exemption_remains_explicit(self):
        with patch.dict('os.environ', {}, clear=True):
            handler = self.handler()
            handler._require_admin_auth()
            handler._require_adapter_report_auth()
