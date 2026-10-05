import re
import json
from email import policy
from email.parser import BytesParser
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from admin_mail import AdminMailer
from community_governance import CommunityGovernance, durable_fraction, hype_value
from runtime import StageForgeRuntime


class HypeLogicTests(unittest.TestCase):
    def test_day_one_is_full_hype_and_day_365_is_zero(self):
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(hype_value(created, created + timedelta(days=1)), 1.0)
        self.assertEqual(durable_fraction(created, created + timedelta(days=1)), 0.0)
        self.assertEqual(hype_value(created, created + timedelta(days=365)), 0.0)
        self.assertEqual(durable_fraction(created, created + timedelta(days=365)), 1.0)

    def test_hype_never_becomes_choice_vote_weight(self):
        created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        halfway = hype_value(created, created + timedelta(days=183))
        self.assertGreater(halfway, 0.0)
        self.assertLess(halfway, 1.0)
        self.assertAlmostEqual(halfway + durable_fraction(created, created + timedelta(days=183)), 1.0, places=8)


class CommunityGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        with patch.dict('os.environ', {'STAGEFORGE_ADMIN_EMAIL_MODE': 'outbox'}, clear=False):
            self.gov = CommunityGovernance(self.root, AdminMailer(self.root))
        self.gov.upsert_account({'id': 'user-a', 'email': 'a@example.test', 'displayName': 'A'})
        self.proposal = self.gov.create_proposal({'id': 'proposal-a', 'title': 'Change the thing', 'description': 'A test change.'})

    def tearDown(self):
        self.tmp.cleanup()

    def _issue_and_token(self, hours=48):
        issued = self.gov.issue_vote_emails('proposal-a', ['user-a'], window_hours=hours, base_url='https://stageforge.test')
        self.assertEqual(issued['issued'][0]['status'], 'sent')
        eml_path = next((self.root / 'admin-email-outbox').glob('*.eml'))
        eml = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes()).get_content()
        match = re.search(r'token=([A-Za-z0-9_\-]+)', eml)
        self.assertIsNotNone(match)
        return issued['issued'][0], match.group(1)

    def _tokens_by_recipient(self):
        result = {}
        for eml_path in (self.root / 'admin-email-outbox').glob('*.eml'):
            message = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
            text = message.get_content()
            match = re.search(r'token=([A-Za-z0-9_\-]+)', text)
            if match:
                result[str(message['To'])] = match.group(1)
        return result

    def test_email_issue_time_sets_immutable_window(self):
        invitation, _ = self._issue_and_token(hours=36)
        sent = datetime.fromisoformat(invitation['sentAt'].replace('Z', '+00:00'))
        expires = datetime.fromisoformat(invitation['expiresAt'].replace('Z', '+00:00'))
        self.assertEqual(expires - sent, timedelta(hours=36))
        self.assertEqual(invitation['windowHours'], 36)

    def test_vote_is_account_bound_when_auth_required(self):
        _, token = self._issue_and_token()
        with self.assertRaises(PermissionError):
            self.gov.cast_vote(token, 'yes', authenticated_user_id='someone-else')
        vote = self.gov.cast_vote(token, 'yes', authenticated_user_id='user-a')
        self.assertEqual(vote['rawVoteUnits'], 1.0)
        self.assertEqual(vote['hypeVoteUnits'], 0.0)

    def test_token_only_mode_is_explicit_development_escape_hatch(self):
        _, token = self._issue_and_token()
        vote = self.gov.cast_vote(token, 'no', authenticated_user_id=None, allow_token_only=True)
        self.assertEqual(vote['choice'], 'no')

    def test_proposal_version_change_invalidates_emailed_ballot(self):
        _, token = self._issue_and_token()
        self.gov.update_proposal('proposal-a', {'description': 'Materially revised language.'})
        with self.assertRaises(PermissionError):
            self.gov.cast_vote(token, 'yes', authenticated_user_id='user-a')

    def test_vote_matures_after_window_without_becoming_hype_vote(self):
        _, token = self._issue_and_token(hours=1)
        self.gov.cast_vote(token, 'yes', authenticated_user_id='user-a')
        # Move the proposal's public origin one year into the past. The cast vote
        # remains one raw vote; only its common durable fraction changes.
        one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
        self.gov.proposals['proposal-a']['createdAt'] = one_year_ago.isoformat().replace('+00:00', 'Z')
        tally = self.gov.proposal_tally('proposal-a', datetime.now(timezone.utc) + timedelta(hours=2))
        self.assertEqual(tally['rawVotes']['yes'], 1)
        self.assertEqual(tally['hypeVoteUnits'], 0.0)
        self.assertEqual(tally['durableVoteUnits']['yes'], 1.0)


    def test_admin_cannot_adopt_before_binding_maturity(self):
        self._issue_and_token()
        with self.assertRaises(ValueError):
            self.gov.update_proposal('proposal-a', {'status': 'adopted'})

    def test_monitor_reports_hype_separately_from_vote_choice(self):
        self._issue_and_token()
        monitor = self.gov.monitor()
        self.assertEqual(len(monitor['proposals']), 1)
        item = monitor['proposals'][0]
        self.assertGreaterEqual(item['hype'], 0.0)
        self.assertLessEqual(item['hype'], 1.0)
        self.assertFalse(item['bindingChangeReady'])

    def test_ratified_governance_policy_change_applies_exact_payload(self):
        self.gov.upsert_account({'id': 'user-b', 'email': 'b@example.test'})
        self.gov.upsert_account({'id': 'user-c', 'email': 'c@example.test'})
        self.gov.update_proposal('proposal-a', {
            'change': {'kind': 'community-governance-policy', 'payload': {'minRawVotes': 5}},
            'description': 'Raise the raw participation floor to five.'
        })
        self.gov.issue_vote_emails('proposal-a', ['user-a', 'user-b', 'user-c'], window_hours=48, base_url='https://stageforge.test')
        tokens = self._tokens_by_recipient()
        for uid, email in [('user-a','a@example.test'), ('user-b','b@example.test'), ('user-c','c@example.test')]:
            self.gov.cast_vote(tokens[email], 'yes', authenticated_user_id=uid)
        self.gov.proposals['proposal-a']['createdAt'] = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat().replace('+00:00', 'Z')
        adopted = self.gov.update_proposal('proposal-a', {'status': 'adopted'})
        self.assertEqual(adopted['status'], 'adopted')
        result = self.gov.apply_ratified_governance_policy('proposal-a')
        self.assertTrue(result['applied'])
        self.assertEqual(result['policy']['minRawVotes'], 5)
        self.assertEqual(self.gov.proposals['proposal-a']['appliedChangeHash'], self.gov.proposals['proposal-a']['change']['hash'])

    def test_runtime_locks_direct_policy_edits_after_community_process_begins(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'STAGEMESH_NATIVE_ENGINE': 'off'}, clear=False):
            runtime = StageForgeRuntime(Path(tmp))
            try:
                runtime.community_create_proposal({'id': 'lock-proposal', 'title': 'Begin governance'})
                with self.assertRaises(PermissionError):
                    runtime.community_patch_policy({'minRawVotes': 1})
                with self.assertRaises(PermissionError):
                    runtime.patch_technology({'policy': {'maxMandatoryCoreExtensions': 1}}, None, None)
            finally:
                runtime.close()

    def test_active_email_window_cannot_be_admin_closed(self):
        self._issue_and_token(hours=48)
        with self.assertRaises(ValueError):
            self.gov.update_proposal('proposal-a', {'status': 'closed'})

    def test_adopted_change_payload_is_immutable(self):
        self.gov.upsert_account({'id': 'user-b', 'email': 'b@example.test'})
        self.gov.upsert_account({'id': 'user-c', 'email': 'c@example.test'})
        self.gov.update_proposal('proposal-a', {'change': {'kind': 'community-governance-policy', 'payload': {'minRawVotes': 5}}})
        self.gov.issue_vote_emails('proposal-a', ['user-a', 'user-b', 'user-c'], window_hours=48, base_url='https://stageforge.test')
        tokens = self._tokens_by_recipient()
        for uid, email in [('user-a','a@example.test'), ('user-b','b@example.test'), ('user-c','c@example.test')]:
            self.gov.cast_vote(tokens[email], 'yes', authenticated_user_id=uid)
        self.gov.proposals['proposal-a']['createdAt'] = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat().replace('+00:00', 'Z')
        self.gov.update_proposal('proposal-a', {'status': 'adopted'})
        with self.assertRaises(ValueError):
            self.gov.update_proposal('proposal-a', {'change': {'kind': 'community-governance-policy', 'payload': {'minRawVotes': 1}}})

    def test_persistence_keeps_vote_and_email_window(self):
        invitation, token = self._issue_and_token()
        with patch.dict('os.environ', {'STAGEFORGE_ADMIN_EMAIL_MODE': 'outbox'}, clear=False):
            restored = CommunityGovernance(self.root, AdminMailer(self.root))
        detail = restored.snapshot(detail=True)
        self.assertEqual(detail['voteCount'], 0)
        self.assertEqual(detail['invitations'][0]['sentAt'], invitation['sentAt'])
        self.assertEqual(detail['invitations'][0]['expiresAt'], invitation['expiresAt'])
        self.assertNotIn('tokenHash', detail['invitations'][0])
        # The private persisted hash survives even though the API view redacts it.
        vote = restored.cast_vote(token, 'abstain', authenticated_user_id='user-a')
        self.assertEqual(vote['choice'], 'abstain')


class CommunityPublicRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.events = []

        def record(record_type, payload):
            self.events.append((record_type, json.loads(json.dumps(payload))))
            index = len(self.events)
            return {'recordId': f'record-{index:020d}', 'recordHash': f'{index:064x}'}

        with patch.dict('os.environ', {'STAGEFORGE_ADMIN_EMAIL_MODE': 'outbox'}, clear=False):
            self.gov = CommunityGovernance(self.root, AdminMailer(self.root), public_record_append=record)
        for uid, email in [('user-a', 'a@example.test'), ('user-b', 'b@example.test'), ('user-c', 'c@example.test')]:
            self.gov.upsert_account({'id': uid, 'email': email})
        self.gov.create_proposal({
            'id': 'proposal-public',
            'title': 'Auditable change',
            'description': 'Public wording, private individual ballots.',
            'change': {'kind': 'community-governance-policy', 'payload': {'minRawVotes': 4}},
        })

    def tearDown(self):
        self.tmp.cleanup()

    def _tokens_by_recipient(self):
        result = {}
        for eml_path in (self.root / 'admin-email-outbox').glob('*.eml'):
            message = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
            match = re.search(r'token=([A-Za-z0-9_\-]+)', message.get_content())
            if match:
                result[str(message['To'])] = match.group(1)
        return result

    def test_public_record_redacts_recipient_identity_and_individual_choice(self):
        self.gov.issue_vote_emails(
            'proposal-public', ['user-a'], window_hours=24, base_url='https://stageforge.test'
        )
        token = self._tokens_by_recipient()['a@example.test']
        vote = self.gov.cast_vote(token, 'yes', authenticated_user_id='user-a')
        self.assertTrue(vote['publicRecordRef'].startswith('upp-public-record:record-'))

        invitation = next(payload for kind, payload in self.events if kind == 'community-vote-invitation')
        self.assertNotIn('userId', invitation)
        self.assertNotIn('email', invitation)
        self.assertNotIn('tokenHash', invitation)

        ballot = next(payload for kind, payload in self.events if kind == 'community-ballot')
        self.assertNotIn('userId', ballot)
        self.assertNotIn('choice', ballot)
        self.assertNotIn('choiceSalt', ballot)
        self.assertEqual(len(ballot['choiceCommitmentSha256']), 64)
        self.assertTrue(ballot['publicBallotId'].startswith('ballot-'))

        detail = self.gov.snapshot(detail=True)
        self.assertNotIn('choiceSalt', detail['votes'][0])
        self.assertEqual(detail['votes'][0]['choice'], 'yes')

    def test_ratification_record_contains_aggregate_not_voter_choice_map(self):
        self.gov.issue_vote_emails(
            'proposal-public', ['user-a', 'user-b', 'user-c'], window_hours=24, base_url='https://stageforge.test'
        )
        tokens = self._tokens_by_recipient()
        for uid, email in [('user-a', 'a@example.test'), ('user-b', 'b@example.test'), ('user-c', 'c@example.test')]:
            self.gov.cast_vote(tokens[email], 'yes', authenticated_user_id=uid)
        self.gov.proposals['proposal-public']['createdAt'] = (
            datetime.now(timezone.utc) - timedelta(days=365)
        ).isoformat().replace('+00:00', 'Z')
        adopted = self.gov.update_proposal('proposal-public', {'status': 'adopted'})
        self.assertEqual(adopted['status'], 'adopted')
        self.assertTrue(adopted['ratificationRecordRef'].startswith('upp-public-record:record-'))

        ratification = next(payload for kind, payload in self.events if kind == 'community-ratification')
        self.assertEqual(ratification['rawVotes'], {'yes': 3, 'no': 0, 'abstain': 0})
        encoded = json.dumps(ratification, sort_keys=True)
        self.assertNotIn('user-a', encoded)
        self.assertNotIn('a@example.test', encoded)
        self.assertNotIn('choiceCommitmentSha256', encoded)
        self.assertEqual(len(ratification['ballotRecordRefs']), 3)
        self.assertEqual(len(ratification['invitationRecordRefs']), 3)

    def test_missing_record_blocks_progress_until_reconciled(self):
        calls = {'count': 0}

        def flaky(record_type, payload):
            calls['count'] += 1
            if calls['count'] == 1:
                raise OSError('ledger unavailable')
            return {'recordId': f'record-{calls["count"]:020d}', 'recordHash': f'{calls["count"]:064x}'}

        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'STAGEFORGE_ADMIN_EMAIL_MODE': 'outbox'}, clear=False):
            gov = CommunityGovernance(Path(tmp), AdminMailer(Path(tmp)), public_record_append=flaky)
            proposal = gov.create_proposal({'id': 'pending', 'title': 'Pending evidence'})
            self.assertTrue(proposal['publicRecordPending'])
            with self.assertRaises(RuntimeError):
                gov.update_proposal('pending', {'description': 'must not skip the missing version evidence'})
            repaired = gov.reconcile_public_record('pending')
            self.assertEqual(repaired['pending'], 0)
            updated = gov.update_proposal('pending', {'description': 'now safely versioned'})
            self.assertFalse(updated['publicRecordPending'])

    def test_runtime_public_record_contains_privacy_preserving_governance_events(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            'os.environ', {'STAGEMESH_NATIVE_ENGINE': 'off', 'STAGEFORGE_ADMIN_EMAIL_MODE': 'outbox'}, clear=False
        ):
            runtime = StageForgeRuntime(Path(tmp))
            try:
                runtime.community_upsert_account({'id': 'runtime-user', 'email': 'runtime@example.test'})
                proposal = runtime.community_create_proposal({'id': 'runtime-proposal', 'title': 'Runtime audit'})
                self.assertTrue(proposal['publicRecordRef'].startswith('upp-public-record:record-'))
                issued = runtime.community_issue_vote_emails(
                    'runtime-proposal', {'userIds': ['runtime-user'], 'windowHours': 24, 'baseUrl': 'https://stageforge.test'}
                )
                eml_path = next((Path(tmp) / 'admin-email-outbox').glob('*.eml'))
                message = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
                token = re.search(r'token=([A-Za-z0-9_\-]+)', message.get_content()).group(1)
                runtime.community_cast_vote({'token': token, 'choice': 'no'}, 'runtime-user')

                records = [json.loads(line) for line in (Path(tmp) / 'public-record.jsonl').read_text('utf-8').splitlines() if line]
                invite_payload = next(row['payload'] for row in records if row['recordType'] == 'community-vote-invitation')
                ballot_payload = next(row['payload'] for row in records if row['recordType'] == 'community-ballot')
                self.assertNotIn('email', invite_payload)
                self.assertNotIn('userId', invite_payload)
                self.assertNotIn('choice', ballot_payload)
                self.assertNotIn('userId', ballot_payload)
                self.assertTrue(runtime.public_record_status()['ok'])
                self.assertEqual(issued['issued'][0]['proposalId'], 'runtime-proposal')
            finally:
                runtime.close()


if __name__ == '__main__':
    unittest.main()
