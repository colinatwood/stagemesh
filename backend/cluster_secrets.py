"""Bounded private HMAC keyrings for replication and witness control paths.

The keyring is deliberately a control-plane primitive.  It is re-read for each
network/authentication operation so an atomic file replacement can rotate keys
without restarting StageMesh, while each individual operation pins one
immutable snapshot and cannot mix keys mid-quorum or mid-transaction.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

_MAX_FILE_BYTES = 32768
_MAX_KEYS = 16
_MAX_KEY_ID = 64
_MIN_SECRET = 32
_MAX_SECRET = 512


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _valid_key_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= _MAX_KEY_ID
        and value.isascii()
        and all(c.isalnum() or c in "._-" for c in value)
    )


def _secret_bytes(value: object) -> bytes:
    if (
        not isinstance(value, str)
        or not _MIN_SECRET <= len(value) <= _MAX_SECRET
        or not value.isascii()
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
    ):
        raise ValueError("invalid HMAC secret")
    return value.encode("utf-8")


@dataclass(frozen=True)
class HmacKeySnapshot:
    """One immutable authentication view pinned for a network operation."""

    active_key_id: str | None
    keys: Mapping[str, bytes]
    keyring_mode: bool

    @property
    def configured(self) -> bool:
        return bool(self.keys)

    @property
    def active_secret(self) -> bytes:
        if not self.configured:
            return b""
        if self.keyring_mode:
            if not self.active_key_id or self.active_key_id not in self.keys:
                raise PermissionError("cluster keyring has no active key")
            return self.keys[self.active_key_id]
        return next(iter(self.keys.values()))

    def resolve(self, key_id: object) -> bytes:
        if not self.keyring_mode:
            if key_id not in (None, ""):
                raise PermissionError("key identifiers require keyring mode")
            return self.active_secret
        if not _valid_key_id(key_id):
            raise PermissionError("cluster key identifier required")
        try:
            return self.keys[str(key_id)]
        except KeyError:
            raise PermissionError("unknown cluster key identifier") from None


class RotatingHmacKeyring:
    """Secure private-file keyring with a legacy single-secret fallback."""

    def __init__(self, path: str | os.PathLike[str] | None, legacy_secret: bytes | None = None) -> None:
        text = str(path or "").strip()
        self._path = Path(text) if text else None
        self._legacy_secret = bytes(legacy_secret or b"")
        if self._path is not None:
            # Fail startup closed, then reload on every operation so atomic
            # replacement rotates immediately without preserving removed keys.
            self.snapshot()

    @property
    def keyring_mode(self) -> bool:
        return self._path is not None

    @property
    def configured(self) -> bool:
        return self.keyring_mode or bool(self._legacy_secret)

    @property
    def path(self) -> Path | None:
        return self._path

    def snapshot(self) -> HmacKeySnapshot:
        if self._path is None:
            keys = {"legacy": self._legacy_secret} if self._legacy_secret else {}
            return HmacKeySnapshot(None, MappingProxyType(keys), False)
        raw = self._read_private_file(self._path)
        try:
            document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
            if not isinstance(document, dict) or set(document) != {"version", "activeKeyId", "keys"}:
                raise ValueError("invalid keyring document")
            if type(document["version"]) is not int or document["version"] != 1:
                raise ValueError("unsupported keyring version")
            active = document["activeKeyId"]
            entries = document["keys"]
            if not _valid_key_id(active) or not isinstance(entries, dict) or not 1 <= len(entries) <= _MAX_KEYS:
                raise ValueError("invalid keyring fields")
            keys: dict[str, bytes] = {}
            for key_id, secret in entries.items():
                if not _valid_key_id(key_id):
                    raise ValueError("invalid key identifier")
                keys[key_id] = _secret_bytes(secret)
            if active not in keys or len(set(keys.values())) != len(keys):
                raise ValueError("ambiguous or missing active key")
            return HmacKeySnapshot(str(active), MappingProxyType(keys), True)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, AttributeError, RecursionError):
            raise PermissionError("cluster keyring unavailable or invalid") from None

    @staticmethod
    def _read_private_file(path: Path) -> bytes:
        try:
            if not path.is_absolute():
                raise ValueError("absolute path required")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) & 0o077
                    or before.st_size > _MAX_FILE_BYTES
                ):
                    raise ValueError("invalid keyring file")
                data = stream.read(_MAX_FILE_BYTES + 1)
                after = os.fstat(stream.fileno())
                if (
                    len(data) > _MAX_FILE_BYTES
                    or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                ):
                    raise ValueError("keyring changed while reading")
            return data
        except (OSError, ValueError):
            raise PermissionError("cluster keyring unavailable or invalid") from None
