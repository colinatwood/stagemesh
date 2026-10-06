from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


_ZERO_HASH = "0" * 64
_SEGMENT_RE = re.compile(r"^(\d{20})\.jsonl$")


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError(f"invalid {name}")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"invalid {name}")
    return value


class StateRepository:
    """Atomic checkpoint + append-only hash-linked event records.

    Authorization decisions use a separately locked, bounded segmented chain. Old
    segments may be pruned only after an fsynced retention anchor commits the exact
    head hash and record count of the removed prefix. This preserves an explicit
    cryptographic commitment to discarded history without pretending the removed
    actor records remain locally inspectable.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.snapshot_path = directory / "show-state.json"
        self.ledger_path = directory / "events.jsonl"
        self.authorization_audit_path = directory / "authorization-audit.jsonl"
        self.authorization_audit_segments = directory / "authorization-audit-segments"
        self.authorization_audit_retention_path = directory / "authorization-audit-retention.json"
        self.authorization_audit_rotate_bytes = _bounded_env_int(
            "STAGEMESH_AUTH_AUDIT_ROTATE_BYTES", 4 * 1024 * 1024, 64 * 1024, 256 * 1024 * 1024)
        self.authorization_audit_retain_segments = _bounded_env_int(
            "STAGEMESH_AUTH_AUDIT_RETAIN_SEGMENTS", 8, 1, 256)
        self._lock = RLock()
        self._authorization_lock = RLock()
        self._authorization_state = None
        directory.mkdir(parents=True, exist_ok=True)
        self.authorization_audit_segments.mkdir(parents=True, exist_ok=True)

    def load_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            if not self.snapshot_path.is_file():
                return None
            try:
                value = json.loads(self.snapshot_path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            return value if isinstance(value, dict) else None

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if not hasattr(os, "O_DIRECTORY"):
            return
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            StateRepository._fsync_directory(path.parent)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            data = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            fd, temp_name = tempfile.mkstemp(prefix=".show-state-", suffix=".json", dir=self.directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.snapshot_path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)

    @staticmethod
    def _last_hash(path: Path, initial_hash: str = _ZERO_HASH) -> str:
        if not path.is_file():
            return initial_hash
        last = ""
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    last = line
        if not last:
            return initial_hash
        try:
            return str(json.loads(last)["hash"])
        except (json.JSONDecodeError, KeyError, TypeError):
            return "INVALID"

    @staticmethod
    def _record(previous_hash: str, event: dict[str, Any]) -> dict[str, Any]:
        record = {"event": event, "previousHash": previous_hash}
        record["hash"] = hashlib.sha256(previous_hash.encode("ascii", "replace") + b"\n" + _canonical(event)).hexdigest()
        return record

    @staticmethod
    def _append_hash_linked(path: Path, event: dict[str, Any], initial_hash: str = _ZERO_HASH) -> dict[str, Any]:
        previous_hash = StateRepository._last_hash(path, initial_hash)
        record = StateRepository._record(previous_hash, event)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record

    @staticmethod
    def _verify_hash_linked(path: Path, initial_hash: str = _ZERO_HASH) -> dict[str, Any]:
        previous_hash = initial_hash
        count = 0
        if not path.is_file():
            return {"ok": True, "records": 0, "head": previous_hash}
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    event = record["event"]
                    if record.get("previousHash") != previous_hash:
                        return {"ok": False, "records": count, "line": line_number, "error": "previous hash mismatch"}
                    expected = hashlib.sha256(previous_hash.encode("ascii") + b"\n" + _canonical(event)).hexdigest()
                    if record.get("hash") != expected:
                        return {"ok": False, "records": count, "line": line_number, "error": "record hash mismatch"}
                    previous_hash = expected
                    count += 1
        except (OSError, json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError) as exc:
            return {"ok": False, "records": count, "error": str(exc)}
        return {"ok": True, "records": count, "head": previous_hash}

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            return self._append_hash_linked(self.ledger_path, event)

    def _retention_anchor(self) -> dict[str, Any]:
        if not self.authorization_audit_retention_path.is_file():
            return {"version": 1, "previousHead": _ZERO_HASH, "nextSequence": 1,
                    "prunedSegments": 0, "prunedRecords": 0}
        try:
            value = json.loads(self.authorization_audit_retention_path.read_text("utf-8"))
            if (not isinstance(value, dict)
                    or set(value) != {"version", "previousHead", "nextSequence", "prunedSegments", "prunedRecords"}
                    or value.get("version") != 1
                    or not isinstance(value.get("previousHead"), str)
                    or len(value["previousHead"]) != 64
                    or any(ch not in "0123456789abcdef" for ch in value["previousHead"])
                    or not isinstance(value.get("nextSequence"), int) or value["nextSequence"] < 1
                    or not isinstance(value.get("prunedSegments"), int) or value["prunedSegments"] < 0
                    or not isinstance(value.get("prunedRecords"), int) or value["prunedRecords"] < 0):
                raise ValueError("invalid authorization audit retention anchor")
            return value
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
            raise OSError("authorization audit retention anchor unavailable or invalid") from None

    @staticmethod
    def _file_signature(path: Path):
        try:
            value = path.stat()
            return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        except FileNotFoundError:
            return None

    def _segment_paths(self) -> list[tuple[int, Path]]:
        result = []
        for path in self.authorization_audit_segments.iterdir():
            if not path.is_file():
                raise OSError("authorization audit segment directory contains non-file entry")
            match = _SEGMENT_RE.fullmatch(path.name)
            if match is None:
                raise OSError("authorization audit segment directory contains unexpected file")
            result.append((int(match.group(1)), path))
        result.sort()
        return result

    def _scan_authorization_audit(self) -> tuple[dict[str, Any], dict[str, Any] | None]:
        try:
            anchor = self._retention_anchor()
            previous = anchor["previousHead"]
            expected_sequence = anchor["nextSequence"]
            records = 0
            retained_segments = 0
            stale_pruned_files = 0
            all_segments = self._segment_paths()
            for sequence, path in all_segments:
                if sequence < expected_sequence:
                    # Crash residue after an anchor commit but before unlink. The
                    # anchor is authoritative, so this old file is not reintroduced.
                    stale_pruned_files += 1
                    continue
                if sequence != expected_sequence:
                    return ({"ok": False, "records": records, "head": previous,
                             "error": "authorization audit segment gap",
                             "expectedSequence": expected_sequence, "actualSequence": sequence}, None)
                result = self._verify_hash_linked(path, previous)
                if not result.get("ok"):
                    return ({**result, "segment": sequence,
                             "records": records + result.get("records", 0)}, None)
                previous = result["head"]
                records += result["records"]
                retained_segments += 1
                expected_sequence += 1
            active_initial = previous
            active = self._verify_hash_linked(self.authorization_audit_path, active_initial)
            if not active.get("ok"):
                return ({**active, "segment": "active",
                         "records": records + active.get("records", 0)}, None)
            records += active["records"]
            previous = active["head"]
            active_bytes = self.authorization_audit_path.stat().st_size if self.authorization_audit_path.is_file() else 0
            segment_bytes = sum(path.stat().st_size for sequence, path in all_segments
                                if sequence >= anchor["nextSequence"])
            report = {
                "ok": True,
                "records": records,
                "totalRecords": records + anchor["prunedRecords"],
                "head": previous,
                "retainedSegments": retained_segments,
                "activeRecords": active["records"],
                "activeBytes": active_bytes,
                "retainedBytes": active_bytes + segment_bytes,
                "rotateBytes": self.authorization_audit_rotate_bytes,
                "retainSegments": self.authorization_audit_retain_segments,
                "retentionAnchor": anchor["previousHead"],
                "nextSequence": anchor["nextSequence"],
                "prunedSegments": anchor["prunedSegments"],
                "prunedRecords": anchor["prunedRecords"],
                "stalePrunedFiles": stale_pruned_files,
            }
            state = {
                "head": previous,
                "activeInitial": active_initial,
                "activeRecords": active["records"],
                "activeBytes": active_bytes,
                "nextSequence": expected_sequence,
                "activeSignature": self._file_signature(self.authorization_audit_path),
                "retentionSignature": self._file_signature(self.authorization_audit_retention_path),
                "segmentSignatures": tuple((sequence, self._file_signature(path)) for sequence, path in all_segments),
            }
            return report, state
        except OSError as exc:
            return {"ok": False, "records": 0, "error": str(exc)}, None

    def _authorization_state_matches_disk(self) -> bool:
        state = self._authorization_state
        if state is None:
            return False
        try:
            segments = tuple((sequence, self._file_signature(path)) for sequence, path in self._segment_paths())
        except OSError:
            return False
        return (state["activeSignature"] == self._file_signature(self.authorization_audit_path)
                and state["retentionSignature"] == self._file_signature(self.authorization_audit_retention_path)
                and state["segmentSignatures"] == segments)

    def _ensure_authorization_state(self) -> dict[str, Any]:
        if self._authorization_state is None:
            report, state = self._scan_authorization_audit()
            if not report.get("ok") or state is None:
                raise OSError("authorization audit verification failed before append")
            self._authorization_state = state
        elif not self._authorization_state_matches_disk():
            raise OSError("authorization audit changed outside repository")
        return self._authorization_state

    def _prune_authorization_segments(self) -> None:
        anchor = self._retention_anchor()
        all_segments = self._segment_paths()
        segments = [(sequence, path) for sequence, path in all_segments
                    if sequence >= anchor["nextSequence"]]
        stale = [path for sequence, path in all_segments if sequence < anchor["nextSequence"]]
        if len(segments) <= self.authorization_audit_retain_segments:
            for path in stale:
                path.unlink()
            if stale:
                self._fsync_directory(self.authorization_audit_segments)
            return
        prune_count = len(segments) - self.authorization_audit_retain_segments
        previous = anchor["previousHead"]
        pruned_records = 0
        last_sequence = anchor["nextSequence"] - 1
        to_delete = []
        for sequence, path in segments[:prune_count]:
            if sequence != last_sequence + 1:
                raise OSError("authorization audit segment gap during retention")
            result = self._verify_hash_linked(path, previous)
            if not result.get("ok"):
                raise OSError("authorization audit segment invalid during retention")
            previous = result["head"]
            pruned_records += result["records"]
            last_sequence = sequence
            to_delete.append(path)
        new_anchor = {
            "version": 1,
            "previousHead": previous,
            "nextSequence": last_sequence + 1,
            "prunedSegments": anchor["prunedSegments"] + len(to_delete),
            "prunedRecords": anchor["prunedRecords"] + pruned_records,
        }
        # Commit the cryptographic prefix summary before deleting any segment. If
        # this write fails (for example ENOSPC), no retained bytes are deleted.
        self._atomic_write_json(self.authorization_audit_retention_path, new_anchor)
        for path in stale + to_delete:
            path.unlink()
        self._fsync_directory(self.authorization_audit_segments)

    def _rotate_authorization_audit(self) -> None:
        state = self._ensure_authorization_state()
        if not self.authorization_audit_path.is_file() or state["activeBytes"] == 0:
            return
        sequence = state["nextSequence"]
        target = self.authorization_audit_segments / f"{sequence:020d}.jsonl"
        if target.exists():
            raise OSError("authorization audit rotation target already exists")
        os.replace(self.authorization_audit_path, target)
        self._fsync_directory(self.authorization_audit_segments)
        self._fsync_directory(self.directory)
        # Force a bounded full re-scan after the infrequent structural change.
        self._authorization_state = None
        self._prune_authorization_segments()
        report, refreshed = self._scan_authorization_audit()
        if not report.get("ok") or refreshed is None:
            raise OSError("authorization audit verification failed after rotation")
        self._authorization_state = refreshed

    def append_authorization_audit(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._authorization_lock:
            event_bytes = _canonical(event)
            if len(event_bytes) > 8192:
                raise OSError("authorization audit event exceeds 8 KiB bound")
            state = self._ensure_authorization_state()
            record = self._record(state["head"], event)
            encoded = (json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
            if state["activeBytes"] and state["activeBytes"] + len(encoded) > self.authorization_audit_rotate_bytes:
                self._rotate_authorization_audit()
                state = self._ensure_authorization_state()
                record = self._record(state["head"], event)
                encoded = (json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
            try:
                with self.authorization_audit_path.open("ab") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError:
                # Disk state may contain a partial write. Do not trust the cache on
                # any subsequent request until a full verification/restart occurs.
                self._authorization_state = None
                raise
            state["head"] = record["hash"]
            state["activeRecords"] += 1
            state["activeBytes"] += len(encoded)
            state["activeSignature"] = self._file_signature(self.authorization_audit_path)
            return record

    def verify_ledger(self) -> dict[str, Any]:
        with self._lock:
            return self._verify_hash_linked(self.ledger_path)

    def verify_authorization_audit(self) -> dict[str, Any]:
        with self._authorization_lock:
            report, state = self._scan_authorization_audit()
            if report.get("ok") and state is not None:
                self._authorization_state = state
            return report
