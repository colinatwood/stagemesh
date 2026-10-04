from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class SecurityStateStore:
    """Small local identity/key store with authenticated, atomic checkpoints."""

    def __init__(self, path: Path, *, max_sessions: int = 128) -> None:
        self.path = Path(path)
        self.max_sessions = max(1, min(int(max_sessions), 4096))
        self._state = self._load_or_create()

    @property
    def root_key(self) -> bytes:
        return bytes.fromhex(self._state["rootKeyHex"])

    @property
    def identity_fingerprint(self) -> str:
        return hashlib.sha256(b"UPP-LOCAL-IDENTITY\0" + self.root_key).hexdigest()

    def _tag(self, payload: dict[str, Any]) -> str:
        key = bytes.fromhex(payload["rootKeyHex"])
        return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()

    def _load_or_create(self) -> dict[str, Any]:
        if not self.path.exists():
            state = {"documentType": "org.upp.security-state", "schemaVersion": 1,
                     "rootKeyHex": secrets.token_hex(32), "keyEpoch": 1,
                     "sessions": {}, "revokedFingerprints": []}
            self._write(state)
            return state
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        tag = str(raw.pop("hmacSha256", ""))
        if raw.get("documentType") != "org.upp.security-state" or raw.get("schemaVersion") != 1:
            raise ValueError("unsupported security state")
        if len(str(raw.get("rootKeyHex", ""))) != 64 or not hmac.compare_digest(tag, self._tag(raw)):
            raise ValueError("security state authentication failed")
        os.chmod(self.path, 0o600)
        return raw

    def _write(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {**state, "hmacSha256": self._tag(state)}
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            stream = os.fdopen(fd, "w", encoding="utf-8")
            fd = -1
            with stream:
                json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
                stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
            os.chmod(self.path, 0o600)
        finally:
            if fd >= 0:
                os.close(fd)
            if os.path.exists(name): os.unlink(name)

    def checkpoint(self, session_id: str, checkpoint: dict[str, Any]) -> None:
        if len(session_id) != 32: raise ValueError("invalid session id")
        sessions = self._state["sessions"]
        if session_id not in sessions and len(sessions) >= self.max_sessions:
            oldest = min(sessions, key=lambda key: int(sessions[key].get("updatedUnixMs", 0)))
            del sessions[oldest]
        sessions[session_id] = dict(checkpoint)
        self._write(self._state)

    def session(self, session_id: str) -> dict[str, Any] | None:
        value = self._state["sessions"].get(session_id)
        return dict(value) if value else None

    def revoke(self, fingerprint: str) -> None:
        fingerprint = fingerprint.lower()
        if len(fingerprint) != 64: raise ValueError("invalid fingerprint")
        values = self._state["revokedFingerprints"]
        if fingerprint not in values: values.append(fingerprint)
        self._write(self._state)

    def rotate(self) -> int:
        self._state["keyEpoch"] = int(self._state["keyEpoch"]) + 1
        self._write(self._state)
        return int(self._state["keyEpoch"])

    def status(self) -> dict[str, Any]:
        return {"identityFingerprint": self.identity_fingerprint,
                "keyEpoch": int(self._state["keyEpoch"]),
                "persistedSessions": len(self._state["sessions"]),
                "revokedIdentities": len(self._state["revokedFingerprints"]),
                "physicalOutputsArmed": False}
