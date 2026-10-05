import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
import temporary_ownership as ownership


class TemporaryOwnershipTests(unittest.TestCase):
    def test_manifest_is_versioned_inode_bound_and_durably_published(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);resource=root/"resource";resource.write_bytes(b"x");owner_path=root/"owner.json"
            original=os.fsync;calls=[]
            def observed(fd):calls.append(fd);return original(fd)
            with patch("temporary_ownership.os.fsync",side_effect=observed):
                owner=ownership.create_owner_manifest(owner_path,resource,resource_class="render-output",purpose="test")
            self.assertEqual(owner["schemaVersion"],2);self.assertEqual(owner["resourceIdentity"]["inode"],resource.stat().st_ino)
            if sys.platform.startswith("linux"):
                self.assertIsInstance(owner.get("procfsPid"),int)
            self.assertGreaterEqual(len(calls),2);self.assertEqual(ownership.classify_owner(owner_path,resource,resource_class="render-output")[0],"live")
            self.assertFalse(any(path.name.endswith('.tmp') for path in root.iterdir()))

    def test_missing_malformed_legacy_and_replaced_owner_evidence_are_unknown(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);resource=root/"resource";resource.write_bytes(b"first");owner_path=root/"owner.json"
            self.assertEqual(ownership.classify_owner(owner_path,resource)[0],"unknown-owner")
            owner_path.write_text("{broken");self.assertEqual(ownership.classify_owner(owner_path,resource)[0],"unknown-owner")
            owner_path.write_text(json.dumps({"pid":99999999}));self.assertEqual(ownership.classify_owner(owner_path,resource)[0],"unknown-owner")
            ownership.create_owner_manifest(owner_path,resource,resource_class="render-output",purpose="test");owner=json.loads(owner_path.read_text());owner["pid"]=99999999;owner_path.write_text(json.dumps(owner))
            replacement=root/"replacement";replacement.write_bytes(b"second");os.replace(replacement,resource)
            self.assertEqual(ownership.classify_owner(owner_path,resource,resource_class="render-output")[0],"unknown-owner")
            self.assertIsNone(ownership.recheck_reclaimable(owner_path,resource,resource_class="render-output"))


    def test_unclean_subprocess_exit_leaves_exact_reclaimable_resource(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);code=(
                "import os,sys;from pathlib import Path;sys.path.insert(0,sys.argv[2]);"
                "from staged_resources import StagedFile;"
                "s=StagedFile(Path(sys.argv[1]),prefix='.render-',suffix='.wav',resource_class='render-output',purpose='crash-test');"
                "s.path.write_bytes(b'partial');os._exit(0)"
            )
            subprocess.run([sys.executable,"-c",code,str(root),str(ROOT/"backend")],check=True)
            from staged_resources import StagedResourceRegistry
            registry=StagedResourceRegistry([("render-output",root,".render-*.wav")]);status=registry.status()
            self.assertEqual(status["reclaimableCount"],1);self.assertEqual(status["unknownOwnerCount"],0)
            cleaned=registry.reclaim();self.assertEqual(cleaned["reclaimedCount"],1);self.assertEqual(list(root.glob(".render-*.wav")),[])

    def test_exact_dead_owner_is_reclaimable(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);resource=root/"resource";resource.write_bytes(b"x");owner_path=root/"owner.json"
            ownership.create_owner_manifest(owner_path,resource,resource_class="render-output",purpose="test");owner=json.loads(owner_path.read_text());owner["pid"]=99999999;owner_path.write_text(json.dumps(owner))
            self.assertEqual(ownership.classify_owner(owner_path,resource,resource_class="render-output")[0],"reclaimable")
            self.assertIsNotNone(ownership.recheck_reclaimable(owner_path,resource,resource_class="render-output"))

    def test_malformed_procfs_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);resource=root/"resource";resource.write_bytes(b"x");owner_path=root/"owner.json"
            ownership.create_owner_manifest(owner_path,resource,resource_class="render-output",purpose="test")
            owner=json.loads(owner_path.read_text());owner["procfsPid"]="not-an-integer";owner_path.write_text(json.dumps(owner))
            self.assertEqual(ownership.classify_owner(owner_path,resource,resource_class="render-output")[0],"unknown-owner")
            self.assertIsNone(ownership.recheck_reclaimable(owner_path,resource,resource_class="render-output"))


if __name__=="__main__":unittest.main()
