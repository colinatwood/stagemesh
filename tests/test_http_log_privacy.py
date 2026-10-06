import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from dev_server import StageMeshHandler


class LogPrivacyTests(unittest.TestCase):
    def test_access_log_omits_url_credentials_and_peer(self):
        handler = object.__new__(StageMeshHandler)
        handler.command = 'GET'
        handler.requestline = 'GET /vote?token=secret HTTP/1.1'
        handler.client_address = ('192.0.2.77', 1234)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            handler.log_request(200, 50)
        self.assertEqual(json.loads(output.getvalue()), {'component': 'http', 'method': 'GET', 'status': 200})

    def test_malformed_request_diagnostics_do_not_echo_input(self):
        handler = object.__new__(StageMeshHandler)
        handler.command = 'secret\nforged log'
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            handler.log_message('Bad request %s', 'secret\nforged log')
            handler.log_request(400)
        self.assertNotIn('secret', output.getvalue())
        self.assertNotIn('forged', output.getvalue())
        self.assertEqual(len(output.getvalue().splitlines()), 2)
