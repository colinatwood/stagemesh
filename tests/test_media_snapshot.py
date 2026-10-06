import hashlib
import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from daw_production import OfflineRenderer
from daw_playback import ArrangementProducer
from media_snapshot import MediaSnapshot
from temporary_ownership import create_owner_manifest
from daw_session import render_plan
from types import SimpleNamespace
from test_daw_playback import FakeNative


class MediaSnapshotTests(unittest.TestCase):
    def test_status_classifies_resources_without_owner_or_source_paths(self):
        with tempfile.TemporaryDirectory() as raw,patch.dict(os.environ,{"STAGEMESH_SNAPSHOT_DIR":raw}):
            store=Path(raw)
            live=store/"snapshot-live";live.mkdir();create_owner_manifest(live/"owner.json",live,resource_class="media-snapshot",purpose="arrangement-playback",extra={"reservedBytes":77});(live/"source.wav").write_bytes(b"1234")
            dead=store/"snapshot-dead";dead.mkdir();create_owner_manifest(dead/"owner.json",dead,resource_class="media-snapshot",purpose="offline-render",extra={"reservedBytes":88});owner=json.loads((dead/"owner.json").read_text());owner["pid"]=99999999;(dead/"owner.json").write_text(json.dumps(owner))
            unknown=store/"snapshot-unknown";unknown.mkdir();(unknown/"owner.json").write_text("{broken")
            status=MediaSnapshot.status(store/"media")
            self.assertEqual(status["resourceCount"],3);self.assertEqual(status["liveCount"],1);self.assertEqual(status["reclaimableCount"],1);self.assertEqual(status["unknownOwnerCount"],1)
            encoded=json.dumps(status);self.assertNotIn('"pid"',encoded);self.assertNotIn(str(store),encoded)

    def test_acknowledged_reclaim_removes_only_proven_dead_exact_owner(self):
        with tempfile.TemporaryDirectory() as raw,patch.dict(os.environ,{"STAGEMESH_SNAPSHOT_DIR":raw}):
            store=Path(raw)
            live=store/"snapshot-live";live.mkdir();create_owner_manifest(live/"owner.json",live,resource_class="media-snapshot",purpose="playback")
            dead=store/"snapshot-dead";dead.mkdir();create_owner_manifest(dead/"owner.json",dead,resource_class="media-snapshot",purpose="render");owner=json.loads((dead/"owner.json").read_text());owner["pid"]=99999999;(dead/"owner.json").write_text(json.dumps(owner))
            unknown=store/"snapshot-unknown";unknown.mkdir();(unknown/"owner.json").write_text("broken")
            result=MediaSnapshot.reclaim(store/"media")
            self.assertEqual(result["reclaimedCount"],1);self.assertEqual(result["reclaimedResourceIds"],["snapshot-dead"])
            self.assertTrue(live.exists());self.assertTrue(unknown.exists());self.assertFalse(dead.exists())

    def test_stale_cleanup_preserves_legacy_and_replaced_resources(self):
        with tempfile.TemporaryDirectory() as raw:
            store=Path(raw)
            dead=store/"snapshot-dead";dead.mkdir();create_owner_manifest(dead/"owner.json",dead,resource_class="media-snapshot",purpose="render",extra={"reservedBytes":88});owner=json.loads((dead/"owner.json").read_text());owner["pid"]=99999999;(dead/"owner.json").write_text(json.dumps(owner))
            legacy=store/"snapshot-legacy";legacy.mkdir();(legacy/"owner.json").write_text(json.dumps({"pid":99999999,"reservedBytes":77}))
            replaced=store/"snapshot-replaced";replaced.mkdir();create_owner_manifest(replaced/"owner.json",replaced,resource_class="media-snapshot",purpose="render");owner=json.loads((replaced/"owner.json").read_text());owner["pid"]=99999999;(replaced/"owner.json").write_text(json.dumps(owner));saved=(replaced/"owner.json").read_bytes();held=store/"held-original";os.rename(replaced,held);replaced.mkdir();(replaced/"owner.json").write_bytes(saved)
            reclaimed=MediaSnapshot.cleanup_stale(store)
            self.assertEqual(reclaimed,["snapshot-dead"]);self.assertTrue(legacy.exists());self.assertTrue(replaced.exists());self.assertTrue(held.exists())

    def test_configured_shared_store_and_owner_manifest(self):
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as shared:
            root = Path(raw); _, session = self.fixture(root)
            with patch.dict(os.environ, {"STAGEMESH_SNAPSHOT_DIR": shared}):
                snapshot = MediaSnapshot(root, render_plan(session, 0, 256))
                try:
                    self.assertEqual(snapshot.root.parent, Path(shared).resolve())
                    owner = json.loads((snapshot.root / "owner.json").read_text())
                    self.assertEqual(owner["pid"], os.getpid());self.assertEqual(owner["schemaVersion"],2);self.assertEqual(owner["resourceClass"],"media-snapshot")
                    self.assertGreater(owner["reservedBytes"], 0);self.assertEqual(owner["resourceIdentity"]["inode"],snapshot.root.stat().st_ino)
                finally: snapshot.close()
            self.assertEqual(list(Path(shared).glob("snapshot-*")), [])

    def test_configured_budget_is_strict_and_invalid_values_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); _, session = self.fixture(root)
            plan = render_plan(session, 0, 256)
            with patch.dict(os.environ, {"STAGEMESH_SNAPSHOT_MAX_BYTES": str(1024*1024),
                                         "STAGEMESH_SNAPSHOT_FREE_RESERVE_BYTES": "0"}):
                snapshot = MediaSnapshot(root, plan); snapshot.close()
            for value in ("invalid", "0", "-1"):
                with self.subTest(value=value), patch.dict(os.environ, {"STAGEMESH_SNAPSHOT_MAX_BYTES": value}):
                    with self.assertRaisesRegex(RuntimeError, "STAGEMESH_SNAPSHOT_MAX_BYTES"):
                        MediaSnapshot(root, plan)


    def test_owner_directory_sync_failure_cleans_snapshot_and_releases_budget(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);_,session=self.fixture(root);baseline=MediaSnapshot._reserved_bytes
            with patch("media_snapshot.fsync_directory",side_effect=OSError("sync")),self.assertRaisesRegex(OSError,"sync"):
                MediaSnapshot(root,render_plan(session,0,256))
            self.assertEqual(MediaSnapshot._reserved_bytes,baseline)
            store=MediaSnapshot._store_path(root);self.assertEqual(list(store.glob("snapshot-*")),[])

    def test_shared_budget_deduplicates_and_releases_reservations(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source, session = self.fixture(root)
            plan = render_plan(session, 0, 256)
            plan["regions"].append(plan["regions"][0])
            size = source.stat().st_size
            baseline = MediaSnapshot._reserved_bytes
            with patch.object(MediaSnapshot, "MAX_TOTAL_BYTES", baseline + size):
                first = MediaSnapshot(root, plan)
                try:
                    self.assertEqual(first.reserved_bytes, size)
                    with self.assertRaisesRegex(RuntimeError, "budget"):
                        MediaSnapshot(root, plan)
                    self.assertEqual(MediaSnapshot._reserved_bytes, baseline + size)
                finally:first.close()
                first.close()
                self.assertEqual(MediaSnapshot._reserved_bytes, baseline)
                next_snapshot = MediaSnapshot(root, plan)
                next_snapshot.close()

    def test_disk_rejection_and_hash_failure_release_resources(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source, session = self.fixture(root)
            plan = render_plan(session, 0, 256)
            baseline = MediaSnapshot._reserved_bytes
            with patch("media_snapshot.shutil.disk_usage", return_value=SimpleNamespace(free=0)):
                with self.assertRaisesRegex(RuntimeError, "temporary disk"):
                    MediaSnapshot(root, plan)
            source.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                MediaSnapshot(root, plan)
            self.assertEqual(MediaSnapshot._reserved_bytes, baseline)

    def fixture(self, root):
        source = root / "tone.wav"
        with wave.open(str(source), "wb") as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(48000)
            output.writeframes(b"\x00\x20" * 100)
        digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        session = {"tracks": [{"trackId": "t", "clips": [{"clipId": "c", "startFrame": 0, "lengthFrames": 256,
                   "source": {"type": "audio-file", "uri": "tone.wav", "contentHash": digest}}]}]}
        return source, session

    def test_export_uses_snapshot_after_original_is_replaced(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source, session = self.fixture(root)
            renderer = OfflineRenderer(root)
            baseline = renderer.render(session, root / "baseline.wav", 0, 256, bits=32)
            original = OfflineRenderer._source_slice
            roots = []
            def mutate(reader, *args):
                source.write_bytes(b"replaced source")
                roots.append(reader.media_root)
                return original(reader, *args)
            with patch.object(OfflineRenderer, "_source_slice", mutate):
                result = renderer.render(session, root / "result.wav", 0, 256, bits=32)
            self.assertEqual(result["outputSha256"], baseline["outputSha256"])
            self.assertTrue(roots)
            self.assertTrue(all(not path.exists() for path in roots))

    def test_playback_keeps_snapshot_until_worker_finishes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source, session = self.fixture(root)
            native = FakeNative(); producer = ArrangementProducer(native, root)
            original = producer._block
            def mutate(*args):
                source.write_bytes(b"replaced source")
                return original(*args)
            producer._block = mutate
            try:
                producer.start(session, 0, 256)
                producer.thread.join(1)
                self.assertFalse(producer.thread.is_alive())
                self.assertEqual(producer.status()["errors"], 0)
                self.assertAlmostEqual(native.blocks[0][2][0], .25 * (0.5 ** .5), places=5)
                self.assertFalse(producer.reader.media_root.exists())
            finally:
                producer.stop()
