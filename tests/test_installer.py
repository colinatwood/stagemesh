import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class InstallerTests(unittest.TestCase):
    def install(self, stage, build, prefix="/usr"):
        env = {**os.environ, "DESTDIR":str(stage), "PREFIX":prefix,
               "STAGEFORGE_BUILD_DIR":str(build)}
        return subprocess.run(["sh",str(ROOT/"scripts/install-linux.sh")],env=env,
                              capture_output=True,text=True)

    def test_staged_helper_and_reinstall_preserve_data(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);build=root/"build";stage=root/"stage"
            (build/"native").mkdir(parents=True)
            engine=build/"native/stagemesh_engine"
            engine.write_text("#!/bin/sh\nexit 0\n");engine.chmod(0o755)
            data=stage/"var/lib/stageforge/user-session.json"
            data.parent.mkdir(parents=True);data.write_text('{"preserve":true}')
            for _ in range(2):
                result=self.install(stage,build)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(data.read_text(),'{"preserve":true}')
            helper=stage/"usr/libexec/stageforge/stageforge-qualify.py"
            result=subprocess.run([sys.executable,str(helper)],cwd=root,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIsInstance(json.loads(result.stdout),dict)
            self.assertTrue((stage/"usr/libexec/stageforge/stageforge-http-qualify.py").is_file())
            self.assertTrue((stage/"usr/libexec/stageforge/stageforge-witness-qualify.py").is_file())
            self.assertTrue((stage/"usr/libexec/stageforge/stageforge-package-qualify.py").is_file())
            self.assertTrue((stage/"usr/libexec/stageforge/stageforge-qualification-plan.py").is_file())
            self.assertTrue((stage/"usr/libexec/stageforge/stageforge-qualification-review.py").is_file())
            self.assertTrue((stage/"usr/libexec/stageforge/stageforge-qualification-status.py").is_file())
            self.assertTrue((stage/"usr/share/stageforge/packaging/stageforge-proxy.env.example").is_file())
            self.assertTrue((stage/"usr/share/stageforge/packaging/stageforge-witness.env.example").is_file())
            self.assertTrue((stage/"usr/share/stageforge/packaging/reverse-proxy/README.md").is_file())
            self.assertTrue((stage/"usr/share/stageforge/frontend/index.html").is_file())
            unit=(stage/"usr/lib/systemd/system/stageforge.service").read_text()
            self.assertIn("--host 127.0.0.1",unit)
            self.assertIn("ProtectKernelTunables=true",unit)
            self.assertIn("EnvironmentFile=-/etc/stageforge/stageforge.env",unit)
            witness_unit=(stage/"usr/lib/systemd/system/stageforge-witness.service").read_text()
            self.assertIn("STAGEFORGE_WITNESS_INDEPENDENT=1", witness_unit)
            self.assertIn("STAGEFORGE_WITNESS_HOST=127.0.0.1", witness_unit)
            self.assertIn("EnvironmentFile=-/etc/stageforge/witness.env", witness_unit)
            self.assertTrue((stage/"usr/lib/sysusers.d/stageforge.conf").is_file())
            self.assertTrue((stage/"usr/lib/tmpfiles.d/stageforge.conf").is_file())
            self.assertTrue((stage/"usr/share/stageforge/packaging/driver-catalog.json").is_file())
            self.assertFalse((stage/"etc/systemd/system/multi-user.target.wants").exists())

            uninstall_env={**os.environ,"DESTDIR":str(stage),"PREFIX":"/usr"}
            removed=subprocess.run(["sh",str(ROOT/"scripts/uninstall-linux.sh")],env=uninstall_env,capture_output=True,text=True)
            self.assertEqual(removed.returncode,0,removed.stderr)
            self.assertFalse((stage/"usr/share/stageforge").exists())
            self.assertEqual(data.read_text(),'{"preserve":true}')

    def test_staged_uninstall_purge_is_explicit(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); stage=root/"stage"; data=stage/"var/lib/stageforge/session.json"
            data.parent.mkdir(parents=True);data.write_text("keep")
            env={**os.environ,"DESTDIR":str(stage),"PREFIX":"/usr"}
            bad=subprocess.run(["sh",str(ROOT/"scripts/uninstall-linux.sh"),"--unknown"],env=env,capture_output=True,text=True)
            self.assertNotEqual(bad.returncode,0);self.assertTrue(data.exists())
            purge=subprocess.run(["sh",str(ROOT/"scripts/uninstall-linux.sh"),"--purge-data"],env=env,capture_output=True,text=True)
            self.assertEqual(purge.returncode,0,purge.stderr);self.assertFalse(data.exists())

    def test_invalid_prefix_does_not_install(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);result=self.install(root/"stage",root/"missing","/opt/stageforge")
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((root/"stage").exists())

    def test_missing_build_does_not_install(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);result=self.install(root/"stage",root/"missing")
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((root/"stage").exists())
