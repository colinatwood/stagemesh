#!/usr/bin/env python3
"""Verify a downloaded StageMesh desktop bundle without external packages.

This checks transport integrity and internal consistency only. A passing report
does not authenticate the publisher or qualify signing, installation, legal,
clean-host, accessibility, or physical audio/MIDI behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


MANIFEST_NAME = "desktop-artifacts.json"
CHECKSUM_NAME = "SHA256SUMS"
SIGNING_VERIFICATION_NAME = "signing-verification.json"
SIDECAR_NAMES = frozenset({MANIFEST_NAME, CHECKSUM_NAME, SIGNING_VERIFICATION_NAME})
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CHECKSUM_PATTERN = re.compile(r"^([0-9a-f]{64})  (.+)$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe relative path: {value}")
    if value != path.as_posix():
        raise ValueError(f"path is not normalized: {value}")
    return value


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{label} could not be read: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _manifest_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if manifest.get("schemaVersion") != 1:
        raise ValueError("artifact manifest schemaVersion must be 1")
    if manifest.get("product") != "StageMesh":
        raise ValueError("artifact manifest product must be StageMesh")
    for field in ("version", "platform"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f"artifact manifest {field} must be a non-empty string")
    if not isinstance(manifest.get("sourceCommit"), str) or not COMMIT_PATTERN.fullmatch(
        manifest["sourceCommit"]
    ):
        raise ValueError("artifact manifest sourceCommit must be a lowercase 40-character SHA")
    if manifest.get("signed") is not False:
        raise ValueError("artifact manifest signed boundary must remain false")
    qualification = manifest.get("qualification")
    if not isinstance(qualification, dict):
        raise ValueError("artifact manifest qualification must be an object")
    if qualification.get("softwarePackageBuilt") is not True:
        raise ValueError("artifact manifest softwarePackageBuilt must be true")
    for field in ("cleanHostInstallQualified", "physicalHardwareQualified"):
        if qualification.get(field) is not False:
            raise ValueError(f"artifact manifest {field} boundary must remain false")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("artifact manifest files must be a non-empty list")
    entries: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise ValueError(f"artifact manifest file {index} must be an object")
        try:
            path = _safe_relative_path(item.get("path"))
        except ValueError as exc:
            raise ValueError(f"artifact manifest file {index}: {exc}") from exc
        if Path(path).name in SIDECAR_NAMES:
            raise ValueError(f"artifact manifest must not inventory metadata sidecar: {path}")
        if path in entries:
            raise ValueError(f"artifact manifest contains duplicate path: {path}")
        size = item.get("bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"artifact manifest has invalid byte count for {path}")
        digest = item.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ValueError(f"artifact manifest has invalid SHA-256 for {path}")
        entries[path] = item
    return entries


def _checksum_entries(path: Path) -> dict[str, str]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"checksum file could not be read: {exc.strerror or exc}") from exc
    if not content:
        raise ValueError("checksum file must not be empty")
    entries: dict[str, str] = {}
    for number, line in enumerate(content.splitlines(), start=1):
        match = CHECKSUM_PATTERN.fullmatch(line)
        if match is None:
            raise ValueError(f"checksum line {number} is malformed")
        digest, raw_path = match.groups()
        try:
            relative = _safe_relative_path(raw_path)
        except ValueError as exc:
            raise ValueError(f"checksum line {number}: {exc}") from exc
        if relative in entries:
            raise ValueError(f"checksum file contains duplicate path: {relative}")
        entries[relative] = digest
    return entries


def _inside_root(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def evaluate(directory: Path) -> dict[str, Any]:
    root = directory.resolve()
    blockers: list[str] = []
    manifest: dict[str, Any] = {}
    entries: dict[str, dict[str, Any]] = {}
    checksums: dict[str, str] = {}
    files_verified = 0
    signing_status = "not-present"
    manifest_path = root / MANIFEST_NAME

    if not root.is_dir():
        blockers.append("download directory does not exist or is not a directory")
    else:
        try:
            manifest = _load_object(manifest_path, "artifact manifest")
            entries = _manifest_entries(manifest)
        except ValueError as exc:
            blockers.append(str(exc))
        try:
            checksums = _checksum_entries(root / CHECKSUM_NAME)
        except ValueError as exc:
            blockers.append(str(exc))

    if entries and checksums:
        expected_paths = set(entries)
        checksum_paths = set(checksums)
        missing_checksums = sorted(expected_paths - checksum_paths)
        extra_checksums = sorted(checksum_paths - expected_paths)
        if missing_checksums:
            blockers.append("checksum file is missing paths: " + ", ".join(missing_checksums))
        if extra_checksums:
            blockers.append("checksum file has unexpected paths: " + ", ".join(extra_checksums))
        for relative in sorted(expected_paths & checksum_paths):
            if checksums[relative] != entries[relative]["sha256"]:
                blockers.append(f"checksum and manifest disagree for {relative}")

        actual_paths = {
            item.relative_to(root).as_posix()
            for item in root.rglob("*")
            if item.is_file()
            and not (item.parent == root and item.name in SIDECAR_NAMES)
        }
        missing_files = sorted(expected_paths - actual_paths)
        unexpected_files = sorted(actual_paths - expected_paths)
        if missing_files:
            blockers.append("download is missing files: " + ", ".join(missing_files))
        if unexpected_files:
            blockers.append("download has unexpected files: " + ", ".join(unexpected_files))

        for relative in sorted(expected_paths & actual_paths):
            current = root / relative
            if not _inside_root(root, current):
                blockers.append(f"download path resolves outside the bundle: {relative}")
                continue
            try:
                actual_size = current.stat().st_size
                actual_digest = _sha256(current)
            except OSError as exc:
                blockers.append(f"download file could not be read: {relative}: {exc}")
                continue
            if actual_size != entries[relative]["bytes"]:
                blockers.append(f"byte count mismatch for {relative}")
            if actual_digest != entries[relative]["sha256"]:
                blockers.append(f"SHA-256 mismatch for {relative}")
            if (
                actual_size == entries[relative]["bytes"]
                and actual_digest == entries[relative]["sha256"]
            ):
                files_verified += 1

    signing_path = root / SIGNING_VERIFICATION_NAME
    if root.is_dir() and signing_path.exists():
        try:
            signing = _load_object(signing_path, "signing verification report")
            if signing.get("schemaVersion") != 1 or signing.get("product") != "StageMesh":
                raise ValueError("signing verification report identity is invalid")
            raw_signing_status = signing.get("status")
            if raw_signing_status not in {"failed", "not-configured", "verified"}:
                raise ValueError("signing verification report status is invalid")
            signing_status = raw_signing_status
            binding = signing.get("artifactManifest")
            if not isinstance(binding, dict):
                raise ValueError("signing verification report lacks artifactManifest binding")
            if binding.get("path") != MANIFEST_NAME:
                raise ValueError("signing verification report names the wrong artifact manifest")
            if binding.get("sha256") != _sha256(manifest_path):
                raise ValueError("signing verification report does not match this artifact manifest")
            if signing.get("readyForPublication") is not False:
                raise ValueError("signing verification readyForPublication boundary must remain false")
        except (OSError, ValueError) as exc:
            signing_status = "invalid"
            blockers.append(str(exc))
    elif root.is_dir():
        blockers.append("signing verification report is missing")

    passed = not blockers
    return {
        "schemaVersion": 1,
        "product": "StageMesh",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "version": manifest.get("version"),
        "platform": manifest.get("platform"),
        "sourceCommit": manifest.get("sourceCommit"),
        "filesVerified": files_verified,
        "signingVerificationStatus": signing_status,
        "readyForPublication": False,
        "blockers": blockers,
        "verificationBoundary": [
            "A pass verifies transport integrity and internal consistency against metadata shipped in the same download.",
            "It does not authenticate the publisher or establish signing, notarization, legal approval, clean-host installation, accessibility, or physical audio/MIDI qualification.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("."))
    args = parser.parse_args()
    report = evaluate(args.directory)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
