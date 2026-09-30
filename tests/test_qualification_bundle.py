import hashlib,json,tempfile,unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from qualification_bundle import create_plan,result_template,source_fingerprint,validate_result

class QualificationBundleTests(unittest.TestCase):
    def engine(self,root):
        path=Path(root)/"stagemesh_engine";path.write_bytes(b"engine");path.chmod(0o755);return path

    def test_plan_is_exact_build_bound_and_contains_external_gates(self):
        with tempfile.TemporaryDirectory() as raw:
            engine=self.engine(raw);plan=create_plan(root=ROOT,engine_path=engine)
            self.assertEqual(plan["documentType"],"org.upp.external-qualification-plan")
            self.assertTrue(plan["planId"].startswith("sha256:"));self.assertTrue(plan["build"]["sourceFingerprint"].startswith("sha256:"))
            ids={item["taskId"] for item in plan["tasks"]}
            self.assertTrue({"independent-witness","lan-security","windows-platform","macos-platform","assistive-technology","stage-hardware"}.issubset(ids))
            self.assertFalse(plan["physicalOutputsArmed"]);self.assertTrue(all(item["requiredArtifacts"] for item in plan["tasks"]))

    def test_passing_result_requires_exact_plan_build_and_all_required_claims(self):
        with tempfile.TemporaryDirectory() as raw:
            plan=create_plan(root=ROOT,engine_path=self.engine(raw));result=result_template(plan,"assistive-technology")
            result["runner"]={"runnerIdHash":"sha256:"+"1"*64,"platform":"Windows 11 + NVDA"};result["passed"]=True
            result["claims"]={name:True for name in result["claims"]}
            for item in result["artifacts"]: item["sha256"]="sha256:"+"a"*64;item["sizeBytes"]=1
            accepted=validate_result(plan,result);self.assertTrue(accepted["accepted"]);self.assertTrue(accepted["passed"]);self.assertIn("UX-035",accepted["backlogIds"])
            with self.assertRaisesRegex(ValueError,"every task claim"):
                validate_result(plan,{**result,"claims":{**result["claims"],"screenReaderWorkflowQualified":False}})
            with self.assertRaisesRegex(ValueError,"exact build"):
                validate_result(plan,{**result,"planId":"sha256:"+"2"*64})

    def test_passing_result_requires_each_task_artifact_class(self):
        with tempfile.TemporaryDirectory() as raw:
            plan=create_plan(root=ROOT,engine_path=self.engine(raw));result=result_template(plan,"independent-witness")
            result["runner"]={"runnerIdHash":"sha256:"+"5"*64,"platform":"three hosts"};result["passed"]=True
            result["claims"]={name:True for name in result["claims"]}
            for item in result["artifacts"]: item["sha256"]="sha256:"+"a"*64;item["sizeBytes"]=1
            result["artifacts"]=result["artifacts"][:-1]
            with self.assertRaisesRegex(ValueError,"missing required artifacts"):
                validate_result(plan,result)

    def test_result_rejects_raw_runner_identity_and_unbounded_artifact_digest(self):
        with tempfile.TemporaryDirectory() as raw:
            plan=create_plan(root=ROOT,engine_path=self.engine(raw));result=result_template(plan,"lan-security")
            result["runner"]={"runnerIdHash":"hostname.example","platform":"Linux"}
            with self.assertRaisesRegex(ValueError,"hashed runner identity"):validate_result(plan,result)
            result["runner"]={"runnerIdHash":"sha256:"+"3"*64,"platform":"Linux"};result["artifacts"]=[{"kind":"qualification-report","name":"report","relativePath":"report.json","sha256":"bad","sizeBytes":1}]
            with self.assertRaisesRegex(ValueError,"artifact requires sha256"):validate_result(plan,result)

if __name__=="__main__":unittest.main()
