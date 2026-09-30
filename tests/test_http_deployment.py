import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from http_credentials import credential_environment
from http_deployment import (evaluate_security_headers, qualify_loopback_backend,
                             qualify_tls_edge, validate_proxy_https_profile)


SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Cache-Control", "no-store"),
    ("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'"),
]


class FakeResponse:
    def __init__(self, status, headers, body=b"{}"):
        self.status = status
        self._headers = headers
        self._body = body
    def getheaders(self):
        return list(self._headers)
    def read(self, maximum=-1):
        return self._body if maximum < 0 else self._body[:maximum]


class BackendConnection:
    def __init__(self, host, port, timeout=5):
        self.host, self.port, self.timeout = host, port, timeout
        self.request_headers = {}
    def request(self, method, path, headers=None):
        self.request_headers = dict(headers or {})
    def getresponse(self):
        h = self.request_headers
        allowed = (h.get("Host") == "stage.internal"
                   and h.get("Origin") == "https://stage.internal"
                   and h.get("X-StageMesh-API-Token") == "a" * 32)
        return FakeResponse(200 if allowed else 403, SECURITY_HEADERS)
    def close(self):
        pass


class TlsSocket:
    def version(self):
        return "TLSv1.3"


class EdgeConnection:
    def __init__(self, host, port, timeout=5, context=None):
        self.sock = TlsSocket()
    def request(self, method, path, headers=None):
        pass
    def getresponse(self):
        return FakeResponse(200, SECURITY_HEADERS + [("Strict-Transport-Security", "max-age=31536000")], b"ok")
    def close(self):
        pass


class HttpDeploymentTests(unittest.TestCase):
    def profile_env(self, root: Path):
        credentials = root / "credentials.json"
        credentials.write_text(json.dumps({
            "STAGEMESH_API_TOKEN": "a" * 32,
            "STAGEMESH_AUTH_PROXY_TOKEN": "b" * 32,
        }), encoding="utf-8")
        credentials.chmod(0o600)
        authorization = root / "authorization.json"
        authorization.write_text(json.dumps({
            "version": 1,
            "users": {"operator": {"roles": ["operator", "authority"]}},
        }), encoding="utf-8")
        authorization.chmod(0o600)
        return {
            "STAGEMESH_DEPLOYMENT_PROFILE": "proxy-https",
            "STAGEMESH_ALLOWED_HOSTS": "stage.internal",
            "STAGEMESH_ALLOWED_ORIGINS": "https://stage.internal",
            "STAGEMESH_HTTP_CREDENTIAL_FILE": str(credentials),
            "STAGEMESH_HTTP_AUTHORIZATION_FILE": str(authorization),
        }

    def test_proxy_https_profile_requires_private_credentials_and_user_roles(self):
        with tempfile.TemporaryDirectory() as raw:
            env = self.profile_env(Path(raw))
            effective = credential_environment(env)
            result = validate_proxy_https_profile("127.0.0.1", effective)
            self.assertTrue(result["active"])
            self.assertFalse(result["trustedForwardedPeerHeaders"])
            self.assertEqual(result["allowedOrigins"], ["https://stage.internal"])
            self.assertEqual(result["authorizationUsers"], 1)

    def test_proxy_https_profile_rejects_nonloopback_backend_and_http_origin(self):
        with tempfile.TemporaryDirectory() as raw:
            env = self.profile_env(Path(raw))
            effective = credential_environment(env)
            with self.assertRaisesRegex(ValueError, "loopback"):
                validate_proxy_https_profile("0.0.0.0", effective)
            effective["STAGEMESH_ALLOWED_ORIGINS"] = "http://stage.internal"
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                validate_proxy_https_profile("127.0.0.1", effective)

    def test_proxy_https_profile_is_opt_in(self):
        self.assertEqual(validate_proxy_https_profile("0.0.0.0", {}),
                         {"active": False, "profile": "development"})

    def test_security_header_evaluation_distinguishes_edge_hsts(self):
        headers = dict(SECURITY_HEADERS)
        self.assertEqual(evaluate_security_headers(headers), [])
        self.assertIn("strict-transport-security missing max-age",
                      evaluate_security_headers(headers, require_hsts=True))

    def test_backend_probe_checks_allow_and_three_denials(self):
        report = qualify_loopback_backend(
            "http://127.0.0.1:8765", "stage.internal", "https://stage.internal",
            "a" * 32, connection_factory=BackendConnection)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["authorizedStatus"], 200)
        self.assertEqual(report["invalidCredentialStatus"], 403)
        self.assertEqual(report["hostileHostStatus"], 403)
        self.assertEqual(report["hostileOriginStatus"], 403)

    def test_edge_probe_requires_verified_modern_tls_and_hsts(self):
        report = qualify_tls_edge("https://stage.internal", connection_factory=EdgeConnection)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["tlsVersion"], "TLSv1.3")
        self.assertTrue(report["certificateVerified"])


if __name__ == "__main__":
    unittest.main()
