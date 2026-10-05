import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from witness import WitnessQuorumClient, WitnessResult
from runtime import StageForgeRuntime


class HandoffRestartFenceTests(unittest.TestCase):
    def test_marker_is_durable_before_transfer_and_blocks_new_client(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fence.json"
            client = WitnessQuorumClient(["http://witness"], "show", "old", b"secret", fence_path=path)
            def transfer(url, payload):
                self.assertEqual(json.loads(path.read_text())["transactionId"], 12)
                return WitnessResult(url, True, 2, 9999999999999, "new")
            with patch.object(client, "_transfer_one", side_effect=transfer):
                client.transfer(target_node_id="new", source_epoch=1, target_epoch=2, transaction_id=12)
            restarted = WitnessQuorumClient(["http://witness"], "show", "old", b"secret", fence_path=path)
            with patch.object(restarted, "_one") as acquire:
                self.assertTrue(restarted.acquire()["acquisitionSuspended"])
                self.assertFalse(restarted.valid())
                acquire.assert_not_called()

    def test_sync_failure_prevents_witness_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fence.json"
            client = WitnessQuorumClient(["http://witness"], "show", "old", b"secret", fence_path=path)
            with patch("witness.os.fsync", side_effect=OSError("disk failure")), patch.object(client, "_transfer_one") as transfer:
                with self.assertRaises(OSError):
                    client.transfer(target_node_id="new", source_epoch=1, target_epoch=2, transaction_id=12)
                transfer.assert_not_called()
            self.assertTrue(client.status()["acquisitionSuspended"])
            restarted = WitnessQuorumClient([], "show", "old", b"", fence_path=path)
            self.assertTrue(restarted.status()["acquisitionSuspended"])

    def test_corrupt_marker_fences_startup_even_without_witness_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "handoff-acquisition-fence.json"
            path.write_text("{incomplete")
            with patch.dict("os.environ", {"STAGEFORGE_NODE_ROLE": "primary", "STAGEFORGE_WITNESS_URLS": "", "STAGEMESH_NATIVE_ENGINE": "off"}):
                runtime = StageForgeRuntime(Path(directory))
                try:
                    self.assertEqual(runtime.replication.role, "standby")
                    self.assertFalse(runtime._has_authority())
                    with self.assertRaisesRegex(RuntimeError, "fence"):
                        runtime.set_node_role({"role": "primary", "acknowledgeAuthorityChange": True, "forceAuthorityOverride": True})
                    with self.assertRaisesRegex(RuntimeError, "fence"):
                        runtime.promote_after_failure({"acknowledgeAuthorityChange": True})
                    runtime.replication.set_role("primary")
                    self.assertFalse(runtime._has_authority())
                finally:
                    runtime.close()

    def test_missing_marker_allows_normal_acquisition(self):
        with tempfile.TemporaryDirectory() as directory:
            client = WitnessQuorumClient(["http://witness"], "show", "old", b"secret", fence_path=Path(directory) / "fence.json")
            with patch.object(client, "_one", return_value=WitnessResult("http://witness", True, 1, 9999999999999, "old")) as acquire:
                self.assertTrue(client.acquire()["leaseValid"])
                acquire.assert_called_once()
