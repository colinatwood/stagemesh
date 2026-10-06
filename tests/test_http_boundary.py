import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from dev_server import validate_http_boundary


class HttpBoundaryTests(unittest.TestCase):
    def test_origin_scheme_requires_explicit_tls_proxy_allowlist(self):
        headers = {"Host": "localhost:8787", "Origin": "https://localhost:8787"}
        with self.assertRaises(PermissionError):
            validate_http_boundary(headers, "127.0.0.1", "/api/v1/state", "GET", {})
        validate_http_boundary(headers, "127.0.0.1", "/api/v1/state", "GET",
                               {"STAGEMESH_ALLOWED_ORIGINS": "https://localhost:8787"})

    def test_authorities_and_origins_reject_url_components(self):
        for host in ("user@localhost", "localhost/path", "localhost?query", "localhost#fragment"):
            with self.subTest(host=host), self.assertRaises(PermissionError):
                validate_http_boundary({"Host": host}, "127.0.0.1", "/", "GET", {})
        for origin in ("http://user@localhost", "http://localhost/path", "http://localhost?q", "http://localhost#f"):
            with self.subTest(origin=origin), self.assertRaises(PermissionError):
                validate_http_boundary({"Host": "localhost", "Origin": origin}, "127.0.0.1", "/", "GET", {})

    def test_loopback_same_origin_api_request_is_allowed(self):
        validate_http_boundary({"Host":"127.0.0.1:8787","Origin":"http://127.0.0.1:8787","Content-Type":"application/json"},"127.0.0.1","/api/v1/profile","POST",{})

    def test_dns_rebinding_host_and_cross_origin_are_rejected(self):
        with self.assertRaisesRegex(PermissionError,"Host"):validate_http_boundary({"Host":"attacker.example"},"127.0.0.1","/api/v1/state","GET",{})
        with self.assertRaisesRegex(PermissionError,"Origin"):validate_http_boundary({"Host":"localhost:8787","Origin":"https://attacker.example","Content-Type":"application/json"},"127.0.0.1","/api/v1/profile","POST",{})
        with self.assertRaisesRegex(PermissionError,"Origin"):validate_http_boundary({"Host":"localhost:8787","Origin":"null","Content-Type":"application/json"},"127.0.0.1","/api/v1/profile","POST",{})

    def test_remote_api_requires_configured_constant_time_token_path(self):
        request={"Host":"stage.internal","Content-Type":"application/json"}
        env={"STAGEMESH_ALLOWED_HOSTS":"stage.internal","STAGEMESH_API_TOKEN":"secret"}
        with self.assertRaisesRegex(PermissionError,"authentication"):validate_http_boundary(request,"10.0.0.8","/api/v1/profile","POST",env)
        validate_http_boundary({**request,"X-StageMesh-API-Token":"secret"},"10.0.0.8","/api/v1/profile","POST",env)

    def test_remote_static_content_does_not_receive_api_authority(self):
        validate_http_boundary({"Host":"stage.internal"},"10.0.0.8","/app.js","GET",{"STAGEMESH_ALLOWED_HOSTS":"stage.internal"})

    def test_proxy_mode_can_require_token_even_from_loopback(self):
        env={"STAGEMESH_REQUIRE_API_TOKEN":"1","STAGEMESH_API_TOKEN":"secret"}
        with self.assertRaisesRegex(PermissionError,"authentication"):validate_http_boundary({"Host":"localhost"},"127.0.0.1","/api/v1/state","GET",env)
        validate_http_boundary({"Host":"localhost","X-StageMesh-API-Token":"secret"},"127.0.0.1","/api/v1/state","GET",env)

    def test_mutation_rejects_non_json_content_type(self):
        with self.assertRaisesRegex(ValueError,"Content-Type"):validate_http_boundary({"Host":"localhost:8787","Content-Type":"text/plain"},"127.0.0.1","/api/v1/profile","POST",{})

    def test_non_loopback_startup_requires_host_allowlist_and_token(self):
        env=os.environ.copy();env.pop("STAGEMESH_ALLOWED_HOSTS",None);env.pop("STAGEMESH_API_TOKEN",None)
        result=subprocess.run([sys.executable,str(ROOT/"backend/dev_server.py"),"--host","0.0.0.0","--port","0"],cwd=ROOT,env=env,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,2);self.assertIn("non-loopback binding requires",result.stderr)


if __name__=="__main__":unittest.main()
