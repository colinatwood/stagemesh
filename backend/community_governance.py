from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from admin_mail import AdminMailer


DEFAULT_COMMUNITY_POLICY: dict[str, Any] = {
    'hypeStartValue': 1.0,
    'hypeDayOne': 1,
    'hypeZeroDay': 365,
    'defaultVoteWindowHours': 168,
    'minRawVotes': 3,
    'minApprovalRatio': 0.60,
    'minDurableVoteUnits': 3.0,
    'requireAllIssuedWindowsClosedForBinding': True,
    'requireAuthenticatedAccount': True,
    'urgentProvisionalMaxDays': 30,
}

CHOICES = {'yes', 'no', 'abstain'}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _change_record(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('proposal change must be an object')
    kind = str(value.get('kind', '')).strip()[:128]
    payload = value.get('payload')
    if not kind or not isinstance(payload, dict):
        raise ValueError('proposal change requires kind and object payload')
    canonical = json.dumps({'kind': kind, 'payload': payload}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return {'kind': kind, 'payload': payload, 'hash': hashlib.sha256(canonical).hexdigest()}


def hype_value(created_at: str | datetime, at: str | datetime | None = None, *, zero_day: int = 365) -> float:
    """Linear hype decay: day 1 = 1.0, zero_day = 0.0.

    Hype never contributes vote units. The complementary durable fraction is
    what may mature into binding change weight.
    """
    created = _parse_time(created_at)
    now = _parse_time(at) if at is not None else _utc_now()
    elapsed_days = max(0.0, (now - created).total_seconds() / 86400.0)
    if elapsed_days <= 1.0:
        return 1.0
    span = max(1.0, float(zero_day - 1))
    return round(max(0.0, min(1.0, 1.0 - ((elapsed_days - 1.0) / span))), 9)


def durable_fraction(created_at: str | datetime, at: str | datetime | None = None, *, zero_day: int = 365) -> float:
    return round(1.0 - hype_value(created_at, at, zero_day=zero_day), 9)


class CommunityGovernance:
    """Community-control state kept outside show-critical replication.

    Raw votes are never reweighted against one another. Hype is a proposal-age
    maturity factor applied equally to every cast choice, so it can delay
    binding authority but cannot push a yes/no choice in either direction.
    """

    def __init__(
        self,
        data_dir: Path,
        mailer: AdminMailer,
        *,
        public_record_append: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.path = data_dir / 'community-governance.json'
        self._lock = RLock()
        self.mailer = mailer
        self._public_record_append = public_record_append
        self.policy = dict(DEFAULT_COMMUNITY_POLICY)
        self.accounts: dict[str, dict[str, Any]] = {}
        self.proposals: dict[str, dict[str, Any]] = {}
        self.invitations: dict[str, dict[str, Any]] = {}
        self.votes: dict[str, dict[str, Any]] = {}
        self.revision = 1
        self._load()

    @property
    def public_record_required(self) -> bool:
        return self._public_record_append is not None

    @staticmethod
    def _reference_uri(reference: dict[str, Any]) -> str:
        record_id = str(reference.get('recordId', '')).strip()
        record_hash = str(reference.get('recordHash', '')).strip()
        if not record_id.startswith('record-') or len(record_hash) != 64:
            raise ValueError('invalid public-record reference')
        return f'upp-public-record:{record_id}:{record_hash}'

    def _append_public_record(self, record_type: str, payload: dict[str, Any]) -> str | None:
        if self._public_record_append is None:
            return None
        reference = self._public_record_append(record_type, payload)
        return self._reference_uri(reference)

    @staticmethod
    def _proposal_public_payload(proposal: dict[str, Any]) -> dict[str, Any]:
        change = proposal.get('change')
        return {
            'version': 1,
            'proposalId': str(proposal.get('id', '')),
            'proposalVersion': int(proposal.get('version', 1)),
            'title': str(proposal.get('title', '')),
            'description': str(proposal.get('description', '')),
            'scope': str(proposal.get('scope', '')),
            'createdAt': proposal.get('createdAt'),
            'updatedAt': proposal.get('updatedAt'),
            'status': str(proposal.get('status', '')),
            'provisional': bool(proposal.get('provisional', False)),
            'provisionalExpiresAt': proposal.get('provisionalExpiresAt'),
            'change': json.loads(json.dumps(change)) if isinstance(change, dict) else None,
        }

    @staticmethod
    def _invitation_public_payload(invite: dict[str, Any]) -> dict[str, Any]:
        # Deliberately excludes userId, email, tokenHash and message content.
        return {
            'version': 1,
            'invitationId': str(invite.get('id', '')),
            'proposalId': str(invite.get('proposalId', '')),
            'proposalVersion': int(invite.get('proposalVersion', 0)),
            'status': str(invite.get('status', '')),
            'windowHours': int(invite.get('windowHours', 0)),
            'sentAt': invite.get('sentAt'),
            'expiresAt': invite.get('expiresAt'),
            'deliveryAcceptedAt': invite.get('deliveryAcceptedAt'),
            'deliveryMode': invite.get('deliveryMode'),
        }

    @staticmethod
    def _ballot_public_payload(vote: dict[str, Any]) -> dict[str, Any]:
        # The individual choice and account identity remain private. The public
        # record carries only an opaque ballot id and a salted commitment that can
        # be selectively opened later if a governance audit requires it.
        return {
            'version': 1,
            'publicBallotId': str(vote.get('publicBallotId', '')),
            'proposalId': str(vote.get('proposalId', '')),
            'proposalVersion': int(vote.get('proposalVersion', 0)),
            'invitationId': str(vote.get('invitationId', '')),
            'castAt': vote.get('castAt'),
            'choiceCommitmentSha256': str(vote.get('choiceCommitmentSha256', '')),
            'rawVoteUnits': 1.0,
        }

    def _record_proposal_version(self, proposal: dict[str, Any]) -> bool:
        if self._public_record_append is None:
            return True
        proposal['publicRecordPending'] = True
        self._save()
        try:
            proposal['publicRecordRef'] = self._append_public_record(
                'community-proposal-version', self._proposal_public_payload(proposal)
            )
            proposal['publicRecordPending'] = False
            self._save()
            return True
        except Exception:
            self._save()
            return False

    def _record_invitation(self, invite: dict[str, Any]) -> bool:
        if self._public_record_append is None:
            return True
        invite['publicRecordPending'] = True
        self._save()
        try:
            invite['publicRecordRef'] = self._append_public_record(
                'community-vote-invitation', self._invitation_public_payload(invite)
            )
            invite['publicRecordPending'] = False
            self._save()
            return True
        except Exception:
            self._save()
            return False

    def _ensure_vote_commitment(self, vote: dict[str, Any]) -> None:
        if vote.get('publicBallotId') and vote.get('choiceSalt') and vote.get('choiceCommitmentSha256'):
            return
        ballot_id = 'ballot-' + secrets.token_hex(16)
        salt = secrets.token_hex(24)
        material = {
            'purpose': 'org.upp.community-ballot-choice/1',
            'publicBallotId': ballot_id,
            'proposalId': str(vote.get('proposalId', '')),
            'proposalVersion': int(vote.get('proposalVersion', 0)),
            'choice': str(vote.get('choice', '')),
            'salt': salt,
        }
        canonical = json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        vote['publicBallotId'] = ballot_id
        vote['choiceSalt'] = salt
        vote['choiceCommitmentSha256'] = hashlib.sha256(canonical).hexdigest()

    def _record_vote(self, vote: dict[str, Any]) -> bool:
        if self._public_record_append is None:
            return True
        self._ensure_vote_commitment(vote)
        vote['publicRecordPending'] = True
        self._save()
        try:
            vote['publicRecordRef'] = self._append_public_record(
                'community-ballot', self._ballot_public_payload(vote)
            )
            vote['publicRecordPending'] = False
            self._save()
            return True
        except Exception:
            self._save()
            return False

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            value = json.loads(self.path.read_text('utf-8'))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(value, dict):
            return
        self.policy = {**DEFAULT_COMMUNITY_POLICY, **(value.get('policy') or {})}
        self.accounts = {str(x['id']): x for x in value.get('accounts', []) if isinstance(x, dict) and x.get('id')}
        self.proposals = {str(x['id']): x for x in value.get('proposals', []) if isinstance(x, dict) and x.get('id')}
        self.invitations = {str(x['id']): x for x in value.get('invitations', []) if isinstance(x, dict) and x.get('id')}
        self.votes = {str(x['id']): x for x in value.get('votes', []) if isinstance(x, dict) and x.get('id')}
        try:
            self.revision = max(1, int(value.get('revision', 1)))
        except (TypeError, ValueError):
            self.revision = 1

    def _persistence_snapshot(self) -> dict[str, Any]:
        return {
            'revision': self.revision,
            'policy': dict(self.policy),
            'accounts': [dict(x) for x in self.accounts.values()],
            'proposals': [dict(x) for x in self.proposals.values()],
            'invitations': [dict(x) for x in self.invitations.values()],
            'votes': [dict(x) for x in self.votes.values()],
        }

    def _save(self) -> None:
        data = json.dumps(self._persistence_snapshot(), indent=2, sort_keys=True, ensure_ascii=False) + '\n'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix='.community-governance-', suffix='.json', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _changed(self) -> None:
        self.revision += 1
        self._save()

    def snapshot(self, *, detail: bool = False) -> dict[str, Any]:
        with self._lock:
            base = {
                'revision': self.revision,
                'policy': dict(self.policy),
                'accountCount': len(self.accounts),
                'proposalCount': len(self.proposals),
                'invitationCount': len(self.invitations),
                'voteCount': len(self.votes),
                'mailer': self.mailer.status(),
                'publicRecordRequired': self.public_record_required,
            }
            if detail:
                base.update({
                    'accounts': [dict(x) for x in self.accounts.values()],
                    'proposals': [dict(x) for x in self.proposals.values()],
                    'invitations': [{k: v for k, v in x.items() if k != 'tokenHash'} for x in self.invitations.values()],
                    'votes': [{k: v for k, v in x.items() if k != 'choiceSalt'} for x in self.votes.values()],
                })
            return base

    def patch_policy(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            known = dict(self.policy)
            known.update(data)
            known['hypeStartValue'] = 1.0
            known['hypeDayOne'] = 1
            known['hypeZeroDay'] = max(2, min(3650, int(known.get('hypeZeroDay', 365))))
            known['defaultVoteWindowHours'] = max(1, min(8760, int(known.get('defaultVoteWindowHours', 168))))
            known['minRawVotes'] = max(1, int(known.get('minRawVotes', 3)))
            known['minApprovalRatio'] = max(0.5, min(1.0, float(known.get('minApprovalRatio', 0.60))))
            known['minDurableVoteUnits'] = max(0.0, float(known.get('minDurableVoteUnits', 1.0)))
            known['requireAllIssuedWindowsClosedForBinding'] = bool(known.get('requireAllIssuedWindowsClosedForBinding', True))
            known['requireAuthenticatedAccount'] = bool(known.get('requireAuthenticatedAccount', True))
            known['urgentProvisionalMaxDays'] = max(1, min(365, int(known.get('urgentProvisionalMaxDays', 30))))
            if known != self.policy:
                self.policy = known
                self._changed()
            return self.snapshot()

    def upsert_account(self, data: dict[str, Any]) -> dict[str, Any]:
        account_id = str(data.get('id', '')).strip()[:128]
        email = str(data.get('email', '')).strip()[:320]
        if not account_id or '@' not in email:
            raise ValueError('account id and valid email are required')
        with self._lock:
            existing = self.accounts.get(account_id, {})
            account = {
                **existing,
                'id': account_id,
                'email': email,
                'displayName': str(data.get('displayName', existing.get('displayName', ''))).strip()[:160],
                'active': bool(data.get('active', existing.get('active', True))),
                'authGeneration': max(1, int(existing.get('authGeneration', 1))),
            }
            if existing and (account['email'] != existing.get('email') or account['active'] != existing.get('active')):
                account['authGeneration'] = max(1, int(existing.get('authGeneration', 1))) + 1
            self.accounts[account_id] = account
            self._changed()
            return dict(account)

    def authenticated_account(self, account_id: str) -> dict[str, Any]:
        account_id = str(account_id).strip()
        with self._lock:
            account = self.accounts.get(account_id)
            if not account or not account.get('active'):
                raise PermissionError('active community account not found')
            if 'authGeneration' not in account:
                account['authGeneration'] = 1
                self._save()
            return dict(account)

    def revoke_account_sessions(self, account_id: str) -> dict[str, Any]:
        account_id = str(account_id).strip()
        with self._lock:
            account = self.accounts.get(account_id)
            if not account:
                raise KeyError(account_id)
            account['authGeneration'] = max(1, int(account.get('authGeneration', 1))) + 1
            self._changed()
            return {k: v for k, v in account.items() if k != 'email'}

    def create_proposal(self, data: dict[str, Any]) -> dict[str, Any]:
        proposal_id = str(data.get('id') or f'proposal-{secrets.token_hex(6)}').strip()[:160]
        title = str(data.get('title', '')).strip()[:240]
        if not title:
            raise ValueError('proposal title is required')
        with self._lock:
            if proposal_id in self.proposals:
                raise ValueError('proposal id already exists')
            now = _utc_now()
            proposal = {
                'id': proposal_id,
                'version': 1,
                'title': title,
                'description': str(data.get('description', '')).strip()[:4000],
                'scope': str(data.get('scope', 'platform-change')).strip()[:80],
                'createdAt': _iso(now),
                'status': 'open',
                'provisional': bool(data.get('provisional', False)),
                'provisionalExpiresAt': _iso(now + timedelta(days=int(self.policy['urgentProvisionalMaxDays']))) if data.get('provisional') else None,
                'change': _change_record(data.get('change')),
                'appliedAt': None,
            }
            self.proposals[proposal_id] = proposal
            self._changed()
            if self._public_record_append is not None:
                self._record_proposal_version(proposal)
            return dict(proposal)

    def update_proposal(self, proposal_id: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                raise KeyError(proposal_id)
            if (self._public_record_append is not None and proposal.get('publicRecordPending')
                    and any(key in data for key in ('title', 'description', 'scope', 'change', 'status'))):
                raise RuntimeError('proposal public-record evidence is pending; reconcile before further mutation')
            if proposal.get('status') == 'adopted' and any(key in data for key in ('title', 'description', 'scope', 'change', 'status')):
                requested_status = str(data.get('status', 'adopted')).strip().lower()
                if any(key in data for key in ('title', 'description', 'scope', 'change')) or requested_status != 'adopted':
                    raise ValueError('adopted proposal is immutable; supersede it with a new proposal')
            changed = False
            if 'status' in data:
                status = str(data['status']).strip().lower()
                if status not in {'open', 'closed', 'adopted', 'rejected', 'superseded'}:
                    raise ValueError('invalid proposal status')
                if status != proposal.get('status') and status in {'closed', 'rejected', 'superseded'}:
                    now = _utc_now()
                    active = [
                        invite for invite in self.invitations.values()
                        if invite.get('proposalId') == proposal_id
                        and int(invite.get('proposalVersion', 0)) == int(proposal.get('version', 1))
                        and invite.get('status') == 'sent'
                        and invite.get('expiresAt')
                        and now <= _parse_time(invite['expiresAt'])
                    ]
                    if active:
                        raise ValueError('proposal status cannot close while emailed voting windows are active')
                if status == 'adopted' and proposal.get('status') != 'adopted':
                    tally = self.proposal_tally(proposal_id)
                    if not tally['bindingChangeReady']:
                        raise ValueError('proposal cannot be adopted until community vote is binding-ready: ' + '; '.join(tally['bindingBlockers']))
                    if self._public_record_append is not None:
                        ratification_payload = {
                            'version': 1,
                            'proposalId': proposal_id,
                            'proposalVersion': int(proposal.get('version', 1)),
                            'proposalRecordRef': proposal.get('publicRecordRef'),
                            'invitationRecordRefs': sorted(
                                str(item.get('publicRecordRef')) for item in self.invitations.values()
                                if item.get('proposalId') == proposal_id
                                and int(item.get('proposalVersion', 0)) == int(proposal.get('version', 1))
                                and item.get('publicRecordRef')
                            ),
                            'ballotRecordRefs': sorted(
                                str(item.get('publicRecordRef')) for item in self.votes.values()
                                if item.get('proposalId') == proposal_id
                                and int(item.get('proposalVersion', 0)) == int(proposal.get('version', 1))
                                and item.get('publicRecordRef')
                            ),
                            'rawVotes': dict(tally['rawVotes']),
                            'totalRawVotes': int(tally['totalRawVotes']),
                            'approvalRatio': float(tally['approvalRatio']),
                            'totalDurableVoteUnits': float(tally['totalDurableVoteUnits']),
                            'evaluatedAt': tally['evaluatedAt'],
                            'changeHash': (proposal.get('change') or {}).get('hash') if isinstance(proposal.get('change'), dict) else None,
                        }
                        proposal['ratificationRecordRef'] = self._append_public_record(
                            'community-ratification', ratification_payload
                        )
                if status != proposal['status']:
                    proposal['status'] = status
                    changed = True
            if any(key in data for key in ('title', 'description', 'scope', 'change')):
                # Material wording/change-payload updates create a new version;
                # old invitations cannot authorize text or operations that were
                # not in the emailed version.
                for key, limit in (('title', 240), ('description', 4000), ('scope', 80)):
                    if key in data:
                        proposal[key] = str(data[key]).strip()[:limit]
                if 'change' in data:
                    proposal['change'] = _change_record(data.get('change'))
                    proposal['appliedAt'] = None
                proposal['version'] = int(proposal.get('version', 1)) + 1
                proposal['updatedAt'] = _iso(_utc_now())
                changed = True
            if changed:
                self._changed()
                if any(key in data for key in ('title', 'description', 'scope', 'change')) and self._public_record_append is not None:
                    self._record_proposal_version(proposal)
            return dict(proposal)

    def _proposal_hype(self, proposal: dict[str, Any], at: datetime | None = None) -> tuple[float, float]:
        hype = hype_value(proposal['createdAt'], at, zero_day=int(self.policy['hypeZeroDay']))
        return hype, round(1.0 - hype, 9)

    def issue_vote_emails(self, proposal_id: str, user_ids: list[str], *, window_hours: int | None, base_url: str) -> dict[str, Any]:
        with self._lock:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                raise KeyError(proposal_id)
            if proposal.get('status') != 'open':
                raise ValueError('proposal is not open for voting')
            hours = int(window_hours if window_hours is not None else self.policy['defaultVoteWindowHours'])
            hours = max(1, min(8760, hours))
            prepared: list[tuple[dict[str, Any], str]] = []
            for user_id in user_ids:
                account = self.accounts.get(str(user_id))
                if not account or not account.get('active'):
                    raise ValueError(f'active user account not found: {user_id}')
                token = secrets.token_urlsafe(32)
                invitation_id = f'invite-{secrets.token_hex(8)}'
                invite = {
                    'id': invitation_id,
                    'proposalId': proposal_id,
                    'proposalVersion': int(proposal['version']),
                    'userId': account['id'],
                    'email': account['email'],
                    'status': 'pending-send',
                    'windowHours': hours,
                    'sentAt': None,
                    'expiresAt': None,
                    'messageId': invitation_id,
                    'tokenHash': hashlib.sha256(token.encode('utf-8')).hexdigest(),
                }
                self.invitations[invitation_id] = invite
                prepared.append((invite, token))
            self._changed()

        results = []
        for invite, token in prepared:
            with self._lock:
                proposal = self.proposals[invite['proposalId']]
                account = self.accounts[invite['userId']]
            vote_url = f"{base_url.rstrip('/')}/vote.html?token={token}"
            sent_at = _utc_now()
            expires_at = sent_at + timedelta(hours=int(invite['windowHours']))
            subject = f"StageMesh admin vote: {proposal['title']}"
            text = (
                f"StageMesh community change vote\n\n"
                f"Proposal: {proposal['title']}\n"
                f"Proposal ID: {proposal['id']}\n"
                f"Version: {proposal['version']}\n\n"
                f"{proposal.get('description', '')}\n\n"
                f"Voting window opens: {_iso(sent_at)}\n"
                f"Voting window closes: {_iso(expires_at)}\n"
                f"Window length: {invite['windowHours']} hours\n"
                f"Vote: {vote_url}\n\n"
                f"Raw vote: one account, one vote. Hype contributes zero vote units.\n"
                f"Binding maturity is calculated from proposal age: day 1 hype=1.0, day {self.policy['hypeZeroDay']} hype=0.0.\n"
            )
            try:
                delivery = self.mailer.send(recipient=account['email'], subject=subject, text=text, message_id=invite['messageId'])
                with self._lock:
                    current = self.invitations[invite['id']]
                    current['status'] = 'sent'
                    current['sentAt'] = _iso(sent_at)
                    current['expiresAt'] = _iso(expires_at)
                    current['deliveryAcceptedAt'] = delivery.get('acceptedAt')
                    current['deliveryMode'] = delivery.get('mode')
                    self._changed()
                    if self._public_record_append is not None:
                        self._record_invitation(current)
                    results.append({k: v for k, v in current.items() if k != 'tokenHash'})
            except Exception as exc:
                with self._lock:
                    current = self.invitations[invite['id']]
                    current['status'] = 'delivery-failed'
                    current['deliveryError'] = str(exc)[:500]
                    self._changed()
                    if self._public_record_append is not None:
                        self._record_invitation(current)
                results.append({'id': invite['id'], 'status': 'delivery-failed', 'error': str(exc)})
        return {'proposalId': proposal_id, 'issued': results}

    def vote_context(self, token: str) -> dict[str, Any]:
        token_hash = hashlib.sha256(str(token).encode('utf-8')).hexdigest()
        now = _utc_now()
        with self._lock:
            invite = next((x for x in self.invitations.values() if secrets.compare_digest(str(x.get('tokenHash', '')), token_hash)), None)
            if not invite:
                raise PermissionError('invalid vote credential')
            proposal = self.proposals.get(invite['proposalId'])
            if not proposal:
                raise PermissionError('proposal is unavailable')
            hype, durable = self._proposal_hype(proposal, now)
            return {
                'proposal': {k: proposal.get(k) for k in ('id', 'version', 'title', 'description', 'scope', 'createdAt', 'status')},
                'invitation': {k: invite.get(k) for k in ('id', 'proposalVersion', 'userId', 'status', 'sentAt', 'expiresAt', 'windowHours')},
                'hype': hype,
                'durableFraction': durable,
                'hypeVoteUnits': 0.0,
                'requiresAuthenticatedAccount': bool(self.policy.get('requireAuthenticatedAccount', True)),
            }

    def cast_vote(self, token: str, choice: str, *, authenticated_user_id: str | None, allow_token_only: bool = False) -> dict[str, Any]:
        token_hash = hashlib.sha256(str(token).encode('utf-8')).hexdigest()
        choice_n = str(choice).strip().lower()
        if choice_n not in CHOICES:
            raise ValueError('choice must be yes, no, or abstain')
        now = _utc_now()
        with self._lock:
            invite = next((x for x in self.invitations.values() if secrets.compare_digest(str(x.get('tokenHash', '')), token_hash)), None)
            if not invite:
                raise PermissionError('invalid vote credential')
            if invite.get('status') not in {'sent', 'voted'}:
                raise PermissionError('vote invitation is not active')
            if invite.get('status') == 'voted':
                raise PermissionError('vote credential has already been used')
            proposal = self.proposals.get(invite['proposalId'])
            if not proposal or int(proposal.get('version', 1)) != int(invite.get('proposalVersion', 0)):
                raise PermissionError('proposal version changed after this email was issued')
            if proposal.get('status') != 'open':
                raise PermissionError('proposal is no longer open')
            sent_at = _parse_time(invite['sentAt'])
            expires_at = _parse_time(invite['expiresAt'])
            if now < sent_at or now > expires_at:
                invite['status'] = 'expired'
                self._changed()
                raise PermissionError('voting window has expired')
            require_auth = bool(self.policy.get('requireAuthenticatedAccount', True)) and not allow_token_only
            if require_auth and (not authenticated_user_id or authenticated_user_id != invite['userId']):
                raise PermissionError('authenticated user account does not match the emailed invitation')
            vote_id = f"vote-{invite['proposalId']}-{invite['userId']}-v{invite['proposalVersion']}"
            if vote_id in self.votes:
                raise PermissionError('this account already voted on this proposal version')
            hype, durable = self._proposal_hype(proposal, now)
            vote = {
                'id': vote_id,
                'proposalId': invite['proposalId'],
                'proposalVersion': invite['proposalVersion'],
                'invitationId': invite['id'],
                'userId': invite['userId'],
                'choice': choice_n,
                'castAt': _iso(now),
                'hypeAtCast': hype,
                'durableFractionAtCast': durable,
                'rawVoteUnits': 1.0,
                'hypeVoteUnits': 0.0,
            }
            self._ensure_vote_commitment(vote)
            self.votes[vote_id] = vote
            invite['status'] = 'voted'
            invite['votedAt'] = vote['castAt']
            self._changed()
            if self._public_record_append is not None:
                self._record_vote(vote)
            return dict(vote)

    def cast_account_vote(self, proposal_id: str, choice: str, *, account_id: str) -> dict[str, Any]:
        account_id = str(account_id).strip()
        choice_n = str(choice).strip().lower()
        if choice_n not in CHOICES:
            raise ValueError('choice must be yes, no, or abstain')
        now = _utc_now()
        with self._lock:
            account = self.accounts.get(account_id)
            if not account or not account.get('active'):
                raise PermissionError('active community account not found')
            proposal = self.proposals.get(str(proposal_id))
            if not proposal or proposal.get('status') != 'open':
                raise PermissionError('proposal is not open')
            current_version = int(proposal.get('version', 1))
            active = []
            for invite in self.invitations.values():
                if (invite.get('proposalId') != proposal.get('id') or invite.get('userId') != account_id
                        or int(invite.get('proposalVersion', 0)) != current_version or invite.get('status') != 'sent'
                        or not invite.get('sentAt') or not invite.get('expiresAt')):
                    continue
                if _parse_time(invite['sentAt']) <= now <= _parse_time(invite['expiresAt']):
                    active.append(invite)
            if len(active) != 1:
                if not active:
                    raise PermissionError('no active voting invitation exists for this account and proposal version')
                raise PermissionError('multiple active voting invitations exist for this account and proposal version')
            invite = active[0]
            vote_id = f"vote-{invite['proposalId']}-{account_id}-v{invite['proposalVersion']}"
            if vote_id in self.votes:
                raise PermissionError('this account already voted on this proposal version')
            hype, durable = self._proposal_hype(proposal, now)
            vote = {
                'id': vote_id,
                'proposalId': invite['proposalId'],
                'proposalVersion': invite['proposalVersion'],
                'invitationId': invite['id'],
                'userId': account_id,
                'choice': choice_n,
                'castAt': _iso(now),
                'hypeAtCast': hype,
                'durableFractionAtCast': durable,
                'rawVoteUnits': 1.0,
                'hypeVoteUnits': 0.0,
                'authMethod': 'account-session',
            }
            self._ensure_vote_commitment(vote)
            self.votes[vote_id] = vote
            invite['status'] = 'voted'
            invite['votedAt'] = vote['castAt']
            self._changed()
            if self._public_record_append is not None:
                self._record_vote(vote)
            return dict(vote)

    def reconcile_public_record(self, proposal_id: str | None = None) -> dict[str, Any]:
        if self._public_record_append is None:
            return {'required': False, 'published': 0, 'pending': 0}
        with self._lock:
            if proposal_id is not None and proposal_id not in self.proposals:
                raise KeyError(proposal_id)
            proposals = [self.proposals[proposal_id]] if proposal_id is not None else list(self.proposals.values())
            published = 0
            for proposal in proposals:
                current_version = int(proposal.get('version', 1))
                if proposal.get('publicRecordPending') or not proposal.get('publicRecordRef'):
                    if self._record_proposal_version(proposal):
                        published += 1
                for invite in self.invitations.values():
                    if (invite.get('proposalId') == proposal.get('id')
                            and int(invite.get('proposalVersion', 0)) == current_version
                            and (invite.get('publicRecordPending') or not invite.get('publicRecordRef'))):
                        if self._record_invitation(invite):
                            published += 1
                for vote in self.votes.values():
                    if (vote.get('proposalId') == proposal.get('id')
                            and int(vote.get('proposalVersion', 0)) == current_version
                            and (vote.get('publicRecordPending') or not vote.get('publicRecordRef'))):
                        if self._record_vote(vote):
                            published += 1
            pending = 0
            for proposal in proposals:
                version = int(proposal.get('version', 1))
                if proposal.get('publicRecordPending') or not proposal.get('publicRecordRef'):
                    pending += 1
                pending += sum(
                    1 for invite in self.invitations.values()
                    if invite.get('proposalId') == proposal.get('id') and int(invite.get('proposalVersion', 0)) == version
                    and (invite.get('publicRecordPending') or not invite.get('publicRecordRef'))
                )
                pending += sum(
                    1 for vote in self.votes.values()
                    if vote.get('proposalId') == proposal.get('id') and int(vote.get('proposalVersion', 0)) == version
                    and (vote.get('publicRecordPending') or not vote.get('publicRecordRef'))
                )
            return {'required': True, 'published': published, 'pending': pending}

    def bootstrap_policy_mutation_allowed(self) -> bool:
        with self._lock:
            return not self.proposals and not self.invitations and not self.votes

    def adopted_change(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                raise KeyError(proposal_id)
            if proposal.get('status') != 'adopted':
                raise ValueError('proposal is not adopted')
            if proposal.get('appliedAt'):
                raise ValueError('proposal change has already been applied')
            change = proposal.get('change')
            if not isinstance(change, dict):
                raise ValueError('proposal has no executable change payload')
            return {'proposalId': proposal_id, 'proposalVersion': proposal['version'], 'change': json.loads(json.dumps(change))}

    def apply_ratified_governance_policy(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            adopted = self.adopted_change(proposal_id)
            change = adopted['change']
            if change.get('kind') != 'community-governance-policy':
                raise ValueError('proposal does not contain a community-governance-policy change')
            self.patch_policy(change.get('payload') or {})
            proposal = self.proposals[proposal_id]
            proposal['appliedAt'] = _iso(_utc_now())
            proposal['appliedChangeHash'] = change.get('hash')
            self._changed()
            return {'applied': True, 'proposalId': proposal_id, 'changeHash': change.get('hash'), 'policy': dict(self.policy)}

    def mark_change_applied(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            adopted = self.adopted_change(proposal_id)
            proposal = self.proposals[proposal_id]
            proposal['appliedAt'] = _iso(_utc_now())
            proposal['appliedChangeHash'] = adopted['change'].get('hash')
            self._changed()
            return dict(proposal)

    def monitor(self, at: str | datetime | None = None) -> dict[str, Any]:
        now = _parse_time(at) if at is not None else _utc_now()
        with self._lock:
            items = []
            for proposal in self.proposals.values():
                hype, durable = self._proposal_hype(proposal, now)
                tally = self.proposal_tally(proposal['id'], now)
                created = _parse_time(proposal['createdAt'])
                zero_at = created + timedelta(days=int(self.policy['hypeZeroDay']))
                items.append({
                    'id': proposal['id'],
                    'version': proposal['version'],
                    'title': proposal['title'],
                    'status': proposal['status'],
                    'hype': hype,
                    'durableFraction': durable,
                    'hypeZeroAt': _iso(zero_at),
                    'totalRawVotes': tally['totalRawVotes'],
                    'totalDurableVoteUnits': tally['totalDurableVoteUnits'],
                    'bindingChangeReady': tally['bindingChangeReady'],
                    'bindingBlockers': tally['bindingBlockers'],
                })
            return {
                'evaluatedAt': _iso(now),
                'hypeRule': f"day 1 = 1.0; day {self.policy['hypeZeroDay']} = 0.0; hype contributes zero choice-vote units",
                'proposals': sorted(items, key=lambda x: x['id']),
            }

    def proposal_tally(self, proposal_id: str, at: str | datetime | None = None) -> dict[str, Any]:
        now = _parse_time(at) if at is not None else _utc_now()
        with self._lock:
            proposal = self.proposals.get(proposal_id)
            if not proposal:
                raise KeyError(proposal_id)
            votes = [x for x in self.votes.values() if x['proposalId'] == proposal_id and int(x['proposalVersion']) == int(proposal['version'])]
            invitations = [x for x in self.invitations.values() if x['proposalId'] == proposal_id and int(x['proposalVersion']) == int(proposal['version'])]
            raw = {choice: sum(1 for vote in votes if vote['choice'] == choice) for choice in CHOICES}
            hype, durable = self._proposal_hype(proposal, now)
            durable_units = {choice: round(raw[choice] * durable, 6) for choice in CHOICES}
            decisive = raw['yes'] + raw['no']
            approval_ratio = (raw['yes'] / decisive) if decisive else 0.0
            total_durable = round(sum(durable_units.values()), 6)
            active_windows = 0
            for invite in invitations:
                if invite.get('sentAt') and invite.get('expiresAt'):
                    if _parse_time(invite['sentAt']) <= now <= _parse_time(invite['expiresAt']) and invite.get('status') == 'sent':
                        active_windows += 1
            all_windows_closed = bool(invitations) and active_windows == 0 and all(
                invite.get('status') in {'voted', 'expired'} or (invite.get('expiresAt') and now > _parse_time(invite['expiresAt']))
                for invite in invitations
            )
            blockers = []
            if self._public_record_append is not None:
                if proposal.get('publicRecordPending') or not proposal.get('publicRecordRef'):
                    blockers.append('proposal version is missing Public Record evidence')
                if any(invite.get('publicRecordPending') or not invite.get('publicRecordRef') for invite in invitations):
                    blockers.append('one or more vote invitations are missing Public Record evidence')
                if any(vote.get('publicRecordPending') or not vote.get('publicRecordRef') for vote in votes):
                    blockers.append('one or more ballots are missing Public Record evidence')
            if len(votes) < int(self.policy['minRawVotes']):
                blockers.append('raw participation minimum not reached')
            if decisive == 0 or approval_ratio < float(self.policy['minApprovalRatio']):
                blockers.append('approval ratio minimum not reached')
            if total_durable < float(self.policy['minDurableVoteUnits']):
                blockers.append('durable vote-unit minimum not reached while proposal hype remains')
            if self.policy.get('requireAllIssuedWindowsClosedForBinding', True) and not all_windows_closed:
                blockers.append('issued voting windows are still open')
            binding_ready = not blockers
            return {
                'proposal': dict(proposal),
                'evaluatedAt': _iso(now),
                'hype': hype,
                'durableFraction': durable,
                'hypeVoteUnits': 0.0,
                'rawVotes': raw,
                'durableVoteUnits': durable_units,
                'totalRawVotes': len(votes),
                'totalDurableVoteUnits': total_durable,
                'approvalRatio': round(approval_ratio, 6),
                'invitationCount': len(invitations),
                'activeVotingWindows': active_windows,
                'allIssuedWindowsClosed': all_windows_closed,
                'bindingChangeReady': binding_ready,
                'bindingBlockers': blockers,
                'principle': 'one-account-one-raw-vote; hype adds zero choice weight; durability matures equally with proposal age',
            }
