import hashlib
import math
import os
import platform
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from plugin_host import IsolatedPluginHost,plugin_host_audit_status,plugin_host_scratch_cleanup,plugin_host_scratch_status,validate_platform_launch_evidence,validate_plugin_manifest

def platform_attestation():
    if platform.system() == "Darwin":
        return {"platformLaunchAttestations": {"Darwin": {"mode": "macos-codesign-cdhash-v1", "teamId": "ABC123DEF4", "codeDirectoryHash": "cdhash:" + "5" * 40}}}
    if platform.system() == "Windows":
        return {"platformLaunchAttestations": {"Windows": {"mode": "windows-authenticode-fileid-v1", "publisherCertificateSha256": "sha256:" + "2" * 64, "fileIdentityRequired": True}}}
    return {}

class PluginHostTests(unittest.TestCase):
    def test_slow_uncontended_acquisition_is_not_contention(self):
        with patch.dict("os.environ", {"STAGEMESH_RT_QUALIFICATION": "1"}):
            host=IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",{"format":"builtin","pluginId":"lock-test"})
        try:
            with patch("plugin_host.time.monotonic_ns", side_effect=[0, 200_000]):
                with host._locked():pass
            self.assertEqual(host.serialization_lock_attempts,1)
            self.assertEqual(host.serialization_lock_contentions,0)
            self.assertEqual(host.max_serialization_lock_wait_ns,200_000)
        finally:host.close()

    def test_failed_nonblocking_acquisition_counts_contention(self):
        from unittest.mock import Mock
        with patch.dict("os.environ", {"STAGEMESH_RT_QUALIFICATION": "1"}):
            host=IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",{"format":"builtin","pluginId":"contended-test"})
        lock=Mock();lock.acquire.side_effect=[False,True]
        try:
            with patch.object(host,"_lock",lock):
                with host._locked():pass
            self.assertEqual(host.serialization_lock_attempts,1)
            self.assertEqual(host.serialization_lock_contentions,1)
            self.assertEqual(lock.acquire.call_count,2)
            lock.release.assert_called_once()
        finally:host.close()

    def test_qualification_mode_measures_plugin_serialization_boundary(self):
        with patch.dict("os.environ", {"STAGEMESH_RT_QUALIFICATION": "1"}):
            host=IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",{"format":"builtin","pluginId":"qualified","configuration":{"gain":1}})
        try:
            host.start();host.process_block([.25,-.25]);audit=host.status()["audit"]
            self.assertTrue(audit["qualificationEnabled"]);self.assertGreaterEqual(audit["serializationLockAttempts"],4);self.assertGreater(audit["requestPayloadBytes"],0);self.assertGreater(audit["responsePayloadBytes"],0)
        finally:host.close()

    def test_builtin_isolated_processing(self):
        host=IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",{"format":"builtin","pluginId":"gain","configuration":{"gain":2}})
        try:
            self.assertFalse(host.start()["bypassed"])
            self.assertEqual(host.process_block([.25,-.75]),[.5,-1.0])
            status=host.status();self.assertTrue(status["isolated"]);self.assertEqual(status["handshake"],{"protocolVersion":1,"latencyFrames":0,"supportsProcess":True});self.assertEqual(status["audit"]["starts"],1);self.assertEqual(status["audit"]["requests"],2);self.assertEqual(status["audit"]["processBlocks"],1);self.assertEqual(status["audit"]["processedSamples"],2);self.assertGreater(status["audit"]["maxRequestDurationNs"],0);self.assertGreater(status["audit"]["requestPayloadBytes"],0);self.assertGreater(status["audit"]["responsePayloadBytes"],0);self.assertIn("serializationLockAttempts",status["audit"])
            self.assertIn("gain",[item["pluginId"] for item in plugin_host_audit_status()])
            with self.assertRaisesRegex(ValueError,"finite"):host.process_block([math.nan])
        finally:host.close()

    def test_external_requires_adapter(self):
        with self.assertRaises(ValueError):validate_plugin_manifest({"format":"vst3","pluginId":"x"})
        manifest={"format":"vst3","pluginId":"x","adapterExecutable":"relative-adapter","hostSystems":[platform.system()],"hostArchitectures":[platform.machine()],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+"0"*64,**platform_attestation()}
        with self.assertRaisesRegex(ValueError,"absolute executable"):IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",manifest)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux external adapter launch binding")
    def test_external_adapter_uses_explicit_executable_without_shell(self):
        with tempfile.TemporaryDirectory() as raw:
            adapter=Path(raw)/"adapter";adapter.write_text("#!/usr/bin/env python3\nimport json,sys\nfor line in sys.stdin:\n r=json.loads(line);o={'ok':True,'active':True,'protocolVersion':1,'pluginId':'external','format':'vst3','supportsProcess':True,'latencyFrames':64} if r['op']=='activate' else {'ok':True,'samples':[v*.5 for v in r['samples']]};o['requestId']=r['requestId'];print(json.dumps(o),flush=True)\n");adapter.chmod(0o700)
            manifest={"format":"vst3","pluginId":"external","adapterExecutable":str(adapter),"hostSystems":[platform.system()],"hostArchitectures":[platform.machine()],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+hashlib.sha256(adapter.read_bytes()).hexdigest(),**platform_attestation()}
            host=IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",manifest)
            try:self.assertEqual(host.start()["handshake"]["latencyFrames"],64);self.assertEqual(host.process_block([.5,-.5]),[.25,-.25]);self.assertEqual(host.executable,adapter)
            finally:host.close()

    @unittest.skipUnless(sys.platform.startswith("linux"),"Linux procfd launch binding")
    def test_linux_external_adapter_executes_verified_fd_after_path_replacement(self):
        import plugin_host
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);adapter=root/"adapter";replacement=root/"replacement"
            adapter.write_text("#!/usr/bin/env python3\nimport json,sys\nfor line in sys.stdin:\n r=json.loads(line);o={'ok':True,'active':True,'protocolVersion':1,'pluginId':'external','format':'vst3','supportsProcess':True,'latencyFrames':7} if r['op']=='activate' else {'ok':True,'samples':r['samples']};o['requestId']=r['requestId'];print(json.dumps(o),flush=True)\n");adapter.chmod(0o700)
            replacement.write_text("#!/usr/bin/env python3\nimport json,sys\nfor line in sys.stdin:\n r=json.loads(line);print(json.dumps({'ok':True,'requestId':r['requestId'],'active':True,'protocolVersion':1,'pluginId':'replaced','format':'vst3','supportsProcess':True,'latencyFrames':999}),flush=True)\n");replacement.chmod(0o700)
            manifest={"format":"vst3","pluginId":"external","adapterExecutable":str(adapter),"hostSystems":[platform.system()],"hostArchitectures":[platform.machine()],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+hashlib.sha256(adapter.read_bytes()).hexdigest()}
            host=IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",manifest)
            original_inode=adapter.stat().st_ino;real_popen=plugin_host.subprocess.Popen;replaced=False
            def launch(*args,**kwargs):
                nonlocal replaced
                if not replaced:
                    os.replace(replacement,adapter);replaced=True
                return real_popen(*args,**kwargs)
            try:
                with patch("plugin_host.subprocess.Popen",side_effect=launch):status=host.start()
                self.assertEqual(status["handshake"]["latencyFrames"],7)
                self.assertEqual(status["launch"]["binding"],"linux-procfd-sha256")
                self.assertEqual(status["launch"]["identity"]["inode"],original_inode)
                self.assertNotEqual(adapter.stat().st_ino,original_inode)
            finally:host.close()

    @unittest.skipUnless(sys.platform.startswith("linux"),"Linux O_NOFOLLOW launch binding")
    def test_linux_external_adapter_rejects_symlink_even_when_target_is_executable(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);target=root/"target";link=root/"adapter"
            target.write_text("#!/bin/sh\nexit 0\n");target.chmod(0o700);link.symlink_to(target)
            manifest={"format":"lv2","pluginId":"external","adapterExecutable":str(link),"hostSystems":[platform.system()],"hostArchitectures":[platform.machine()],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+hashlib.sha256(target.read_bytes()).hexdigest()}
            with self.assertRaisesRegex(ValueError,"regular executable"):IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",manifest)

    def test_external_manifest_rejects_incompatible_host_protocol_and_hash(self):
        base={"format":"clap","pluginId":"external","adapterExecutable":"/tmp/adapter","hostSystems":[platform.system()],"hostArchitectures":[platform.machine()],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+"0"*64}
        with self.assertRaisesRegex(ValueError,"host system"):validate_plugin_manifest({**base,"hostSystems":["Windows" if platform.system()!="Windows" else "Darwin"]})
        with self.assertRaisesRegex(ValueError,"host architecture"):validate_plugin_manifest({**base,"hostArchitectures":["not-this-machine"]})
        with self.assertRaisesRegex(ValueError,"protocol 1"):validate_plugin_manifest({**base,"adapterProtocolVersions":[2]})
        with self.assertRaisesRegex(ValueError,"adapterSha256"):validate_plugin_manifest({**base,"adapterSha256":"sha256:nope"})

    def test_windows_manifest_requires_signed_file_identity_attestation(self):
        base={"format":"vst3","pluginId":"win","adapterExecutable":"C:/StageForge/adapter.exe","hostSystems":["Windows"],"hostArchitectures":["AMD64"],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+"1"*64}
        with self.assertRaisesRegex(ValueError,"Windows platformLaunchAttestation"):
            validate_plugin_manifest(base,host_system="Windows",host_machine="AMD64")
        manifest={**base,"platformLaunchAttestations":{"Windows":{"mode":"windows-authenticode-fileid-v1","publisherCertificateSha256":"sha256:"+"2"*64,"fileIdentityRequired":True}}}
        normalized=validate_plugin_manifest(manifest,host_system="Windows",host_machine="AMD64")
        self.assertEqual(normalized["platformLaunchAttestation"]["mode"],"windows-authenticode-fileid-v1")
        self.assertTrue(normalized["platformLaunchAttestation"]["fileIdentityRequired"])

    def test_windows_launch_evidence_binds_hash_publisher_and_file_identity(self):
        manifest={"format":"vst3","pluginId":"win","adapterExecutable":"C:/StageForge/adapter.exe","hostSystems":["Windows"],"hostArchitectures":["AMD64"],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+"1"*64,"platformLaunchAttestations":{"Windows":{"mode":"windows-authenticode-fileid-v1","publisherCertificateSha256":"sha256:"+"2"*64,"fileIdentityRequired":True}}}
        evidence={"adapterSha256":"sha256:"+"1"*64,"signatureStatus":"Valid","publisherCertificateSha256":"sha256:"+"2"*64,"volumeSerial":"VOL-1","fileId":"FILE-123"}
        result=validate_platform_launch_evidence(manifest,evidence,host_system="Windows")
        self.assertEqual(result["binding"],"windows-authenticode-fileid-v1")
        with self.assertRaisesRegex(ValueError,"publisher certificate mismatch"):
            validate_platform_launch_evidence(manifest,{**evidence,"publisherCertificateSha256":"sha256:"+"3"*64},host_system="Windows")
        with self.assertRaisesRegex(ValueError,"file identity"):
            validate_platform_launch_evidence(manifest,{**evidence,"fileId":""},host_system="Windows")

    def test_macos_manifest_and_launch_evidence_require_exact_codesign_identity(self):
        manifest={"format":"audio-unit","pluginId":"mac","adapterExecutable":"/Applications/StageForge Adapter.app/Contents/MacOS/adapter","hostSystems":["Darwin"],"hostArchitectures":["arm64"],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+"4"*64,"platformLaunchAttestations":{"Darwin":{"mode":"macos-codesign-cdhash-v1","teamId":"ABC123DEF4","codeDirectoryHash":"cdhash:"+"5"*40}}}
        normalized=validate_plugin_manifest(manifest,host_system="Darwin",host_machine="arm64")
        self.assertEqual(normalized["platformLaunchAttestation"]["teamId"],"ABC123DEF4")
        evidence={"adapterSha256":"sha256:"+"4"*64,"signatureValid":True,"teamId":"ABC123DEF4","codeDirectoryHash":"cdhash:"+"5"*40,"fileId":"dev:1:inode:22"}
        self.assertEqual(validate_platform_launch_evidence(manifest,evidence,host_system="Darwin")["binding"],"macos-codesign-cdhash-v1")
        with self.assertRaisesRegex(ValueError,"code directory hash mismatch"):
            validate_platform_launch_evidence(manifest,{**evidence,"codeDirectoryHash":"cdhash:"+"6"*40},host_system="Darwin")
        with self.assertRaisesRegex(ValueError,"Team ID mismatch"):
            validate_platform_launch_evidence(manifest,{**evidence,"teamId":"ZZZ999YYY8"},host_system="Darwin")

    def test_nonlinux_external_launch_refuses_path_digest_fallback(self):
        with tempfile.TemporaryDirectory() as raw:
            adapter=Path(raw)/"adapter";adapter.write_text("#!/bin/sh\nexit 0\n");adapter.chmod(0o700)
            manifest={"format":"clap","pluginId":"win","adapterExecutable":str(adapter),"hostSystems":["Windows"],"hostArchitectures":["AMD64"],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+hashlib.sha256(adapter.read_bytes()).hexdigest(),"platformLaunchAttestations":{"Windows":{"mode":"windows-authenticode-fileid-v1","publisherCertificateSha256":"sha256:"+"2"*64,"fileIdentityRequired":True}}}
            with patch("plugin_host.platform.system",return_value="Windows"),patch("plugin_host.platform.machine",return_value="AMD64"),patch("plugin_host.sys.platform","win32"):
                with self.assertRaisesRegex(RuntimeError,"launch binding is not implemented"):
                    IsolatedPluginHost(adapter,manifest)

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux external adapter launch binding")
    def test_external_adapter_hash_mismatch_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as raw:
            adapter=Path(raw)/"adapter";adapter.write_text("#!/bin/sh\nexit 0\n");adapter.chmod(0o700)
            manifest={"format":"lv2","pluginId":"external","adapterExecutable":str(adapter),"hostSystems":[platform.system()],"hostArchitectures":[platform.machine()],"adapterProtocolVersions":[1],"adapterSha256":"sha256:"+"0"*64,**platform_attestation()}
            with self.assertRaisesRegex(ValueError,"hash mismatch"):IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",manifest)

    def test_timeout_is_reaped_and_audited_before_bypass(self):
        with tempfile.TemporaryDirectory() as raw:
            script=Path(raw)/"slow.py";script.write_text("import sys,time\nfor line in sys.stdin:\n time.sleep(1)\n")
            host=IsolatedPluginHost(script,{"format":"builtin","pluginId":"slow"},timeout=.02)
            try:
                with self.assertRaises(TimeoutError):host.start()
                status=host.status();self.assertTrue(status["bypassed"]);self.assertEqual(status["failures"],1);self.assertEqual(status["audit"]["timeouts"],1);self.assertGreaterEqual(status["audit"]["forcedKills"],1);self.assertIsNone(host.process);self.assertIsNone(status["scratchResourceId"])
            finally:host.close()

    def test_malformed_output_fails_closed_and_is_audited(self):
        with tempfile.TemporaryDirectory() as raw:
            script=Path(raw)/"bad.py";script.write_text("import sys\nfor line in sys.stdin: print('not-json',flush=True)\n")
            host=IsolatedPluginHost(script,{"format":"builtin","pluginId":"bad"})
            try:
                with self.assertRaises(ValueError):host.start()
                self.assertEqual(host.status()["audit"]["invalidResponses"],1);self.assertIsNone(host.process);self.assertIsNone(host.status()["scratchResourceId"])
            finally:host.close()

    def test_mismatched_handshake_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            script=Path(raw)/"wrong.py";script.write_text("import json,sys\nfor line in sys.stdin:\n r=json.loads(line);print(json.dumps({'ok':True,'requestId':r['requestId'],'active':True,'protocolVersion':1,'pluginId':'wrong','format':'builtin','supportsProcess':True,'latencyFrames':0}),flush=True)\n")
            host=IsolatedPluginHost(script,{"format":"builtin","pluginId":"expected"})
            try:
                with self.assertRaisesRegex(ValueError,"handshake mismatch"):host.start()
                self.assertTrue(host.status()["bypassed"]);self.assertEqual(host.status()["audit"]["invalidResponses"],1)
            finally:host.close()

    def test_plugin_receives_private_scratch_and_close_removes_it(self):
        with tempfile.TemporaryDirectory() as raw,patch.dict("os.environ",{"STAGEFORGE_PLUGIN_SCRATCH_DIR":raw}):
            script=Path(raw)/"scratch.py";script.write_text("import json,os,sys\nfor line in sys.stdin:\n r=json.loads(line);open(os.path.join(os.environ['STAGEFORGE_PLUGIN_INSTANCE_SCRATCH_DIR'],'used'),'w').write('x');print(json.dumps({'ok':True,'requestId':r['requestId'],'active':True,'protocolVersion':1,'pluginId':'scratch','format':'builtin','supportsProcess':True,'latencyFrames':0}),flush=True)\n")
            host=IsolatedPluginHost(script,{"format":"builtin","pluginId":"scratch"})
            try:
                status=host.start();self.assertIsNotNone(status["scratchResourceId"]);self.assertEqual(plugin_host_scratch_status()["liveCount"],1)
            finally:host.close()
            self.assertEqual(plugin_host_scratch_status()["resourceCount"],0)

    def test_scratch_cleanup_keeps_unknown_and_removes_exact_dead_owner(self):
        import json
        from staged_resources import _process_identity
        with tempfile.TemporaryDirectory() as raw,patch.dict("os.environ",{"STAGEFORGE_PLUGIN_SCRATCH_DIR":raw}):
            from temporary_ownership import create_owner_manifest
            root=Path(raw);dead=root/"host-dead";dead.mkdir();create_owner_manifest(dead/"owner.json",dead,resource_class="plugin-host-scratch",purpose="isolated-effect-host");owner=json.loads((dead/"owner.json").read_text());owner["pid"]=99999999;(dead/"owner.json").write_text(json.dumps(owner));(dead/"bytes").write_bytes(b"x")
            unknown=root/"host-unknown";unknown.mkdir();(unknown/"owner.json").write_text("broken")
            result=plugin_host_scratch_cleanup();self.assertEqual(result["reclaimedCount"],1);self.assertFalse(dead.exists());self.assertTrue(unknown.exists());self.assertEqual(result["unknownOwnerCount"],1)

    def test_stderr_flood_cannot_block_handshake(self):
        with tempfile.TemporaryDirectory() as raw,patch.dict("os.environ",{"STAGEFORGE_PLUGIN_SCRATCH_DIR":raw}):
            script=Path(raw)/"stderr.py";script.write_text("import json,sys\nfor line in sys.stdin:\n r=json.loads(line);sys.stderr.write('x'*1048576);sys.stderr.flush();print(json.dumps({'ok':True,'requestId':r['requestId'],'active':True,'protocolVersion':1,'pluginId':'stderr','format':'builtin','supportsProcess':True,'latencyFrames':0}),flush=True)\n")
            host=IsolatedPluginHost(script,{"format":"builtin","pluginId":"stderr"},timeout=.5)
            try:self.assertFalse(host.start()["bypassed"])
            finally:host.close()


    def test_scratch_manifest_durability_failure_cleans_directory_before_launch(self):
        with tempfile.TemporaryDirectory() as raw,patch.dict("os.environ",{"STAGEFORGE_PLUGIN_SCRATCH_DIR":raw}),patch("plugin_host.fsync_directory",side_effect=OSError("sync")):
            host=IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",{"format":"builtin","pluginId":"durability"})
            try:
                with self.assertRaisesRegex(OSError,"sync"):host.start()
                self.assertIsNone(host.process);self.assertIsNone(host.scratch_path);self.assertEqual(list(Path(raw).glob("host-*")),[])
            finally:host.close()

    def test_invalid_scratch_budget_fails_before_launch(self):
        for value in ("broken","0","1048575"):
            with self.subTest(value=value),tempfile.TemporaryDirectory() as raw,patch.dict("os.environ",{"STAGEFORGE_PLUGIN_SCRATCH_DIR":raw,"STAGEFORGE_PLUGIN_SCRATCH_MAX_BYTES":value}):
                host=IsolatedPluginHost(ROOT/"scripts/stageforge-plugin-host.py",{"format":"builtin","pluginId":"budget"})
                try:
                    with self.assertRaisesRegex(RuntimeError,"STAGEFORGE_PLUGIN_SCRATCH_MAX_BYTES"):host.start()
                    self.assertIsNone(host.process)
                finally:host.close()

if __name__=="__main__":unittest.main()
