import hashlib,json,tempfile,unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from qualification_bundle import create_plan,result_template
from qualification_review import create_review
from qualification_status import summarize_submissions

class QualificationStatusTests(unittest.TestCase):
    def engine(self,root):
        path=Path(root)/'stagemesh_engine';path.write_bytes(b'engine');path.chmod(0o755);return path
    def key(self,root):
        path=Path(root)/'review-key.json';path.write_text(json.dumps({'version':1,'keyId':'reviewer-1','reviewerIdHash':'sha256:'+'9'*64,'secret':'k'*48}));path.chmod(0o600);return path
    def submission(self,plan,root,task,decision='approve'):
        task_dir=root/task;art=task_dir/'artifacts';art.mkdir(parents=True)
        result=result_template(plan,task);result['runner']={'runnerIdHash':'sha256:'+'4'*64,'platform':'external-host'}
        result['passed']=decision!='reject';result['claims']={name:(decision!='reject') for name in result['claims']}
        for i,item in enumerate(result['artifacts']):
            data=(item['kind']+'\n').encode();name=f'{i}.bin';(art/name).write_bytes(data)
            item.update({'name':name,'relativePath':name,'sha256':'sha256:'+hashlib.sha256(data).hexdigest(),'sizeBytes':len(data)})
        (task_dir/'result.json').write_text(json.dumps(result))
        review=create_review(plan=plan,result=result,artifact_root=art,review_key_file=self.review_key,decision=decision,reviewed_at='2026-09-14T14:00:00Z')
        (task_dir/'review.json').write_text(json.dumps(review));return task_dir

    def setUp(self): self.review_key=None

    def test_empty_intake_reports_every_task_pending(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);plan=create_plan(root=ROOT,engine_path=self.engine(root));self.review_key=self.key(root);subs=root/'submissions'
            status=summarize_submissions(plan=plan,submissions_root=subs,review_key_file=self.review_key)
            self.assertEqual(status['counts']['pending'],len(plan['tasks']));self.assertFalse(status['allTasksApproved'])

    def test_approved_submission_is_backlog_review_eligible(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);plan=create_plan(root=ROOT,engine_path=self.engine(root));self.review_key=self.key(root);subs=root/'submissions';self.submission(plan,subs,'assistive-technology')
            status=summarize_submissions(plan=plan,submissions_root=subs,review_key_file=self.review_key)
            row=next(item for item in status['tasks'] if item['taskId']=='assistive-technology')
            self.assertEqual(row['status'],'approved');self.assertTrue(row['eligibleForBacklogReview']);self.assertEqual(status['counts']['approved'],1)

    def test_evidence_changed_after_review_becomes_invalid(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);plan=create_plan(root=ROOT,engine_path=self.engine(root));self.review_key=self.key(root);subs=root/'submissions';task=self.submission(plan,subs,'lan-security')
            next((task/'artifacts').iterdir()).write_text('tampered')
            status=summarize_submissions(plan=plan,submissions_root=subs,review_key_file=self.review_key)
            row=next(item for item in status['tasks'] if item['taskId']=='lan-security')
            self.assertEqual(row['status'],'invalid');self.assertFalse(row['eligibleForBacklogReview'])

    def test_needs_evidence_review_is_preserved(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);plan=create_plan(root=ROOT,engine_path=self.engine(root));self.review_key=self.key(root);subs=root/'submissions'
            task='assistive-technology';task_dir=subs/task;art=task_dir/'artifacts';art.mkdir(parents=True)
            result=result_template(plan,task);result['runner']={'runnerIdHash':'sha256:'+'4'*64,'platform':'at-host'}
            for i,item in enumerate(result['artifacts']):
                data=b'partial\n';name=f'{i}.bin';(art/name).write_bytes(data);item.update({'name':name,'relativePath':name,'sha256':'sha256:'+hashlib.sha256(data).hexdigest(),'sizeBytes':len(data)})
            (task_dir/'result.json').write_text(json.dumps(result))
            review=create_review(plan=plan,result=result,artifact_root=art,review_key_file=self.review_key,decision='needs-evidence',reviewed_at='2026-09-14T14:00:00Z')
            (task_dir/'review.json').write_text(json.dumps(review))
            status=summarize_submissions(plan=plan,submissions_root=subs,review_key_file=self.review_key)
            row=next(item for item in status['tasks'] if item['taskId']==task)
            self.assertEqual(row['status'],'needs-evidence');self.assertFalse(row['eligibleForBacklogReview'])

if __name__=='__main__':unittest.main()
