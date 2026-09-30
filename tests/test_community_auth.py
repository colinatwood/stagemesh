import re
from email import policy
from email.parser import BytesParser
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from admin_mail import AdminMailer
from community_auth import CommunitySessionManager
from community_governance import CommunityGovernance
from runtime import StageMeshRuntime


class CommunitySessionManagerTests(unittest.TestCase):
    def test_signed_session_verifies_and_rejects_tamper_or_expiry(self):
        manager = CommunitySessionManager(b's' * 32, ttl_seconds=120)
        issued = manager.issue('user-a', 3, now_ns=1_000_000_000_000)
        session = manager.verify(issued['sessionToken'], now_ns=1_030_000_000_000)
        self.assertEqual(session.account_id, 'user-a')
        self.assertEqual(session.auth_generation, 3)
        token = issued['sessionToken']
        tampered = ('A' if token[0] != 'A' else 'B') + token[1:]
        with self.assertRaises(PermissionError):
            manager.verify(tampered, now_ns=1_030_000_000_000)
        with self.assertRaises(PermissionError):
            manager.verify(token, now_ns=1_121_000_000_000)

    def test_ttl_is_bounded(self):
        self.assertEqual(CommunitySessionManager(b's' * 32, ttl_seconds=1).ttl_seconds, 60)
        self.assertEqual(CommunitySessionManager(b's' * 32, ttl_seconds=999999).ttl_seconds, 86400)


class CommunityAccountAuthTests(unittest.TestCase):
    def test_old_accounts_migrate_to_generation_one_and_revocation_increments(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'STAGEMESH_ADMIN_EMAIL_MODE': 'outbox'}, clear=False):
            gov = CommunityGovernance(Path(tmp), AdminMailer(Path(tmp)))
            gov.upsert_account({'id': 'user-a', 'email': 'a@example.test'})
            # Simulate a pre-checkpoint account record that did not persist authGeneration.
            gov.accounts['user-a'].pop('authGeneration', None)
            gov._save()
            restored = CommunityGovernance(Path(tmp), AdminMailer(Path(tmp)))
            account = restored.authenticated_account('user-a')
            self.assertEqual(account['authGeneration'], 1)
            revoked = restored.revoke_account_sessions('user-a')
            self.assertEqual(revoked['authGeneration'], 2)

    def test_email_or_active_state_change_revokes_existing_generation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {'STAGEMESH_ADMIN_EMAIL_MODE': 'outbox'}, clear=False):
            gov = CommunityGovernance(Path(tmp), AdminMailer(Path(tmp)))
            first = gov.upsert_account({'id': 'user-a', 'email': 'a@example.test'})
            self.assertEqual(first['authGeneration'], 1)
            same = gov.upsert_account({'id': 'user-a', 'email': 'a@example.test', 'displayName': 'A'})
            self.assertEqual(same['authGeneration'], 1)
            changed = gov.upsert_account({'id': 'user-a', 'email': 'new@example.test'})
            self.assertEqual(changed['authGeneration'], 2)
            disabled = gov.upsert_account({'id': 'user-a', 'email': 'new@example.test', 'active': False})
            self.assertEqual(disabled['authGeneration'], 3)

    def test_runtime_session_votes_without_magic_link_token_and_revocation_fences_old_session(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            'os.environ', {'STAGEMESH_NATIVE_ENGINE': 'off', 'STAGEMESH_ADMIN_EMAIL_MODE': 'outbox'}, clear=False
        ):
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime.community_upsert_account({'id': 'user-a', 'email': 'a@example.test'})
                runtime.community_create_proposal({'id': 'proposal-a', 'title': 'Session vote'})
                runtime.community_issue_vote_emails(
                    'proposal-a', {'userIds': ['user-a'], 'windowHours': 24, 'baseUrl': 'https://stagemesh.test'}
                )
                session = runtime.community_issue_session('user-a')
                vote = runtime.community_cast_vote(
                    {'sessionToken': session['sessionToken'], 'proposalId': 'proposal-a', 'choice': 'yes'}, None
                )
                self.assertEqual(vote['choice'], 'yes')
                self.assertEqual(vote['authMethod'], 'account-session')
                self.assertTrue(vote['publicRecordRef'].startswith('upp-public-record:record-'))

                runtime.community_create_proposal({'id': 'proposal-b', 'title': 'Revoked session'})
                runtime.community_issue_vote_emails(
                    'proposal-b', {'userIds': ['user-a'], 'windowHours': 24, 'baseUrl': 'https://stagemesh.test'}
                )
                runtime.community_revoke_sessions('user-a')
                with self.assertRaises(PermissionError):
                    runtime.community_cast_vote(
                        {'sessionToken': session['sessionToken'], 'proposalId': 'proposal-b', 'choice': 'yes'}, None
                    )
            finally:
                runtime.close()

    def test_session_vote_requires_exactly_one_active_account_invitation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            'os.environ', {'STAGEMESH_NATIVE_ENGINE': 'off', 'STAGEMESH_ADMIN_EMAIL_MODE': 'outbox'}, clear=False
        ):
            runtime = StageMeshRuntime(Path(tmp))
            try:
                runtime.community_upsert_account({'id': 'user-a', 'email': 'a@example.test'})
                runtime.community_create_proposal({'id': 'proposal-a', 'title': 'Invitation required'})
                session = runtime.community_issue_session('user-a')
                with self.assertRaises(PermissionError):
                    runtime.community_cast_vote(
                        {'sessionToken': session['sessionToken'], 'proposalId': 'proposal-a', 'choice': 'yes'}, None
                    )
                runtime.community_issue_vote_emails(
                    'proposal-a', {'userIds': ['user-a'], 'windowHours': 24, 'baseUrl': 'https://stagemesh.test'}
                )
                runtime.community_issue_vote_emails(
                    'proposal-a', {'userIds': ['user-a'], 'windowHours': 24, 'baseUrl': 'https://stagemesh.test'}
                )
                with self.assertRaises(PermissionError):
                    runtime.community_cast_vote(
                        {'sessionToken': session['sessionToken'], 'proposalId': 'proposal-a', 'choice': 'yes'}, None
                    )
            finally:
                runtime.close()


if __name__ == '__main__':
    unittest.main()
