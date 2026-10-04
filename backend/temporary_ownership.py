"""Durable, conservative ownership evidence for crash-visible temporary resources.

Version 2 manifests bind one process identity to one exact filesystem object.  Any
legacy, malformed, missing, replaced or otherwise unverifiable resource is
classified as unknown and is never automatically reclaimed.
"""
from __future__ import annotations

import json
import os
import platform
import stat
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 2
MANIFEST_DOCUMENT_TYPE = "org.stageforge.temporary-resource-owner"


def process_identity(pid: int | None = None) -> dict[str, Any]:
    pid = os.getpid() if pid is None else int(pid)
    result: dict[str, Any] = {"pid": pid}
    if platform.system() == "Darwin":
        try:
            def ps(field: str) -> str:
                completed = subprocess.run(
                    ["ps", "-p", str(pid), "-o", f"{field}="],
                    check=True, capture_output=True, text=True,
                )
                value = completed.stdout.strip()
                if not value:
                    raise ValueError(f"missing ps field: {field}")
                return value
            boot = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            started = datetime.strptime(ps("lstart"), "%a %b %d %H:%M:%S %Y")
            result.update({"bootId": boot, "processStartTicks": int(started.timestamp())})
            return result
        except (OSError, ValueError, subprocess.SubprocessError):
            return result
    try:
        result["bootId"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        result["processStartTicks"] = int(Path(f"/proc/{pid}/stat").read_text().split()[21])
    except (OSError, ValueError, IndexError):
        pass
    return result


def owner_live(owner: Any) -> bool | None:
    """Return exact liveness only for a v2 owner with process-generation evidence."""
    if not isinstance(owner, dict) or owner.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        return None
    if owner.get("documentType") != MANIFEST_DOCUMENT_TYPE or type(owner.get("pid")) is not int:
        return None
    if not isinstance(owner.get("bootId"), str) or not owner.get("bootId"):
        return None
    if type(owner.get("processStartTicks")) is not int:
        return None
    current = process_identity(owner["pid"])
    if "bootId" not in current or "processStartTicks" not in current:
        try:
            os.kill(owner["pid"], 0)
        except ProcessLookupError:
            return False
        except (PermissionError, OSError):
            return None
        return None
    return current["bootId"] == owner["bootId"] and current["processStartTicks"] == owner["processStartTicks"]


def _resource_identity(path: Path) -> dict[str, Any] | None:
    try:
        info = path.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode):
        return None
    if stat.S_ISREG(info.st_mode):
        kind = "file"
    elif stat.S_ISDIR(info.st_mode):
        kind = "directory"
    else:
        return None
    return {"device": int(info.st_dev), "inode": int(info.st_ino), "kind": kind}


def resource_matches(owner: Any, resource_path: Path) -> bool:
    if not isinstance(owner, dict) or owner.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        return False
    expected = owner.get("resourceIdentity")
    if not isinstance(expected, dict):
        return False
    actual = _resource_identity(Path(resource_path))
    if actual is None:
        return False
    return expected == actual


def build_owner_manifest(resource_path: Path, *, resource_class: str, purpose: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    identity = _resource_identity(Path(resource_path))
    if identity is None:
        raise RuntimeError("temporary resource must be a regular file or directory")
    owner = dict(extra or {})
    owner.update({
        "documentType": MANIFEST_DOCUMENT_TYPE,
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        **process_identity(),
        "createdAtUnixMs": int(time.time() * 1000),
        "resourceClass": str(resource_class)[:32],
        "purpose": str(purpose)[:32],
        "resourceIdentity": identity,
    })
    return owner


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_owner_manifest(owner_path: Path, owner: dict[str, Any]) -> None:
    """Atomically publish and durably sync an owner manifest and its directory entry."""
    owner_path = Path(owner_path)
    owner_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(owner, separators=(",", ":"), sort_keys=True).encode("utf-8")
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{owner_path.name}.", suffix=".tmp", dir=owner_path.parent)
    tmp = Path(raw_tmp)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        stream = os.fdopen(fd, "wb", closefd=True)
        fd = -1
        with stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, owner_path)
        os.chmod(owner_path, 0o600)
        _fsync_directory(owner_path.parent)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        tmp.unlink(missing_ok=True)
        raise


def create_owner_manifest(owner_path: Path, resource_path: Path, *, resource_class: str, purpose: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    owner = build_owner_manifest(resource_path, resource_class=resource_class, purpose=purpose, extra=extra)
    write_owner_manifest(owner_path, owner)
    return owner


def load_verified_owner(owner_path: Path, resource_path: Path, *, resource_class: str | None = None) -> dict[str, Any] | None:
    """Load only current-format ownership bound to the exact resource object."""
    try:
        owner = json.loads(Path(owner_path).read_text())
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(owner, dict):
        return None
    if owner.get("documentType") != MANIFEST_DOCUMENT_TYPE or owner.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        return None
    if resource_class is not None and owner.get("resourceClass") != resource_class:
        return None
    if not resource_matches(owner, Path(resource_path)):
        return None
    return owner


def classify_owner(owner_path: Path, resource_path: Path, *, resource_class: str | None = None) -> tuple[str, dict[str, Any] | None]:
    owner = load_verified_owner(owner_path, resource_path, resource_class=resource_class)
    live = owner_live(owner)
    if live is True:
        return "live", owner
    if live is False:
        return "reclaimable", owner
    return "unknown-owner", owner


def recheck_reclaimable(owner_path: Path, resource_path: Path, *, resource_class: str | None = None) -> dict[str, Any] | None:
    """Perform the final exact owner/resource check immediately before deletion."""
    owner = load_verified_owner(owner_path, resource_path, resource_class=resource_class)
    if owner_live(owner) is not False:
        return None
    # Deliberately repeat the path-to-object check after liveness evaluation.
    # If the pathname changed while we were checking the process, fail closed.
    if not resource_matches(owner, Path(resource_path)):
        return None
    return owner

# Public alias for callers that create a resource directory before its manifest.
fsync_directory = _fsync_directory
