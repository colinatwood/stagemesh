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
sys.path.insert(0, str(ROOT / "backend"))

from dev_server import StageMeshHandler, StageMeshHTTPServer
from persistence import StateRepository
from replication import make_envelope
from runtime import StageMeshRuntime


class SpecializedAuthorizationAuditHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repository = StateRepository(root / "audit")
        self.api = "a" * 32
        self.admin = "m" * 32
        self.adapter = "d" * 32
        self.proxy = "p" * 32
        self.policy = root / "authorization.json"
        self.policy.write_text(json.dumps({"version": 1, "users": {"human-admin": {"roles": ["admin"]}}}), "utf-8")
        self.policy.chmod(0o600)

    def env(self, **extra):
        result = {
            "STAGEMESH_REQUIRE_API_TOKEN": "1",
            "STAGEMESH_API_TOKEN": self.api,
            "STAGEMESH_ADMIN_API_TOKEN": self.admin,
            "STAGEMESH_ADAPTER_REPORT_TOKEN": self.adapter,
            "STAGEMESH_AUTH_PROXY_TOKEN": self.proxy,
            "STAGEMESH_HTTP_AUTHORIZATION_FILE": str(self.policy),
        }
        result.update(extra)
        return result

    def request(self, path, body=None, headers=None, method="POST"):
        server = StageMeshHTTPServer(("127.0.0.1", 0), StageMeshHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = http.client.HTTPConnection(*server.server_address, timeout=3)
        payload = json.dumps({} if body is None else body)
        request_headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(payload.encode())),
            "X-StageMesh-API-Token": self.api,
        }
        request_headers.update(headers or {})
        try:
            conn.request(method, path, body=payload, headers=request_headers)
            response = conn.getresponse()
            raw = response.read()
            return response.status, json.loads(raw.decode()) if raw else {}
        finally:
            conn.close(); server.shutdown(); server.server_close(); thread.join(2)

    def events(self):
        if not self.repository.authorization_audit_path.exists():
            return []
        return [json.loads(line)["event"] for line in self.repository.authorization_audit_path.read_text("utf-8").splitlines()]

    def test_admin_allow_and_deny_are_durably_audited(self):
        with patch.dict(os.environ, self.env(), clear=True), \
             patch("dev_server.RUNTIME.repository.append_authorization_audit", side_effect=self.repository.append_authorization_audit), \
             patch("dev_server.RUNTIME.community_upsert_account", return_value={"ok": True}) as action:
            status, _ = self.request("/api/v1/community/accounts", headers={"X-StageMesh-Admin-Token": self.admin})
            self.assertEqual(status, 200)
            status, _ = self.request("/api/v1/community/accounts", headers={"X-StageMesh-Admin-Token": "wrong"})
            self.assertEqual(status, 403)
        self.assertEqual(action.call_count, 1)
        events = self.events()
        self.assertEqual([event["decision"] for event in events], ["allow", "deny"])
        self.assertTrue(all(event["credentialClass"] == "admin-token" for event in events))
        self.assertTrue(all("path" not in event for event in events))
        self.assertTrue(self.repository.verify_authorization_audit()["ok"])

    def test_adapter_allow_and_deny_are_audited_before_execution(self):
        with patch.dict(os.environ, self.env(), clear=True), \
             patch("dev_server.RUNTIME.repository.append_authorization_audit", side_effect=self.repository.append_authorization_audit), \
             patch("dev_server.RUNTIME.report_shadow_prebuffer", return_value={"ok": True}) as action:
            status, _ = self.request("/api/v1/handoff/execution/shadow", headers={"X-StageMesh-Adapter-Token": self.adapter})
            self.assertEqual(status, 200)
            status, _ = self.request("/api/v1/handoff/execution/shadow", headers={"X-StageMesh-Adapter-Token": "wrong"})
            self.assertEqual(status, 403)
        self.assertEqual(action.call_count, 1)
        events = self.events()
        self.assertEqual([event["decision"] for event in events], ["allow", "deny"])
        self.assertTrue(all(event["credentialClass"] == "adapter-token" for event in events))

    def test_human_admin_role_does_not_inherit_adapter_credential(self):
        env = self.env(STAGEMESH_ADAPTER_REPORT_TOKEN="")
        headers = {
            "X-StageMesh-Auth-Proxy-Token": self.proxy,
            "X-StageMesh-Authenticated-User": "human-admin",
        }
        with patch.dict(os.environ, env, clear=True), \
             patch("dev_server.RUNTIME.repository.append_authorization_audit", side_effect=self.repository.append_authorization_audit), \
             patch("dev_server.RUNTIME.report_shadow_prebuffer") as action:
            status, _ = self.request("/api/v1/handoff/execution/shadow", headers=headers)
        self.assertEqual(status, 403)
        action.assert_not_called()
        event = self.events()[0]
        self.assertEqual(event["credentialClass"], "loopback-adapter")
        self.assertEqual(event["decision"], "deny")

    def test_machine_hmac_hook_is_audited_without_raw_payload(self):
        def apply(body, authorization_hook=None):
            authorization_hook(True, "replication-hmac-verified", {"actor": "primary-a", "keyId": "2026-09-b"})
            return {"ok": True}
        with patch.dict(os.environ, self.env(), clear=True), \
             patch("dev_server.RUNTIME.repository.append_authorization_audit", side_effect=self.repository.append_authorization_audit), \
             patch("dev_server.RUNTIME.apply_replica", side_effect=apply):
            status, _ = self.request("/api/v1/replication/apply", body={"secretLookingField": "never-audited"})
        self.assertEqual(status, 200)
        event = self.events()[0]
        self.assertEqual(event["action"], "machine.replication.apply")
        self.assertEqual(event["actor"], "primary-a")
        self.assertEqual(event["keyId"], "2026-09-b")
        self.assertNotIn("secretLookingField", json.dumps(event))

    def test_audit_unavailable_blocks_specialized_action(self):
        with patch.dict(os.environ, self.env(), clear=True), \
             patch("dev_server.RUNTIME.repository.append_authorization_audit", side_effect=OSError("disk full")), \
             patch("dev_server.RUNTIME.community_upsert_account") as action:
            status, body = self.request("/api/v1/community/accounts", headers={"X-StageMesh-Admin-Token": self.admin})
        self.assertEqual(status, 503)
        self.assertIn("authorization audit unavailable", body["error"])
        action.assert_not_called()


class MachineAuthorizationRuntimeTests(unittest.TestCase):
    def test_replication_hook_runs_after_hmac_verification_before_mutation(self):
        secret = "r" * 40
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {"STAGEMESH_REPLICATION_SECRET": secret}, clear=True):
            runtime = StageMeshRuntime(Path(raw))
            try:
                runtime.replication.set_role("standby")
                snapshot = runtime.state.replication_snapshot()
                envelope = make_envelope(snapshot, node_id="primary-a", epoch=2, sequence=1, secret=secret.encode())
                seen = []
                original = runtime.state.apply_replica_snapshot
                def apply(value):
                    self.assertEqual(seen[0][0], True)
                    return original(value)
                with patch.object(runtime.state, "apply_replica_snapshot", side_effect=apply):
                    runtime.apply_replica(envelope, authorization_hook=lambda *args: seen.append(args))
                self.assertEqual(seen[0][1], "replication-hmac-verified")
                tampered = {**envelope, "hmacSha256": "0" * 64}
                denied = []
                with self.assertRaises(ValueError):
                    runtime.apply_replica(tampered, authorization_hook=lambda *args: denied.append(args))
                self.assertEqual(denied[0][0], False)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
