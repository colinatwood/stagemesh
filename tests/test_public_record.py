import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from public_record import PublicRecordStore, make_witness_attestation
from runtime import StageForgeRuntime


class PublicRecordStoreTests(unittest.TestCase):
    def _policy(self, root: Path, secret: str = "w" * 40) -> Path:
        path = root / "public-record-witnesses.json"
        path.write_text(json.dumps({"version": 1, "quorum": 1, "witnesses": {"witness-a": secret}}), "utf-8")
        os.chmod(path, 0o600)
        return path

    def test_signed_chain_detects_payload_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = PublicRecordStore(root / "public-record.jsonl", signer_id="node-a", signing_secret=b"s" * 32)
            first = store.append("venue-adaptation", {"transactionId": "tx-1", "intentPreserved": True})
            second = store.append("authority-lease-grant", {"leaseId": "lease-1", "scope": "audio"})
            status = store.verify()
            self.assertTrue(status["ok"]); self.assertEqual(status["records"], 2); self.assertEqual(status["head"], second["recordHash"])
            lines = (root / "public-record.jsonl").read_text("utf-8").splitlines()
            row = json.loads(lines[0]); row["payload"]["intentPreserved"] = False
            lines[0] = json.dumps(row, sort_keys=True, separators=(",", ":"))
            (root / "public-record.jsonl").write_text("\n".join(lines) + "\n", "utf-8")
            tampered = store.verify()
            self.assertFalse(tampered["ok"]); self.assertIn("hash", tampered["error"])

    def test_external_witness_attestation_is_authenticated_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); secret = "external-witness-secret-" + "x" * 20
            policy = self._policy(root, secret)
            store = PublicRecordStore(root / "public-record.jsonl", signer_id="node-a", signing_secret=b"s" * 32, witness_policy_path=policy)
            record = store.append("venue-adaptation", {"transactionId": "tx-1"})
            attestation = make_witness_attestation(record["recordHash"], "witness-a", secret.encode("utf-8"), issued_at_ns=123456789)
            accepted = store.attest(attestation)
            self.assertTrue(accepted["accepted"]); self.assertFalse(accepted["deduplicated"])
            replay = store.attest(attestation); self.assertTrue(replay["deduplicated"])
            status = store.verify()
            self.assertTrue(status["ok"]); self.assertTrue(status["allRecordsWitnessed"]); self.assertEqual(status["witnessRecords"], 1)
            bad = dict(attestation); bad["hmacSha256"] = "0" * 64
            with self.assertRaises(PermissionError): store.attest(bad)

    def test_private_witness_policy_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); policy = self._policy(root); os.chmod(policy, 0o644)
            with self.assertRaises(PermissionError):
                PublicRecordStore(root / "public-record.jsonl", signer_id="node-a", signing_secret=b"s" * 32, witness_policy_path=policy)

    def test_stable_reference_resolves_only_after_signed_chain_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = PublicRecordStore(root / "public-record.jsonl", signer_id="node-a", signing_secret=b"s" * 32)
            ref = store.append("technology-conformance", {"version": 1, "extensionId": "upp.test.v1", "evidenceDigestSha256": "a" * 64})
            uri = store.reference_uri(ref)
            record = store.resolve_reference(uri, record_type="technology-conformance")
            self.assertEqual(record["recordId"], ref["recordId"]); self.assertEqual(record["hash"], ref["recordHash"])
            with self.assertRaises(ValueError):
                store.resolve_reference(uri, record_type="venue-adaptation")
            lines = store.path.read_text("utf-8").splitlines(); row = json.loads(lines[0]); row["payload"]["extensionId"] = "upp.tampered.v1"
            store.path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
            with self.assertRaises(OSError):
                store.resolve_reference(uri, record_type="technology-conformance")


class PublicRecordRuntimeTests(unittest.TestCase):
    def _venue(self):
        return {
            "documentType": "org.upp.venue-profile", "schemaVersion": 1,
            "id": "record-venue", "name": "Record Venue", "capabilities": ["audio.transport", "authority.fence"],
            "devices": [{"id": "audio-a", "status": "expected", "capabilities": ["audio.output.multi", "audio.input.capture", "audio.monitor"], "latency": {"fixedMs": 5, "jitterMs": 1, "timestamped": True}}],
            "patch": {
                "audio.foh": {"target": "audio-a:out-1-2", "authority": "foh"},
                "audio.live-input": {"target": "audio-a:in-1-4"},
                "audio.monitor": {"target": "audio-a:out-3-6"},
            },
        }

    def test_adaptation_receipt_is_signed_persisted_and_externally_witnessable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); secret = "external-witness-secret-" + "z" * 20
            policy_path = root / "witness-policy.json"
            policy_path.write_text(json.dumps({"version": 1, "quorum": 1, "witnesses": {"witness-a": secret}}), "utf-8"); os.chmod(policy_path, 0o600)
            env = {"STAGEMESH_NATIVE_ENGINE": "off", "STAGEFORGE_PUBLIC_RECORD_WITNESS_FILE": str(policy_path)}
            with patch.dict("os.environ", env, clear=False):
                runtime = StageForgeRuntime(root / "runtime")
                try:
                    runtime.save_venue_profile(self._venue())
                    tx = runtime.venue_adaptation_propose({})
                    runtime.venue_adaptation_validate(tx["transactionId"])
                    committed = runtime.venue_adaptation_commit(tx["transactionId"], {"mode": "immediate", "requestedBy": "stage-manager"})
                    ref = committed["receipt"]["publicRecord"]
                    persisted = runtime.venue_adaptation_get(tx["transactionId"])
                    self.assertEqual(persisted["receipt"]["publicRecord"]["recordHash"], ref["recordHash"])
                    status = runtime.public_record_status(); self.assertTrue(status["ok"]); self.assertEqual(status["records"], 1); self.assertFalse(status["allRecordsWitnessed"])
                    attestation = make_witness_attestation(ref["recordHash"], "witness-a", secret.encode("utf-8"), issued_at_ns=987654321)
                    result = runtime.public_record_attest(attestation)
                    self.assertTrue(result["attestation"]["accepted"]); self.assertTrue(result["publicRecord"]["allRecordsWitnessed"])
                finally:
                    runtime.close()

    def test_authority_grant_and_revoke_return_public_record_references(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", {"STAGEMESH_NATIVE_ENGINE": "off", "STAGEFORGE_PUBLIC_RECORD_WITNESS_FILE": ""}, clear=False):
            runtime = StageForgeRuntime(Path(tmp))
            try:
                grant = runtime.venue_authority_grant({"scopeKind": "resource", "scope": "lighting-network", "grantee": "lighting", "ttlSeconds": 60})
                self.assertEqual(grant["publicRecord"]["sequence"], 1)
                revoked = runtime.venue_authority_revoke(grant["leaseId"], {"requestedBy": "stage-manager"})
                self.assertEqual(revoked["publicRecord"]["sequence"], 2)
                self.assertEqual(runtime.public_record_status()["records"], 2)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
