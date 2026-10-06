import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from adapters import AdapterRegistry
from persistence import StateRepository
from runtime import StageMeshRuntime
from replication import ReplicationTracker, make_envelope, verify_envelope
from planned_handoff import make_offer, make_ready_receipt, verify_offer, verify_ready_receipt


class PersistenceTests(unittest.TestCase):
    def test_snapshot_roundtrip_and_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = StateRepository(Path(tmp))
            snapshot = {"revision": 4, "transport": {"running": False}}
            repo.save_snapshot(snapshot)
            self.assertEqual(repo.load_snapshot(), snapshot)
            repo.append_event({"eventId": 1, "revision": 4, "text": "one"})
            repo.append_event({"eventId": 2, "revision": 5, "text": "two"})
            result = repo.verify_ledger()
            self.assertTrue(result["ok"])
            self.assertEqual(result["records"], 2)

    def test_ledger_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = StateRepository(Path(tmp))
            repo.append_event({"eventId": 1, "revision": 1, "text": "original"})
            line = json.loads(repo.ledger_path.read_text("utf-8"))
            line["event"]["text"] = "tampered"
            repo.ledger_path.write_text(json.dumps(line) + "\n", "utf-8")
            self.assertFalse(repo.verify_ledger()["ok"])


class PlannedHandoffProtocolTests(unittest.TestCase):
    def test_ready_receipt_is_offer_bound_authenticated_and_tamper_evident(self):
        secret = b"ready-secret"
        offer = make_offer(transaction_id=92, source_node_id="primary-a", target_node_id="standby-b",
                           source_epoch=7, target_epoch=8, target_show_ns=99,
                           allow_degraded_program=False, secret=secret)
        receipt = make_ready_receipt(offer=offer, program_ready=True, secret=secret)
        self.assertEqual(verify_ready_receipt(receipt, secret=secret,
                                             expected_source_node_id="primary-a", offer=offer),
                         (True, "ok"))
        tampered = json.loads(json.dumps(receipt))
        tampered["programReady"] = False
        self.assertFalse(verify_ready_receipt(tampered, secret=secret,
                                              expected_source_node_id="primary-a", offer=offer)[0])
        malformed = json.loads(json.dumps(receipt))
        malformed["programReady"] = "false"
        self.assertFalse(verify_ready_receipt(malformed, secret=secret,
                                              expected_source_node_id="primary-a", offer=offer)[0])

    def test_offer_is_target_bound_authenticated_and_tamper_evident(self):
        secret = b"planned-handoff-secret"
        offer = make_offer(transaction_id=91, source_node_id="primary-a", target_node_id="standby-b",
                           source_epoch=7, target_epoch=8, target_show_ns=12_000_000_000,
                           allow_degraded_program=False, secret=secret)
        self.assertEqual(verify_offer(offer, secret=secret, expected_target_node_id="standby-b"), (True, "ok"))
        self.assertFalse(verify_offer(offer, secret=secret, expected_target_node_id="standby-c")[0])
        tampered = json.loads(json.dumps(offer))
        tampered["targetShowNs"] += 1
        self.assertFalse(verify_offer(tampered, secret=secret, expected_target_node_id="standby-b")[0])

    def test_offer_refuses_missing_auth_and_nonadvancing_epoch(self):
        with self.assertRaises(RuntimeError):
            make_offer(transaction_id=1, source_node_id="a", target_node_id="b", source_epoch=1,
                       target_epoch=2, target_show_ns=1, allow_degraded_program=False, secret=b"")
        with self.assertRaises(ValueError):
            make_offer(transaction_id=1, source_node_id="a", target_node_id="b", source_epoch=2,
                       target_epoch=2, target_show_ns=1, allow_degraded_program=False, secret=b"x")


class AdapterTests(unittest.TestCase):
    def test_safe_mode_preserves_critical_work(self):
        plan = AdapterRegistry().plan(45, "safe")
        decisions = {item["id"]: item for item in plan["decisions"]}
        self.assertNotEqual(decisions["audio-core"]["status"], "off")
        self.assertNotEqual(decisions["midi-bridge"]["status"], "off")
        self.assertEqual(decisions["ai-connector"]["status"], "off")
        self.assertEqual(decisions["visualizer"]["status"], "off")


class ReplicationTests(unittest.TestCase):
    def test_envelope_digest_and_hmac_detect_tampering(self):
        snapshot = {"apiVersion": 1, "revision": 7, "transport": {"running": False}}
        secret = b"shared-test-secret"
        envelope = make_envelope(snapshot, node_id="primary-a", epoch=2, sequence=4, secret=secret)
        self.assertEqual(verify_envelope(envelope, secret=secret), (True, "ok"))
        tampered = json.loads(json.dumps(envelope))
        tampered["snapshot"]["revision"] = 8
        ok, reason = verify_envelope(tampered, secret=secret)
        self.assertFalse(ok)
        self.assertIn("digest", reason)


    def test_v2_replication_signs_execution_telemetry(self):
        snapshot = {"apiVersion": 1, "revision": 9, "transport": {"running": True, "seconds": 12.5}}
        secret = b"telemetry-secret"
        telemetry = {
            "showTimeNs": 12_500_000_000,
            "audioOutputs": [{"slot": 0, "lastBlockEndShowNs": 12_490_000_000}],
            "activeAudioInputSlots": [],
        }
        envelope = make_envelope(
            snapshot, node_id="primary-a", epoch=4, sequence=8, secret=secret, execution_telemetry=telemetry
        )
        self.assertEqual(envelope["protocolVersion"], 2)
        self.assertEqual(verify_envelope(envelope, secret=secret), (True, "ok"))
        tampered = json.loads(json.dumps(envelope))
        tampered["executionTelemetry"]["audioOutputs"][0]["lastBlockEndShowNs"] += 1_000_000
        ok, reason = verify_envelope(tampered, secret=secret)
        self.assertFalse(ok)
        self.assertIn("digest", reason)

    def test_tracker_fences_standby_ordering(self):
        snapshot = {"apiVersion": 1, "revision": 3}
        primary = ReplicationTracker("primary", "primary")
        standby = ReplicationTracker("standby", "standby")
        envelope = primary.export(snapshot)
        self.assertTrue(standby.can_apply(envelope).accepted)
        standby.mark_applied(envelope)
        self.assertFalse(standby.can_apply(envelope).accepted)
        with self.assertRaises(RuntimeError):
            standby.export(snapshot)

class RuntimeTests(unittest.TestCase):
    def test_command_id_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            first_revision = runtime.state.revision
            result1, duplicate1 = runtime.mutate("same-command", lambda: runtime.state.patch_show({"bpm": 130}, first_revision))
            result2, duplicate2 = runtime.mutate("same-command", lambda: runtime.state.patch_show({"bpm": 200}, result1["revision"]))
            self.assertFalse(duplicate1)
            self.assertTrue(duplicate2)
            self.assertEqual(result2["transport"]["bpm"], 130)
            self.assertEqual(runtime.state.snapshot()["transport"]["bpm"], 130)
            runtime.close()

    def test_standby_is_read_only_until_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            envelope = runtime.export_replica()
            runtime.set_node_role({"role": "standby", "acknowledgeAuthorityChange": True})
            with self.assertRaises(RuntimeError):
                runtime.mutate(None, lambda: runtime.state.patch_show({"bpm": 140}))
            applied = runtime.apply_replica(envelope)
            self.assertTrue(applied["accepted"])
            runtime.set_node_role({"role": "primary", "acknowledgeAuthorityChange": True, "forceAuthorityOverride": True})
            result, _ = runtime.mutate(None, lambda: runtime.state.patch_show({"bpm": 140}))
            self.assertEqual(result["transport"]["bpm"], 140)
            runtime.close()

    def test_runtime_persists_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            runtime.mutate(None, lambda: runtime.state.patch_system({"venue": "Test Venue"}))
            restored = StageMeshRuntime(Path(tmp))
            self.assertEqual(restored.state.snapshot()["system"]["venue"], "Test Venue")
            self.assertFalse(restored.state.snapshot()["transport"]["running"])
            runtime.close()
            restored.close()


if __name__ == "__main__":
    unittest.main()


class ContinuityTests(unittest.TestCase):
    def test_failover_continuity_report_separates_clock_from_output_rearm(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            runtime._record_failover_continuity(4200)
            report = runtime.failover_continuity_status()
            self.assertEqual(report["replicaAgeMs"], 4200)
            self.assertFalse(report["physicalOutputsAutoArmed"])
            self.assertIn(report["grade"], {"unmeasured", "sample-window", "tight", "degraded", "discontinuous"})
            if runtime.native.available:
                self.assertTrue(report["measured"])
                self.assertIsNotNone(report["timelineErrorMs"])
            runtime.close()


    def test_failover_uses_signed_primary_program_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            try:
                snapshot = runtime.state.persistence_snapshot()
                runtime.set_node_role({"role": "standby", "acknowledgeAuthorityChange": True})
                envelope = make_envelope(
                    snapshot,
                    node_id="primary-a",
                    epoch=7,
                    sequence=1,
                    execution_telemetry={
                        "showTimeNs": 2_000_000_000,
                        "transportRunning": True,
                        "audioOutputs": [{"slot": 0, "purpose": "foh", "lastBlockEndShowNs": 1_995_000_000}],
                        "activeAudioInputSlots": [0],
                    },
                )
                runtime.apply_replica(envelope)
                runtime.set_node_role({"role": "primary", "acknowledgeAuthorityChange": True, "forceAuthorityOverride": True})
                report = runtime.failover_continuity_status()
                self.assertEqual(report["sourceLastProgramShowNs"], 1_995_000_000)
                self.assertEqual(report["handoffMode"], "live-input-state-warm")
                self.assertFalse(report["deterministicPrebufferEligible"])
            finally:
                runtime.close()

    def test_handoff_readiness_explains_live_input_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            try:
                snapshot = runtime.state.persistence_snapshot()
                runtime.set_node_role({"role": "standby", "acknowledgeAuthorityChange": True})
                envelope = make_envelope(
                    snapshot, node_id="primary-a", epoch=3, sequence=1,
                    execution_telemetry={
                        "showTimeNs": 4_000_000_000, "transportRunning": True,
                        "audioOutputs": [{"slot": 0, "lastBlockEndShowNs": 3_995_000_000}],
                        "activeAudioInputSlots": [0, 2],
                    },
                )
                runtime.apply_replica(envelope)
                ready = runtime.handoff_readiness_status()
                self.assertEqual(ready["mode"], "live-input-state-warm")
                self.assertEqual(ready["activeLiveInputSlots"], [0, 2])
                self.assertFalse(ready["prebufferReady"])
                self.assertTrue(any("duplicated" in reason for reason in ready["reasons"]))
            finally:
                runtime.close()

    def test_cross_node_program_gap_is_measured_in_show_time(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime._promotion_at_ns = 1
                runtime._last_failover_continuity["sourceLastProgramShowNs"] = 1_000_000_000
                with patch.object(runtime, "audio_outputs_status", return_value={
                    "outputs": [{
                        "slot": 0, "active": True, "firstWriteNs": 2,
                        "firstRenderShowNs": 1_012_000_000, "maxExcessGapMs": 0.4,
                    }]
                }):
                    runtime._refresh_failover_audio_telemetry()
                report = runtime.failover_continuity_status()
                self.assertEqual(report["crossNodeProgramGapMs"], 12.0)
                self.assertEqual(report["crossNodeProgramOverlapMs"], 0.0)
                self.assertEqual(report["crossNodeProgramGrade"], "tight")
            finally:
                runtime.close()

class PeerReplicationTransportTests(unittest.TestCase):
    def test_push_client_delivers_handoff_readiness_to_peer_route(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from peer_replication import ReplicationPushClient

        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                received.append((self.path, json.loads(self.rfile.read(length).decode("utf-8"))))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = ReplicationPushClient(f"http://127.0.0.1:{server.server_port}")
            result = client.deliver_planned_handoff_ready({"transactionId": 92})
            self.assertTrue(result.ok)
            self.assertEqual(received, [("/api/v1/handoff/planned/peer-ready", {"transactionId": 92})])
            self.assertEqual(client.status()["handoffReadyDeliveries"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

    def test_primary_consumes_handoff_readiness_idempotently(self):
        secret = b"ready-secret"
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime._replication_secret = secret
                runtime.replication.set_role("primary")
                node_id = str(runtime.replication.status()["nodeId"])
                offer = make_offer(transaction_id=93, source_node_id=node_id,
                                   target_node_id="standby-b", source_epoch=1, target_epoch=2,
                                   target_show_ns=99, allow_degraded_program=False, secret=secret)
                runtime._planned_handoff = {
                    "state": "offered",
                    **{key: value for key, value in offer.items() if key != "hmacSha256"},
                }
                receipt = make_ready_receipt(offer=offer, program_ready=True, secret=secret)
                first = runtime.planned_handoff_peer_ready(receipt)
                second = runtime.planned_handoff_peer_ready(receipt)
                self.assertEqual(first["transaction"]["state"], "target-ready")
                self.assertTrue(second["transaction"]["programReady"])
                self.assertEqual(second["transaction"]["readyReceiptDigest"], receipt["digestSha256"])
                conflict = make_ready_receipt(offer=offer, program_ready=False, secret=secret)
                with self.assertRaises(RuntimeError):
                    runtime.planned_handoff_peer_ready(conflict)
            finally:
                runtime.close()

    def test_primary_push_client_delivers_replication_envelope(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from peer_replication import ReplicationPushClient

        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                received.append(json.loads(self.rfile.read(length).decode("utf-8")))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = ReplicationPushClient(f"http://127.0.0.1:{server.server_port}")
            envelope = make_envelope({"revision": 7}, node_id="primary-a", epoch=2, sequence=3, secret=b"secret")
            result = client.push(envelope)
            self.assertTrue(result.ok)
            self.assertEqual(received[0]["revision"], 7)
            status = client.status()
            self.assertEqual(status["pushes"], 1)
            self.assertIsNone(status["lastError"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

    def test_failover_detector_requires_stale_replica_before_promotion(self):
        from runtime import StageMeshRuntime
        from tempfile import TemporaryDirectory
        import time

        with TemporaryDirectory() as directory:
            runtime = StageMeshRuntime(Path(directory))
            try:
                envelope = runtime.export_replica()
                runtime.set_node_role({"role": "standby", "acknowledgeAuthorityChange": True})
                runtime.apply_replica(envelope)
                runtime._failover_suspect_ms = 100
                runtime._failover_promote_ms = 200
                self.assertFalse(runtime.failover_status()["safeToPromote"])
                # Advance the replica-age source directly instead of racing the
                # process scheduler against a 1–2 ms wall-clock threshold.
                with runtime.replication._lock:
                    runtime.replication._last_applied_at -= 0.250
                self.assertTrue(runtime.failover_status()["safeToPromote"])
                promoted = runtime.promote_after_failure({"acknowledgeAuthorityChange": True})
                self.assertTrue(promoted["promoted"])
                self.assertEqual(promoted["node"]["role"], "primary")
                self.assertFalse(promoted["node"]["lightingArmed"])
                self.assertFalse(promoted["node"]["audio"]["active"])
            finally:
                runtime.close()
    def test_runtime_automatically_pushes_signed_heartbeat_to_peer(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from unittest.mock import patch
        import time

        received = []
        secret = b"runtime-peer-secret"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                envelope = json.loads(self.rfile.read(length).decode("utf-8"))
                received.append(envelope)
                ok, _ = verify_envelope(envelope, secret=secret)
                body = b"{}" if ok else b'{"error":"bad envelope"}'
                self.send_response(200 if ok else 400)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {
                "STAGEMESH_PEER_URL": f"http://127.0.0.1:{server.server_port}",
                "STAGEMESH_REPLICATION_SECRET": secret.decode(),
                "STAGEMESH_REPLICATION_INTERVAL_SECONDS": "0.05",
                "STAGEMESH_REPLICATION_HEARTBEAT_SECONDS": "0.10",
                "STAGEMESH_NATIVE_ENGINE": "off",
            }
            with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
                runtime = StageMeshRuntime(Path(tmp))
                try:
                    deadline = time.time() + 1.0
                    status = runtime.replication_status()
                    while (not received or status["transport"]["pushes"] < 1) and time.time() < deadline:
                        time.sleep(0.02)
                        status = runtime.replication_status()
                    self.assertTrue(received)
                    self.assertTrue(status["automaticPushEnabled"])
                    self.assertGreaterEqual(status["transport"]["pushes"], 1)
                finally:
                    runtime.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=1)


class WitnessLeaseTests(unittest.TestCase):
    def test_transfer_suspends_all_future_acquisition_even_after_partial_failure(self):
        from unittest.mock import patch
        from witness import WitnessQuorumClient, WitnessResult
        for transferred in (True, False):
            with self.subTest(transferred=transferred):
                client = WitnessQuorumClient(["http://witness"], "show", "old", b"secret")
                result = WitnessResult("http://witness", transferred, 2, 1, "new")
                with patch.object(client, "_transfer_one", return_value=result):
                    client.transfer(target_node_id="new", source_epoch=1, target_epoch=2, transaction_id=9)
                with patch.object(client, "_one") as acquire:
                    for _ in range(3):
                        status = client.acquire()
                        self.assertTrue(status["acquisitionSuspended"])
                        self.assertFalse(status["leaseValid"])
                    acquire.assert_not_called()
                self.assertFalse(client.valid())

    def test_transfer_exception_still_suspends_acquisition(self):
        from unittest.mock import patch
        from witness import WitnessQuorumClient
        client = WitnessQuorumClient(["http://witness"], "show", "old", b"secret")
        with patch.object(client, "_transfer_one", side_effect=ValueError("malformed response")):
            with self.assertRaises(ValueError):
                client.transfer(target_node_id="new", source_epoch=1, target_epoch=2, transaction_id=9)
        with patch.object(client, "_one") as acquire:
            self.assertFalse(client.acquire()["leaseValid"])
            acquire.assert_not_called()

    def test_witness_store_fences_second_holder_until_expiry(self):
        from witness import WitnessLeaseStore
        import time as _time
        with tempfile.TemporaryDirectory() as tmp:
            store = WitnessLeaseStore(Path(tmp) / "leases.json")
            first = store.acquire("show-a", "node-a", 500)
            self.assertTrue(first["granted"])
            denied = store.acquire("show-a", "node-b", 500)
            self.assertFalse(denied["granted"])
            self.assertEqual(denied["holderNodeId"], "node-a")
            _time.sleep(0.55)
            second = store.acquire("show-a", "node-b", 500)
            self.assertTrue(second["granted"])
            self.assertGreater(second["epoch"], first["epoch"])

    def test_witness_store_transfers_only_live_exact_source_lease(self):
        from witness import WitnessLeaseStore
        with tempfile.TemporaryDirectory() as tmp:
            store = WitnessLeaseStore(Path(tmp) / "leases.json")
            first = store.acquire("show-transfer", "node-a", 1000)
            moved = store.transfer("show-transfer", "node-a", "node-b", first["epoch"],
                                   first["epoch"] + 1, 71, 1000)
            self.assertTrue(moved["granted"])
            self.assertEqual(moved["holderNodeId"], "node-b")
            replay = store.transfer("show-transfer", "node-a", "node-b", first["epoch"],
                                    first["epoch"] + 1, 71, 1000)
            self.assertTrue(replay["granted"])
            self.assertTrue(replay["idempotent"])
            stolen = store.acquire("show-transfer", "node-c", 1000)
            self.assertFalse(stolen["granted"])
            wrong = store.transfer("show-transfer", "node-a", "node-c", first["epoch"],
                                   first["epoch"] + 1, 72, 1000)
            self.assertFalse(wrong["granted"])

    def test_witness_quorum_requires_majority(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from witness import WitnessLeaseStore, WitnessQuorumClient, verify_request, verify_transfer_request, sign_response

        secret = b"witness-test-secret"
        servers = []
        threads = []
        try:
            for _ in range(3):
                store = WitnessLeaseStore()
                class Handler(BaseHTTPRequestHandler):
                    lease_store = store
                    def log_message(self, *args):
                        pass
                    def do_POST(self):
                        length = int(self.headers.get("Content-Length", "0"))
                        body = json.loads(self.rfile.read(length).decode("utf-8"))
                        transfer = self.path == "/api/v1/lease/transfer"
                        ok, reason, payload = (verify_transfer_request(body, secret) if transfer
                                               else verify_request(body, secret))
                        if not ok:
                            raw = json.dumps({"error": reason}).encode()
                            self.send_response(403)
                        else:
                            if transfer:
                                result = self.lease_store.transfer(
                                    payload["clusterId"], payload["sourceNodeId"], payload["targetNodeId"],
                                    payload["sourceEpoch"], payload["targetEpoch"], payload["transactionId"],
                                    payload["ttlMs"])
                            else:
                                result = self.lease_store.acquire(payload["clusterId"], payload["nodeId"], payload["ttlMs"])
                            raw = json.dumps(sign_response(result, payload, "transfer" if self.path.endswith("/transfer") else "acquire", secret)).encode()
                            self.send_response(200)
                        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                thread = Thread(target=server.serve_forever, daemon=True); thread.start()
                servers.append(server); threads.append(thread)
            urls = [f"http://127.0.0.1:{s.server_port}" for s in servers]
            client = WitnessQuorumClient(urls, "show-a", "node-a", secret, ttl_ms=1000)
            status = client.acquire()
            self.assertTrue(status["leaseValid"])
            self.assertEqual(status["quorum"], 2)
            self.assertGreaterEqual(status["leaseEpoch"], 1)
            transfer = client.transfer(target_node_id="node-b", source_epoch=status["leaseEpoch"],
                                       target_epoch=status["leaseEpoch"] + 1, transaction_id=72)
            self.assertTrue(transfer["transferred"])
            self.assertEqual(transfer["grants"], 3)
            self.assertFalse(client.status()["leaseValid"])
            successor = WitnessQuorumClient(urls, "show-a", "node-b", secret, ttl_ms=1000)
            successor_status = successor.acquire()
            self.assertTrue(successor_status["leaseValid"])
            self.assertEqual(successor_status["leaseEpoch"], status["leaseEpoch"] + 1)
        finally:
            for server in servers:
                server.shutdown(); server.server_close()
            for thread in threads:
                thread.join(timeout=1)

class WitnessRuntimeFencingTests(unittest.TestCase):
    def test_background_tick_does_not_reacquire_after_planned_release(self):
        from unittest.mock import patch
        from witness import WitnessQuorumClient, WitnessResult
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime.replication.set_role("primary")
                runtime._auto_failover = True
                runtime._witness = WitnessQuorumClient(["http://witness"], "show", "old", b"secret")
                runtime._planned_handoff = {
                    "state": "target-ready", "transactionId": 9, "sourceNodeId": "old",
                    "targetNodeId": "new", "sourceEpoch": 1, "targetEpoch": 2,
                    "targetShowNs": 0, "programReady": True,
                }
                with patch.object(runtime._witness, "_transfer_one", return_value=WitnessResult("http://witness", True, 2, 1, "new")):
                    runtime.planned_handoff_release_authority({"acknowledgeAuthorityRelease": True})
                with patch.object(runtime._witness, "_one") as acquire, patch.object(runtime, "failover_status", return_value={"heartbeatEligible": True}):
                    runtime._witness_tick()
                    runtime._witness_tick()
                    acquire.assert_not_called()
                self.assertEqual(runtime.replication.role, "standby")
                self.assertFalse(runtime._has_authority())
            finally:
                runtime.close()

    def test_planned_release_demotes_before_witness_transfer(self):
        class FakeWitness:
            configured = True

            def __init__(self):
                self.role_at_transfer = None

            def transfer(self, **facts):
                self.role_at_transfer = runtime.replication.role
                return {"transferred": True, **facts, "grants": 2, "quorum": 2}

        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime.replication.set_role("primary")
                runtime._witness = FakeWitness()
                runtime._planned_handoff = {
                    "state": "target-ready", "transactionId": 73,
                    "sourceNodeId": runtime.replication.status()["nodeId"],
                    "targetNodeId": "node-b", "sourceEpoch": 1, "targetEpoch": 2,
                    "targetShowNs": 0, "programReady": True,
                }
                result = runtime.planned_handoff_release_authority(
                    {"acknowledgeAuthorityRelease": True})
                self.assertEqual(runtime._witness.role_at_transfer, "standby")
                self.assertEqual(runtime.replication.role, "standby")
                self.assertEqual(result["transaction"]["state"], "authority-released")
                self.assertFalse(result["transaction"]["physicalOutputsArmed"])
            finally:
                runtime.close()

    def test_partial_planned_release_remains_demoted_and_indeterminate(self):
        class PartialWitness:
            configured = True

            def transfer(self, **facts):
                return {"transferred": False, **facts, "grants": 1, "quorum": 2}

            def status(self):
                return {"leaseValid": False, "leaseEpoch": 1}

        with tempfile.TemporaryDirectory() as tmp:
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime.replication.set_role("primary")
                runtime._witness = PartialWitness()
                runtime._planned_handoff = {
                    "state": "target-ready", "transactionId": 74,
                    "sourceNodeId": runtime.replication.status()["nodeId"],
                    "targetNodeId": "node-b", "sourceEpoch": 1, "targetEpoch": 2,
                    "targetShowNs": 0, "programReady": True,
                }
                result = runtime.planned_handoff_release_authority(
                    {"acknowledgeAuthorityRelease": True})
                self.assertEqual(runtime.replication.role, "standby")
                self.assertEqual(result["transaction"]["state"], "release-indeterminate")
                self.assertFalse(runtime.witness_status()["authoritative"])
            finally:
                runtime.close()

    def test_primary_self_fences_after_witness_lease_expires(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from unittest.mock import patch
        from witness import WitnessLeaseStore, verify_request, sign_response
        import time as _time

        secret = b"runtime-witness-secret"
        store = WitnessLeaseStore()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                ok, reason, payload = verify_request(body, secret)
                if not ok:
                    raw = json.dumps({"error": reason}).encode(); self.send_response(403)
                else:
                    raw = json.dumps(sign_response(store.acquire(payload["clusterId"], payload["nodeId"], payload["ttlMs"]), payload, "acquire", secret)).encode(); self.send_response(200)
                self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        runtime = None
        try:
            env = {
                "STAGEMESH_WITNESS_URLS": f"http://127.0.0.1:{server.server_port}",
                "STAGEMESH_WITNESS_SECRET": secret.decode(),
                "STAGEMESH_WITNESS_TTL_MS": "500",
                "STAGEMESH_WITNESS_TIMEOUT_SECONDS": "0.1",
                "STAGEMESH_NATIVE_ENGINE": "off",
            }
            with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
                runtime = StageMeshRuntime(Path(tmp))
                deadline = _time.time() + 1.0
                while not runtime.witness_status()["authoritative"] and _time.time() < deadline:
                    _time.sleep(0.02)
                self.assertTrue(runtime.witness_status()["authoritative"])
                server.shutdown(); server.server_close(); thread.join(timeout=1)
                deadline = _time.time() + 1.5
                while runtime.replication.role == "primary" and _time.time() < deadline:
                    _time.sleep(0.03)
                self.assertEqual(runtime.replication.role, "standby")
                self.assertFalse(runtime.node_status()["physicalAuthority"])
        finally:
            if runtime is not None: runtime.close()
            try: server.shutdown(); server.server_close()
            except Exception: pass
            if thread.is_alive(): thread.join(timeout=1)

class AutomaticFailoverTests(unittest.TestCase):
    def test_standby_auto_promotes_only_after_heartbeat_and_witness_lease(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from unittest.mock import patch
        from witness import WitnessLeaseStore, verify_request, sign_response
        import time as _time

        secret = b"auto-witness-secret"
        store = WitnessLeaseStore()
        store.acquire("show-auto", "node-a", 500)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                ok, reason, payload = verify_request(body, secret)
                if not ok:
                    raw = json.dumps({"error": reason}).encode(); self.send_response(403)
                else:
                    raw = json.dumps(sign_response(store.acquire(payload["clusterId"], payload["nodeId"], payload["ttlMs"]), payload, "acquire", secret)).encode(); self.send_response(200)
                self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            env = {
                "STAGEMESH_NODE_ID": "node-b", "STAGEMESH_NODE_ROLE": "standby",
                "STAGEMESH_WITNESS_URLS": f"http://127.0.0.1:{server.server_port}",
                "STAGEMESH_WITNESS_SECRET": secret.decode(), "STAGEMESH_CLUSTER_ID": "show-auto",
                "STAGEMESH_WITNESS_TTL_MS": "500", "STAGEMESH_AUTO_FAILOVER": "1",
                "STAGEMESH_FAILOVER_SUSPECT_MS": "100", "STAGEMESH_FAILOVER_PROMOTE_MS": "200",
                "STAGEMESH_NATIVE_ENGINE": "off",
            }
            with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
                runtime = StageMeshRuntime(Path(tmp))
                try:
                    primary = ReplicationTracker("node-a", "primary")
                    runtime.apply_replica(primary.export(runtime.state.persistence_snapshot()))
                    self.assertEqual(runtime.replication.role, "standby")
                    deadline = _time.time() + 1.5
                    while runtime.replication.role != "primary" and _time.time() < deadline:
                        _time.sleep(0.03)
                    self.assertEqual(runtime.replication.role, "primary")
                    self.assertTrue(runtime.witness_status()["authoritative"])
                    self.assertFalse(runtime.node_status()["lightingArmed"])
                finally:
                    runtime.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=1)
