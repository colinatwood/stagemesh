#!/usr/bin/env python3
"""Record per-installer Windows build references and compare a selected executable.

A match is byte identity against metadata shipped in a verified download. It is
not publisher authentication, extracted-installer proof or source attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


DOCUMENT_TYPE = "org.stagemesh.desktop-executable-reference"
EXECUTABLE = "stagemesh-desktop.exe"
COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON = 1024 * 1024


def _plain_file(path: Path) -> Path:
    path = path.absolute()
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("file paths must not use symlinks or Windows reparse points")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("expected a regular file")
    return path


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def snapshot(path: Path, *, contents: bool = False):
    path = _plain_file(path)
    before = path.stat()
    if before.st_size <= 0:
        raise ValueError("empty files cannot establish executable identity")
    if contents and before.st_size > MAX_JSON:
        raise ValueError("JSON metadata exceeds the size limit")
    digest = hashlib.sha256()
    chunks = []
    with path.open("rb") as source:
        if _identity(before) != _identity(os.fstat(source.fileno())):
            raise ValueError("file identity changed before reading")
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            if contents:
                chunks.append(block)
                if sum(map(len, chunks)) > MAX_JSON:
                    raise ValueError("JSON metadata grew beyond the size limit")
        after = os.fstat(source.fileno())
    if _identity(before) != _identity(after) or _identity(before) != _identity(path.stat()):
        raise ValueError("file changed while being read")
    _plain_file(path)
    return {"bytes": before.st_size, "sha256": digest.hexdigest()}, b"".join(chunks)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("JSON metadata contains duplicate keys")
        value[key] = item
    return value


def _load(path: Path):
    identity, data = snapshot(path, contents=True)
    value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    return value, identity


def _installer_path(value: str):
    if not isinstance(value, str) or "\\" in value or ":" in value or any(ord(c) < 32 for c in value):
        raise ValueError("installer must use a safe relative POSIX path")
    path = PurePosixPath(value)
    if len(path.parts) != 2 or value != path.as_posix() or path.parts[0] not in {"msi", "nsis"}:
        raise ValueError("installer must be directly inside msi/ or nsis/")
    kind = path.parts[0]
    if path.name in {".", ".."} or path.suffix.lower() != (".msi" if kind == "msi" else ".exe"):
        raise ValueError("installer extension does not match its format")
    return kind


def _fingerprint(value):
    return (isinstance(value, dict) and type(value.get("bytes")) is int and value["bytes"] > 0
            and isinstance(value.get("sha256"), str) and DIGEST.fullmatch(value["sha256"]))


def record(directory: Path, executable: Path, kind: str, commit: str, channel: str):
    if not COMMIT.fullmatch(commit) or channel not in {"online", "offline"} or kind not in {"msi", "nsis"}:
        raise ValueError("recording requires an exact source SHA, Windows channel and installer format")
    root = directory.resolve(strict=True)
    if executable.name != EXECUTABLE:
        raise ValueError("build executable must be named stagemesh-desktop.exe")
    pattern = "*.msi" if kind == "msi" else "*.exe"
    installers = list((root / kind).glob(pattern))
    if len(installers) != 1:
        raise ValueError("expected exactly one installer for the selected format")
    installer = installers[0]
    relative = installer.relative_to(root).as_posix()
    _installer_path(relative)
    installer_id, _ = snapshot(installer)
    executable_id, _ = snapshot(executable)
    report = {
        "documentType": DOCUMENT_TYPE, "schemaVersion": 1, "product": "StageMesh",
        "platform": "Windows", "sourceCommit": commit, "distributionChannel": channel,
        "installer": {"path": relative, **installer_id},
        "executable": {"name": EXECUTABLE, **executable_id},
        "observation": "post-bundle-build-output",
        "installerPayloadExtracted": False, "sourceProvenanceVerified": False,
    }
    destination = root / "executable-bindings" / (kind + ".json")
    destination.parent.mkdir(exist_ok=True)
    # Reject redirected output and duplicate recording rather than replacing evidence.
    if destination.parent.is_symlink() or getattr(destination.parent.stat(), "st_file_attributes", 0) & 0x400:
        raise ValueError("reference directory must not be redirected")
    with destination.open("x", encoding="utf-8") as output:
        output.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def _download_verifier():
    # Load only our fixed companion, never code chosen by --directory.
    source = Path(__file__).with_name("verify-desktop-download.py")
    if not source.exists():
        source = Path(__file__).with_name("verify-download.py")
    spec = importlib.util.spec_from_file_location("stagemesh_download_verifier", source)
    if spec is None or spec.loader is None:
        raise ValueError("download verifier companion is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(directory: Path, executable: Path, installer: str, commit: str, channel: str):
    report = {
        "documentType": "org.stagemesh.installed-executable-comparison", "schemaVersion": 1,
        "passed": False, "candidateIntegrityVerified": False,
        "installedExecutableMatchesCandidateReference": False,
        "sourceProvenanceVerified": False, "publisherAuthenticated": False,
        "installerPayloadExtracted": False, "installedLocationVerified": False,
        "cleanHostInstallQualified": False, "physicalHardwareQualified": False,
        "blockers": [],
        "verificationBoundary": [
            "A match compares a selected file with the post-bundle build-output reference for one installer.",
            "Bundle integrity and matching bytes do not authenticate metadata or attest source provenance.",
            "The installer payload is not independently extracted, and installation state, sidecars, resources and hardware are not qualified.",
        ],
    }
    try:
        if not isinstance(commit, str) or not COMMIT.fullmatch(commit) or channel not in {"online", "offline"}:
            raise ValueError("comparison requires an exact expected source SHA and Windows channel")
        kind = _installer_path(installer)
        root = directory.resolve(strict=True)
        if executable.name != EXECUTABLE:
            raise ValueError("selected executable must be named stagemesh-desktop.exe")
        if executable.resolve().is_relative_to(root):
            raise ValueError("selected executable must be outside the download bundle")
        manifest, manifest_id = _load(root / "desktop-artifacts.json")
        if (manifest.get("platform"), manifest.get("sourceCommit"), manifest.get("distributionChannel")) != ("Windows", commit, channel):
            raise ValueError("candidate platform, source or distribution channel does not match the request")
        verification = _download_verifier().evaluate(root)
        if not verification.get("passed"):
            raise ValueError("download integrity check failed; run the download verifier for details")
        report["candidateIntegrityVerified"] = True
        reference_path = "executable-bindings/" + kind + ".json"
        entries = {item["path"]: item for item in manifest["files"]}
        if installer not in entries or reference_path not in entries:
            raise ValueError("installer or executable reference is absent from the verified manifest")
        reference, reference_id = _load(root / reference_path)
        expected = {
            "documentType": DOCUMENT_TYPE, "product": "StageMesh", "platform": "Windows",
            "sourceCommit": commit, "distributionChannel": channel,
            "observation": "post-bundle-build-output",
        }
        if type(reference.get("schemaVersion")) is not int or reference["schemaVersion"] != 1 or any(reference.get(k) != v for k, v in expected.items()):
            raise ValueError("executable reference identity does not match the selected candidate")
        if reference.get("installerPayloadExtracted") is not False or reference.get("sourceProvenanceVerified") is not False:
            raise ValueError("executable reference qualification boundary is invalid")
        binary = reference.get("executable")
        selected = reference.get("installer")
        if not _fingerprint(binary) or binary.get("name") != EXECUTABLE or not _fingerprint(selected) or selected.get("path") != installer:
            raise ValueError("reference executable or installer identity is invalid")
        for relative, identity in ((reference_path, reference_id), (installer, snapshot(root / installer)[0])):
            if any(entries[relative][field] != identity[field] for field in ("bytes", "sha256")):
                raise ValueError("selected candidate files changed or disagree with the manifest")
        if any(selected[field] != entries[installer][field] for field in ("bytes", "sha256")):
            raise ValueError("reference belongs to a different installer")
        observed, _ = snapshot(executable)
        if any(binary[field] != observed[field] for field in ("bytes", "sha256")):
            raise ValueError("selected executable differs from this installer's build reference")
        if snapshot(root / "desktop-artifacts.json")[0] != manifest_id or snapshot(root / reference_path)[0] != reference_id:
            raise ValueError("candidate metadata changed during comparison")
        report.update({
            "passed": True, "installedExecutableMatchesCandidateReference": True,
            "candidateDeclaredSourceCommit": commit, "distributionChannel": channel,
            "artifactManifest": manifest_id, "executableReference": reference_id,
            "installer": {"path": installer, **{k: selected[k] for k in ("bytes", "sha256")}},
            "selectedExecutable": {"name": EXECUTABLE, **observed},
        })
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        # Do not print user paths or exception reprs into a potentially shared report.
        report["blockers"].append(str(exc) if isinstance(exc, ValueError) else "comparison input could not be read safely")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("record", "check"):
        sub = commands.add_parser(name)
        sub.add_argument("--directory", type=Path, required=True)
        sub.add_argument("--executable", type=Path, required=True)
        sub.add_argument("--commit", required=True)
        sub.add_argument("--distribution-channel", choices=("online", "offline"), required=True)
        sub.add_argument("--format" if name == "record" else "--installer", required=True)
    args = parser.parse_args()
    if args.command == "record":
        try:
            result = record(args.directory, args.executable, args.format, args.commit, args.distribution_channel)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    else:
        result = check(args.directory, args.executable, args.installer, args.commit, args.distribution_channel)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if args.command == "record" or result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
