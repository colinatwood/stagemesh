"""Per-user HTTP control authorization policy for the development bridge.

This layer is intentionally separate from transport authentication. The API token
proves a caller reached the protected bridge; a trusted auth proxy token proves the
user identity header was injected by a reviewed proxy; this policy decides which
show-control mutations that user may perform.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from typing import Any, Mapping


ROLE_NAMES = frozenset({"observer", "performer", "operator", "authority", "admin"})
_MUTATING_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

# These routes retain their pre-existing narrower authorization mechanisms rather
# than inheriting ordinary show-control roles.
_SPECIALIZED_EXACT = frozenset({
    ("POST", "/api/v1/handoff/execution/shadow"),
    ("POST", "/api/v1/handoff/execution/live"),
    ("POST", "/api/v1/venue/reconciliation/report"),
    ("POST", "/api/v1/le-uwb/observations/uwb"),
    ("POST", "/api/v1/le-uwb/observations/le"),
    ("POST", "/api/v1/venue/profile"),
    ("POST", "/api/v1/replication/apply"),
    ("POST", "/api/v1/handoff/planned/peer-ready"),
    ("POST", "/api/v1/community/accounts"),
    ("POST", "/api/v1/community/proposals"),
    ("POST", "/api/v1/community/vote"),
    ("POST", "/api/v1/community/session"),
    ("POST", "/api/v1/community/session/revoke"),
    ("POST", "/api/v1/community/public-record/reconcile"),
    ("POST", "/api/v1/public-record/witness"),
    ("POST", "/api/v1/technology/conformance-receipt"),
    ("PATCH", "/api/v1/community/policy"),
})

_AUTHORITY_EXACT = frozenset({
    "/api/v1/witness/recover",
    "/api/v1/node/role",
    "/api/v1/failover/promote",
})
_AUTHORITY_PREFIXES = (
    "/api/v1/handoff/planned/",
    "/api/v1/venue/authority/",
)

_PLAYER_SUFFIX_ACTIONS = {
    "/monitor": "player.monitor.write",
    "/midi/input": "player.midi.write",
    "/notation/note": "player.notation.write",
    "/notation/clear": "player.notation.write",
    "/notation/settings": "player.notation.write",
}


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    actor: str | None
    roles: tuple[str, ...]
    action: str
    target: str | None
    reason: str


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _valid_identifier(value: str, maximum: int = 128) -> bool:
    return (isinstance(value, str) and value == value.strip() and 0 < len(value) <= maximum
            and all(ord(char) >= 32 and ord(char) != 127 for char in value))


def _read_private_json(path: str, maximum_bytes: int = 65536) -> Any:
    if not os.path.isabs(path):
        raise ValueError("absolute path required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) & 0o077 or before.st_size > maximum_bytes):
            raise ValueError("invalid file")
        data = stream.read(maximum_bytes + 1)
        after = os.fstat(stream.fileno())
        if (len(data) > maximum_bytes or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("changed file")
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs)


def authorization_policy(environ: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    """Load and validate the optional private per-user control-role policy.

    The file is intentionally re-read per HTTP request so an atomic replacement can
    revoke or change subsequent requests without restarting the bridge.
    """
    env = os.environ if environ is None else environ
    path = str(env.get("STAGEMESH_HTTP_AUTHORIZATION_FILE", "")).strip()
    if not path:
        return None
    try:
        value = _read_private_json(path)
        if not isinstance(value, dict) or set(value) != {"version", "users"} or value.get("version") != 1:
            raise ValueError("invalid policy root")
        users = value.get("users")
        if not isinstance(users, dict) or len(users) > 1024:
            raise ValueError("invalid users")
        normalized_users: dict[str, dict[str, Any]] = {}
        for actor, record in users.items():
            if not _valid_identifier(actor):
                raise ValueError("invalid actor")
            if not isinstance(record, dict) or not set(record) <= {"roles", "players"}:
                raise ValueError("invalid user record")
            roles = record.get("roles")
            players = record.get("players", [])
            if (not isinstance(roles, list) or not 1 <= len(roles) <= len(ROLE_NAMES)
                    or not all(isinstance(role, str) and role in ROLE_NAMES for role in roles)
                    or len(set(roles)) != len(roles)):
                raise ValueError("invalid roles")
            if (not isinstance(players, list) or len(players) > 32
                    or not all(_valid_identifier(player) for player in players)
                    or len(set(players)) != len(players)):
                raise ValueError("invalid players")
            normalized_users[actor] = {
                "roles": tuple(sorted(roles)),
                "players": frozenset(players),
            }
        return {"version": 1, "users": normalized_users}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, AttributeError, RecursionError):
        raise PermissionError("HTTP authorization file unavailable or invalid") from None


def specialized_authorization_route(method: str, path: str) -> bool:
    method = method.upper()
    if (method, path) in _SPECIALIZED_EXACT:
        return True
    if method in _MUTATING_METHODS and path.startswith("/api/v1/community/proposals/"):
        # Proposal update/email/apply routes retain the existing admin-token boundary.
        return True
    return False


def _player_action(path: str) -> tuple[str, str] | None:
    prefix = "/api/v1/players/"
    if not path.startswith(prefix):
        return None
    tail = path[len(prefix):]
    for suffix, action in _PLAYER_SUFFIX_ACTIONS.items():
        if tail.endswith(suffix):
            player = tail[:-len(suffix)].strip("/")
            if player and "/" not in player:
                return action, player
    return None


def classify_control_action(method: str, path: str) -> tuple[str, str | None, bool]:
    """Return (action, target, authority_sensitive) using bounded route metadata."""
    player = _player_action(path)
    if player is not None:
        return player[0], player[1], False
    if path in _AUTHORITY_EXACT or any(path.startswith(prefix) for prefix in _AUTHORITY_PREFIXES):
        tail = path[len("/api/v1/"):].replace("/", ".")
        return f"authority.{tail}", None, True
    if path == "/api/v1/handoff":
        return "authority.handoff.policy", None, True
    if path.startswith("/api/v1/"):
        domain = path[len("/api/v1/"):].split("/", 1)[0] or "api"
        return f"{domain}.control", None, False
    return "http.control", None, False


def authorize_control_request(policy: dict[str, Any] | None, actor: str | None,
                              method: str, path: str) -> AuthorizationDecision | None:
    """Authorize one ordinary API mutation when role policy is configured.

    ``None`` means role policy is disabled or the route uses a specialized existing
    credential boundary. Roles are additive: operator grants ordinary control,
    authority grants authority-transfer/fencing operations, performer grants only
    assigned player-local controls, and admin grants all ordinary control roles.
    """
    method = method.upper()
    if policy is None or method not in _MUTATING_METHODS or not path.startswith("/api/v1/"):
        return None
    if specialized_authorization_route(method, path):
        return None
    action, target, authority_sensitive = classify_control_action(method, path)
    if not actor:
        return AuthorizationDecision(False, None, (), action, target, "authenticated-user-required")
    record = policy.get("users", {}).get(actor)
    if record is None:
        return AuthorizationDecision(False, actor, (), action, target, "user-not-authorized")
    roles = tuple(record["roles"])
    role_set = set(roles)
    if "admin" in role_set:
        return AuthorizationDecision(True, actor, roles, action, target, "admin-role")
    if authority_sensitive:
        allowed = "authority" in role_set
        return AuthorizationDecision(allowed, actor, roles, action, target,
                                     "authority-role" if allowed else "authority-role-required")
    if target is not None:
        if "operator" in role_set:
            return AuthorizationDecision(True, actor, roles, action, target, "operator-role")
        if "performer" in role_set and target in record["players"]:
            return AuthorizationDecision(True, actor, roles, action, target, "assigned-performer")
        return AuthorizationDecision(False, actor, roles, action, target, "player-control-not-authorized")
    allowed = "operator" in role_set
    return AuthorizationDecision(allowed, actor, roles, action, target,
                                 "operator-role" if allowed else "operator-role-required")
