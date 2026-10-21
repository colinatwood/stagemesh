#!/usr/bin/env python3
"""Record per-installer Windows build references and compare a selected executable.

A match is byte identity against metadata shipped in a verified download. New
MSI references use producer-extracted payload bytes; comparison does not itself
extract the installer, authenticate its publisher or attest source provenance.
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
import subprocess
import sys
import tempfile


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


def _open_identity(info):
    # Windows stat(path) and fstat(fd) can expose different ctime meanings
    # (observed on Python 3.14). Compare ctime within each API below; the
    # cross-API check still binds volume, file ID, size and modification time.
    identity = _identity(info)
    return identity[:-1] if os.name == "nt" else identity


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
        opened = os.fstat(source.fileno())
        if _open_identity(before) != _open_identity(opened):
            raise ValueError("file identity changed before reading")
        remaining = before.st_size
        while remaining:
            block = source.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError("file changed while being read")
            digest.update(block)
            if contents:
                chunks.append(block)
            remaining -= len(block)
        if source.read(1):
            raise ValueError("file changed while being read")
        after = os.fstat(source.fileno())
    if _identity(opened) != _identity(after) or _identity(before) != _identity(path.stat()):
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


def msi_payload(installer: Path):
    """Read an embedded MSI cabinet as data; never invoke an install action.

    Windows Installer supplies the database/table decoding. expand.exe only
    decompresses the selected cabinet member into a fresh temporary directory.
    External cabinets, ambiguous files and unsupported layouts fail closed.
    """
    if sys.platform != "win32":
        raise ValueError("MSI payload extraction requires Windows")
    import ctypes
    from ctypes import wintypes

    system = ctypes.create_unicode_buffer(32768)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetSystemDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    kernel.GetSystemDirectoryW.restype = wintypes.UINT
    length = kernel.GetSystemDirectoryW(system, len(system))
    if not 0 < length < len(system):
        raise ValueError("Windows system directory unavailable")
    api = ctypes.WinDLL(str(Path(system.value) / "msi.dll"))
    handle = wintypes.UINT
    signatures = {
        "MsiOpenDatabaseW": [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(handle)],
        "MsiDatabaseOpenViewW": [handle, wintypes.LPCWSTR, ctypes.POINTER(handle)],
        "MsiViewExecute": [handle, handle], "MsiViewFetch": [handle, ctypes.POINTER(handle)],
        "MsiRecordGetStringW": [handle, wintypes.UINT, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)],
        "MsiRecordGetInteger": [handle, wintypes.UINT],
        "MsiRecordReadStream": [handle, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)],
        "MsiCloseHandle": [handle],
    }
    for name, arguments in signatures.items():
        function = getattr(api, name); function.argtypes = arguments; function.restype = wintypes.UINT
    api.MsiRecordGetInteger.restype = ctypes.c_int
    handles = []

    def opened(function, *arguments):
        result = handle()
        if function(*arguments, ctypes.byref(result)) != 0:
            raise ValueError("MSI database could not be read")
        handles.append(result.value)
        return result.value

    def rows(query):
        view = opened(api.MsiDatabaseOpenViewW, database, query)
        if api.MsiViewExecute(view, 0) != 0:
            raise ValueError("MSI query could not be executed")
        while True:
            row = handle()
            result = api.MsiViewFetch(view, ctypes.byref(row))
            if result == 259:  # ERROR_NO_MORE_ITEMS
                return
            if result != 0:
                raise ValueError("MSI query could not be read")
            try:
                yield row.value
            finally:
                api.MsiCloseHandle(row.value)

    def string(row, field):
        buffer = ctypes.create_unicode_buffer(32768); size = wintypes.DWORD(len(buffer))
        if api.MsiRecordGetStringW(row, field, buffer, ctypes.byref(size)) != 0:
            raise ValueError("MSI string exceeds supported bounds")
        return buffer.value

    before, _ = snapshot(installer)
    try:
        database = opened(api.MsiOpenDatabaseW, str(_plain_file(installer)), None)  # MSIDBOPEN_READONLY
        files = []
        for row in rows("SELECT `File`, `FileName`, `FileSize`, `Sequence` FROM `File`"):
            if string(row, 2).split("|")[-1].casefold() == EXECUTABLE:
                files.append((string(row, 1), api.MsiRecordGetInteger(row, 3), api.MsiRecordGetInteger(row, 4)))
        if len(files) != 1:
            raise ValueError("MSI must contain exactly one desktop executable")
        member, expected_size, sequence = files[0]
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.]{0,71}", member) or not 0 < expected_size <= 512 * 1024 * 1024 or sequence <= 0:
            raise ValueError("MSI executable member is unsupported")
        media = sorted((api.MsiRecordGetInteger(row, 1), string(row, 2))
                       for row in rows("SELECT `LastSequence`, `Cabinet` FROM `Media`"))
        cabinets = [cabinet for last, cabinet in media if last >= sequence]
        if not cabinets or not cabinets[0].startswith("#") or not cabinets[0][1:]:
            raise ValueError("MSI executable must use an embedded cabinet")
        cabinet = cabinets[0][1:]
        with tempfile.TemporaryDirectory(prefix="stagemesh-msi-payload-") as temporary:
            root = Path(temporary); archive = root / "payload.cab"; output = root / "expanded"; output.mkdir()
            found = 0
            # Cabinet identifiers originate in this database, quoted as SQL literals.
            query = "SELECT `Data` FROM `_Streams` WHERE `Name` = '" + cabinet.replace("'", "''") + "'"
            for row in rows(query):
                found += 1
                with archive.open("xb") as destination:
                    total = 0
                    while True:
                        buffer = ctypes.create_string_buffer(1024 * 1024); size = wintypes.DWORD(len(buffer))
                        if api.MsiRecordReadStream(row, 1, buffer, ctypes.byref(size)) != 0:
                            raise ValueError("MSI cabinet could not be read")
                        if size.value == 0:
                            break
                        total += size.value
                        if total > 1024 * 1024 * 1024:
                            raise ValueError("MSI cabinet exceeds supported bounds")
                        destination.write(buffer.raw[:size.value])
            if found != 1:
                raise ValueError("MSI embedded cabinet is missing or ambiguous")
            result = subprocess.run([str(Path(system.value) / "expand.exe"), "-F:" + member,
                                     str(archive), str(output)], capture_output=True, timeout=120)
            if result.returncode != 0 or sorted(p.name for p in output.iterdir()) != [member]:
                raise ValueError("MSI desktop executable could not be decompressed")
            identity, _ = snapshot(output / member)
            if identity["bytes"] != expected_size:
                raise ValueError("MSI executable size disagrees with File table")
        if snapshot(installer)[0] != before:
            raise ValueError("MSI changed during payload extraction")
        return identity
    finally:
        for value in reversed(handles):
            api.MsiCloseHandle(value)


def record(directory: Path, executable: Path, kind: str, commit: str, channel: str, *, extract_msi: bool = False):
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
    if extract_msi and kind != "msi":
        raise ValueError("payload extraction is supported only for MSI")
    executable_id = msi_payload(installer) if extract_msi else snapshot(executable)[0]
    if snapshot(installer)[0] != installer_id:
        raise ValueError("installer changed during reference recording")
    report = {
        "documentType": DOCUMENT_TYPE, "schemaVersion": 1, "product": "StageMesh",
        "platform": "Windows", "sourceCommit": commit, "distributionChannel": channel,
        "installer": {"path": relative, **installer_id},
        "executable": {"name": EXECUTABLE, **executable_id},
        "observation": "extracted-msi-payload" if extract_msi else "post-bundle-build-output",
        "installerPayloadExtracted": extract_msi, "sourceProvenanceVerified": False,
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
        }
        if type(reference.get("schemaVersion")) is not int or reference["schemaVersion"] != 1 or any(reference.get(k) != v for k, v in expected.items()):
            raise ValueError("executable reference identity does not match the selected candidate")
        extracted = reference.get("observation") == "extracted-msi-payload" and kind == "msi"
        if (reference.get("observation") not in {"post-bundle-build-output", "extracted-msi-payload"}
                or reference.get("observation") == "extracted-msi-payload" and kind != "msi"
                or reference.get("installerPayloadExtracted") is not extracted
                or reference.get("sourceProvenanceVerified") is not False):
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
            raise ValueError("selected executable differs from this installer's executable reference")
        if snapshot(root / "desktop-artifacts.json")[0] != manifest_id or snapshot(root / reference_path)[0] != reference_id:
            raise ValueError("candidate metadata changed during comparison")
        report.update({
            "passed": True, "installedExecutableMatchesCandidateReference": True,
            "candidateDeclaredSourceCommit": commit, "distributionChannel": channel,
            "artifactManifest": manifest_id, "executableReference": reference_id,
            "installer": {"path": installer, **{k: selected[k] for k in ("bytes", "sha256")}},
            "selectedExecutable": {"name": EXECUTABLE, **observed},
            "referenceObservation": reference["observation"],
            "candidateReferenceFromExtractedPayload": extracted,
        })
        if extracted:
            report["verificationBoundary"][0] = "A match compares a selected file with the producer's extracted MSI executable reference for one installer."
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
        if name == "record":
            sub.add_argument("--extract-msi-payload", action="store_true")
    args = parser.parse_args()
    if args.command == "record":
        try:
            result = record(args.directory, args.executable, args.format, args.commit, args.distribution_channel,
                            extract_msi=args.extract_msi_payload)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            parser.error(str(exc))
    else:
        result = check(args.directory, args.executable, args.installer, args.commit, args.distribution_channel)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if args.command == "record" or result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
