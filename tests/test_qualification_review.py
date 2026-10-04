import hashlib,json,os,tempfile,unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from qualification_bundle import create_plan,result_template,validate_result
from qualification_review import create_review,validate_review,verify_artifacts,load_review_key

class QualificationReviewTests(unittest.TestCase):
    def engine(self,root):
        path=Path(root)/'stagemesh_engine';path.write_bytes(b'engine');path.chmod(0o755);return path
    def key(self,root):
        path=Path(root)/'review-key.json'
        path.write_text(json.dumps({'version':1,'keyId':'release-reviewer-1','reviewerIdHash':'sha256:'+'7'*64,'secret':'s'*48}))
        path.chmod(0o600);return path
    def passing_result(self,plan,task,artifact_root):
        result=result_template(plan,task);result['runner']={'runnerIdHash':'sha256:'+'4'*64,'platform':'qualification-host'}
        result['passed']=True;result['claims']={name:True for name in result['claims']}
        for index,item in enumerate(result['artifacts']):
            name=f'evidence-{index}.json';data=(item['kind']+'\n').encode();(artifact_root/name).write_bytes(data)
            item.update({'name':name,'relativePath':name,'sha256':'sha256:'+hashlib.sha256(data).hexdigest(),'sizeBytes':len(data)})
        validate_result(plan,result);return result

    def test_approve_binds_exact_result_artifacts_and_authenticated_reviewer(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);plan=create_plan(root=ROOT,engine_path=self.engine(root));art=root/'art';art.mkdir();result=self.passing_result(plan,'independent-witness',art)
            review=create_review(plan=plan,result=result,artifact_root=art,review_key_file=self.key(root),decision='approve',reviewed_at='2026-09-14T12:00:00Z',notes=['reviewed'])
            self.assertTrue(review['eligibleForBacklogReview']);self.assertEqual(len(review['artifactVerification']),3)
            accepted=validate_review(plan=plan,result=result,review=review,review_key_file=root/'review-key.json')
            self.assertTrue(accepted['accepted']);self.assertTrue(accepted['eligibleForBacklogReview'])

    def test_review_rejects_tampered_artifact_and_path_escape(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);plan=create_plan(root=ROOT,engine_path=self.engine(root));art=root/'art';art.mkdir();result=self.passing_result(plan,'lan-security',art)
            (art/result['artifacts'][0]['relativePath']).write_text('tampered')
            with self.assertRaisesRegex(ValueError,'digest/size mismatch'):verify_artifacts(result,art)
            result=self.passing_result(plan,'lan-security',art);result['artifacts'][0]['relativePath']='../escape.json'
            with self.assertRaisesRegex(ValueError,'safe relative path'):validate_result(plan,result)

    def test_review_signature_and_result_digest_detect_tampering(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);plan=create_plan(root=ROOT,engine_path=self.engine(root));art=root/'art';art.mkdir();result=self.passing_result(plan,'assistive-technology',art);key=self.key(root)
            review=create_review(plan=plan,result=result,artifact_root=art,review_key_file=key,decision='approve',reviewed_at='2026-09-14T12:00:00+00:00')
            bad={**review,'decision':'reject'}
            with self.assertRaisesRegex(PermissionError,'signature'):validate_review(plan=plan,result=result,review=bad,review_key_file=key)
            mutated=json.loads(json.dumps(result));mutated['notes']=['changed']
            with self.assertRaisesRegex(ValueError,'reviewed result'):validate_review(plan=plan,result=mutated,review=review,review_key_file=key)

    def test_review_key_requires_private_permissions(self):
        with tempfile.TemporaryDirectory() as raw:
            key=self.key(Path(raw));key.chmod(0o644)
            with self.assertRaisesRegex(PermissionError,'unavailable'):load_review_key(key)

    def test_approve_rejects_non_passing_result(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);plan=create_plan(root=ROOT,engine_path=self.engine(root));art=root/'art';art.mkdir();result=result_template(plan,'lan-security');key=self.key(root)
            with self.assertRaisesRegex(ValueError,'cannot approve'):create_review(plan=plan,result=result,artifact_root=art,review_key_file=key,decision='approve',reviewed_at='2026-09-14T12:00:00Z')

if __name__=='__main__':unittest.main()
