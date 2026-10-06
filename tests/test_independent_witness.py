import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from witness import WitnessQuorumClient, sign_response
from witness_topology import load_witness_topology


class IndependentWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.entries = []
        for index, name in enumerate(("a", "b", "c"), start=1):
            keyring = self.root / f"witness-{name}.json"
            self._write_private_json(keyring, {
                "version": 1,
                "activeKeyId": "k1",
                "keys": {"k1": f"stagemesh-independent-witness-{name}-secret-0001"},
            })
            self.entries.append({
                "url": f"http://127.0.0.1:{8800 + index}",
                "witnessId": f"witness-{name}",
                "failureDomain": f"failure-domain-{name}",
                "keyringFile": str(keyring),
            })
        self.topology_path = self.root / "topology.json"

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _write_private_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, sort_keys=True), "utf-8")
        path.chmod(0o600)

    def _write_topology(self, **changes) -> Path:
        value = {
            "version": 1,
            "quorum": 2,
            "maxClockSkewMs": 2000,
            "allowInsecureLoopback": True,
            "witnesses": [dict(item) for item in self.entries],
        }
        value.update(changes)
        self._write_private_json(self.topology_path, value)
        return self.topology_path

    def _load(self, **changes):
        return load_witness_topology(self._write_topology(**changes))

    def _reply_factory(self, topology, *, bad_identity=(), skewed=(), wrong_key=()):
        by_url = {item["url"]: item for item in topology["witnesses"]}
        secrets = {
            item["url"]: json.loads(Path(item["keyringFile"]).read_text("utf-8"))["keys"]["k1"].encode("ascii")
            for item in topology["witnesses"]
        }

        def reply(request, **kwargs):
            base = request.full_url.rsplit("/api/v1/lease/acquire", 1)[0]
            entry = by_url[base]
            body = json.loads(request.data.decode("utf-8"))
            now_ms = int(time.time() * 1000)
            result = {
                "granted": True,
                "clusterId": body["clusterId"],
                "holderNodeId": body["nodeId"],
                "epoch": 1,
                "expiresAtUnixMs": now_ms + 5000,
                "serverUnixMs": now_ms + (10000 if base in skewed else 0),
                "witnessId": "wrong-witness" if base in bad_identity else entry["witnessId"],
                "failureDomain": entry["failureDomain"],
                "reason": "granted",
            }
            secret = secrets[base]
            if base in wrong_key:
                secret = secrets[topology["witnesses"][0]["url"]]
            signed = sign_response(result, body, "acquire", secret, key_id=body.get("keyId"))
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(signed).encode("utf-8")
            return response

        return reply

    def test_private_topology_loads_unique_identity_domain_and_keyring(self):
        topology = self._load()
        self.assertEqual(topology["quorum"], 2)
        self.assertEqual(topology["maxClockSkewMs"], 2000)
        self.assertEqual([item["witnessId"] for item in topology["witnesses"]],
                         ["witness-a", "witness-b", "witness-c"])

    def test_topology_rejects_duplicate_failure_domain_keyring_and_nonmajority(self):
        cases = []
        duplicate_domain = [dict(item) for item in self.entries]
        duplicate_domain[1]["failureDomain"] = duplicate_domain[0]["failureDomain"]
        cases.append({"witnesses": duplicate_domain})
        duplicate_key = [dict(item) for item in self.entries]
        duplicate_key[1]["keyringFile"] = duplicate_key[0]["keyringFile"]
        cases.append({"witnesses": duplicate_key})
        cases.append({"quorum": 1})
        for change in cases:
            with self.subTest(change=change), self.assertRaises(PermissionError):
                self._load(**change)

    def test_topology_rejects_world_readable_file_and_insecure_nonloopback_url(self):
        path = self._write_topology()
        path.chmod(0o644)
        with self.assertRaises(PermissionError):
            load_witness_topology(path)
        entries = [dict(item) for item in self.entries]
        entries[0]["url"] = "http://192.0.2.10:8790"
        with self.assertRaises(PermissionError):
            self._load(witnesses=entries)

    def test_independent_quorum_uses_per_witness_keys_and_identity(self):
        topology = self._load()
        client = WitnessQuorumClient([], "show", "node-a", b"", independent_topology=topology)
        with patch("witness.urlopen", side_effect=self._reply_factory(topology)):
            status = client.acquire()
        self.assertTrue(status["leaseValid"])
        self.assertTrue(status["independentMode"])
        self.assertEqual(status["quorum"], 2)
        self.assertEqual(status["independentWitnessIds"], ["witness-a", "witness-b", "witness-c"])
        self.assertEqual(status["declaredFailureDomains"], ["failure-domain-a", "failure-domain-b", "failure-domain-c"])
        self.assertFalse(status["physicalIndependenceQualified"])
        self.assertTrue(all(item["clock_skew_ms"] is not None for item in status["results"]))

    def test_one_identity_failure_is_tolerated_but_two_destroy_quorum(self):
        topology = self._load()
        urls = [item["url"] for item in topology["witnesses"]]
        client = WitnessQuorumClient([], "show", "node-a", b"", independent_topology=topology)
        with patch("witness.urlopen", side_effect=self._reply_factory(topology, bad_identity={urls[0]})):
            self.assertTrue(client.acquire()["leaseValid"])
        client = WitnessQuorumClient([], "show", "node-a", b"", independent_topology=topology)
        with patch("witness.urlopen", side_effect=self._reply_factory(topology, bad_identity={urls[0], urls[1]})):
            status = client.acquire()
        self.assertFalse(status["leaseValid"])
        self.assertEqual(sum(1 for item in status["results"] if item["granted"]), 1)

    def test_clock_skew_and_wrong_endpoint_key_cannot_count_as_votes(self):
        topology = self._load(maxClockSkewMs=500)
        urls = [item["url"] for item in topology["witnesses"]]
        client = WitnessQuorumClient([], "show", "node-a", b"", independent_topology=topology)
        with patch("witness.urlopen", side_effect=self._reply_factory(topology, skewed={urls[0]}, wrong_key={urls[1]})):
            status = client.acquire()
        self.assertFalse(status["leaseValid"])
        errors = [str(item["error"] or "") for item in status["results"]]
        self.assertTrue(any("clock skew" in item for item in errors))
        self.assertTrue(any("authentication failed" in item for item in errors))

    def test_independent_server_configuration_forbids_shared_secret_fallback(self):
        import witness_server
        with patch.object(witness_server, "INDEPENDENT_MODE", True), \
             patch.object(witness_server, "WITNESS_ID", "witness-a"), \
             patch.object(witness_server, "FAILURE_DOMAIN", "rack-a"), \
             patch.object(witness_server, "EXPLICIT_KEYRING_PATH", str(self.entries[0]["keyringFile"])), \
             patch.object(witness_server, "SECRET", b"shared"):
            self.assertIn("forbids", witness_server.independent_configuration_error())
        with patch.object(witness_server, "INDEPENDENT_MODE", True), \
             patch.object(witness_server, "WITNESS_ID", "witness-a"), \
             patch.object(witness_server, "FAILURE_DOMAIN", "rack-a"), \
             patch.object(witness_server, "EXPLICIT_KEYRING_PATH", str(self.entries[0]["keyringFile"])), \
             patch.object(witness_server, "SECRET", b""):
            self.assertIsNone(witness_server.independent_configuration_error())


if __name__ == "__main__":
    unittest.main()
