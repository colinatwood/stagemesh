import os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from runtime import StageMeshRuntime


class DawTemporaryResourceRuntimeTests(unittest.TestCase):
    def runtime(self,root):
        runtime=StageMeshRuntime.__new__(StageMeshRuntime);runtime.daw_media_root=Path(root)/"media";runtime.daw_media_root.mkdir();objects=runtime.daw_media_root/"objects";objects.mkdir();runtime.daw_media=SimpleNamespace(objects=objects);runtime.daw_exports_root=Path(root)/"exports";runtime.daw_exports_root.mkdir()
        return runtime

    def test_cleanup_requires_exact_boolean_acknowledgement(self):
        with tempfile.TemporaryDirectory() as raw:
            runtime=self.runtime(raw)
            for value in (None,False,"true",1):
                with self.subTest(value=value),self.assertRaisesRegex(ValueError,"acknowledgeCleanup"):
                    runtime.daw_temporary_resource_cleanup({"acknowledgeCleanup":value})

    def test_empty_status_and_cleanup_remain_disarmed(self):
        with tempfile.TemporaryDirectory() as raw,patch.dict(os.environ,{"STAGEMESH_SNAPSHOT_DIR":str(Path(raw)/"snapshots"),"STAGEMESH_PLUGIN_SCRATCH_DIR":str(Path(raw)/"plugin-scratch")}):
            runtime=self.runtime(raw);status=runtime.daw_temporary_resource_status()
            self.assertEqual(status["resourceCount"],0);self.assertFalse(status["physicalOutputsArmed"])
            cleaned=runtime.daw_temporary_resource_cleanup({"acknowledgeCleanup":True})
            self.assertEqual(cleaned["reclaimedCount"],0);self.assertFalse(cleaned["physicalOutputsArmed"])

    def test_plugin_lifecycle_projection_never_restarts_or_arms(self):
        with tempfile.TemporaryDirectory() as raw,patch.dict(os.environ,{"STAGEMESH_PLUGIN_SCRATCH_DIR":str(Path(raw)/"plugin-scratch")}):
            status=self.runtime(raw).plugin_host_lifecycle_status()
            self.assertEqual(status["documentType"],"org.upp.plugin-host-lifecycle");self.assertFalse(status["automaticRestart"]);self.assertFalse(status["physicalOutputsArmed"]);self.assertIn("scratch",status)


if __name__=="__main__":unittest.main()
