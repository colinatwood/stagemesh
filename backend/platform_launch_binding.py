"""OS-native verification-to-launch binding for external adapter executables.

The functions in this module bind verification to the executable object used for
process creation. They do not qualify any plugin product and never arm outputs.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

_CDHASH = re.compile(r"^[0-9a-f]{40,64}$", re.I)
_TEAM = re.compile(r"^[A-Z0-9]{6,64}$")


class PlatformLaunchBindingError(RuntimeError):
    pass


def _sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    while True:
        block = stream.read(1024 * 1024)
        if not block:
            break
        digest.update(block)
    return digest.hexdigest()


def _require_absolute_executable(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or not path.is_file():
        raise PlatformLaunchBindingError("adapter executable must be an absolute regular file")
    return path


@dataclass
class BoundProcess:
    pid: int
    _popen: subprocess.Popen
    _cleanup: tempfile.TemporaryDirectory | None = None

    def wait(self, timeout: float | None = None) -> int:
        result = int(self._popen.wait(timeout=timeout))
        if self._cleanup is not None:
            self._cleanup.cleanup()
            self._cleanup = None
        return result

    def terminate(self) -> None:
        self._popen.terminate()


def _windows_authenticode_evidence(path: Path) -> dict:
    escaped = str(path).replace("'", "''")
    script = (
        f"$p='{escaped}'; $s=Get-AuthenticodeSignature -LiteralPath $p; "
        "$h=$null; if($s.SignerCertificate){"
        "$sha=[Security.Cryptography.SHA256]::Create(); try {"
        "$h=([BitConverter]::ToString($sha.ComputeHash($s.SignerCertificate.RawData))).Replace('-','').ToLowerInvariant()"
        "} finally {$sha.Dispose()}}; "
        "[pscustomobject]@{Status=[string]$s.Status; CertificateSha256=$h; Subject=[string]$s.SignerCertificate.Subject} | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise PlatformLaunchBindingError(
            f"Authenticode verification command failed: {completed.stderr.strip()[:256]}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PlatformLaunchBindingError("Authenticode verification returned malformed JSON") from exc
    return {
        "signatureStatus": str(payload.get("Status") or ""),
        "publisherCertificateSha256": str(payload.get("CertificateSha256") or "").lower(),
        "subject": str(payload.get("Subject") or "")[:256],
    }


def windows_verify_and_launch(
    executable: Path,
    argv: Sequence[str] = (),
    *,
    expected_adapter_sha256: str | None = None,
    expected_publisher_certificate_sha256: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[BoundProcess, dict]:
    if os.name != "nt":
        raise PlatformLaunchBindingError("Windows launch binding is unavailable on this platform")
    path = _require_absolute_executable(executable)
    kernel32 = ctypes.windll.kernel32
    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", ctypes.c_ulong),
            ("ftCreationTimeLow", ctypes.c_ulong),
            ("ftCreationTimeHigh", ctypes.c_ulong),
            ("ftLastAccessTimeLow", ctypes.c_ulong),
            ("ftLastAccessTimeHigh", ctypes.c_ulong),
            ("ftLastWriteTimeLow", ctypes.c_ulong),
            ("ftLastWriteTimeHigh", ctypes.c_ulong),
            ("dwVolumeSerialNumber", ctypes.c_ulong),
            ("nFileSizeHigh", ctypes.c_ulong),
            ("nFileSizeLow", ctypes.c_ulong),
            ("nNumberOfLinks", ctypes.c_ulong),
            ("nFileIndexHigh", ctypes.c_ulong),
            ("nFileIndexLow", ctypes.c_ulong),
        ]

    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.GetFileInformationByHandle.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(BY_HANDLE_FILE_INFORMATION),
    ]
    kernel32.GetFileInformationByHandle.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    handle = kernel32.CreateFileW(
        str(path),
        GENERIC_READ,
        FILE_SHARE_READ,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if handle in {None, INVALID_HANDLE_VALUE}:
        raise PlatformLaunchBindingError("could not lock adapter executable for verified launch")
    try:
        info = BY_HANDLE_FILE_INFORMATION()
        if not kernel32.GetFileInformationByHandle(ctypes.c_void_p(handle), ctypes.byref(info)):
            raise PlatformLaunchBindingError("could not read adapter Windows file identity")
        with path.open("rb") as stream:
            digest = _sha256_stream(stream)
        if expected_adapter_sha256:
            expected_digest = expected_adapter_sha256.removeprefix("sha256:").lower()
            if digest.lower() != expected_digest:
                raise PlatformLaunchBindingError("adapter SHA-256 mismatch")
        signature = _windows_authenticode_evidence(path)
        if signature["signatureStatus"] != "Valid":
            raise PlatformLaunchBindingError("adapter Authenticode signature is not valid")
        if expected_publisher_certificate_sha256:
            expected = expected_publisher_certificate_sha256.removeprefix("sha256:").lower()
            if signature["publisherCertificateSha256"] != expected:
                raise PlatformLaunchBindingError("adapter publisher certificate mismatch")
        file_id = (int(info.nFileIndexHigh) << 32) | int(info.nFileIndexLow)
        process = subprocess.Popen(
            [str(path), *map(str, argv)],
            env=dict(env) if env is not None else None,
        )
        evidence = {
            "binding": "windows-authenticode-fileid-lock-v1",
            "adapterSha256": "sha256:" + digest,
            "publisherCertificateSha256": "sha256:" + signature["publisherCertificateSha256"],
            "signatureStatus": signature["signatureStatus"],
            "volumeSerial": f"{int(info.dwVolumeSerialNumber):08x}",
            "fileId": f"{file_id:016x}",
            "pid": int(process.pid),
            "physicalOutputsArmed": False,
        }
        return BoundProcess(int(process.pid), process), evidence
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def _codesign_evidence(path: Path) -> dict:
    completed = subprocess.run(
        ["/usr/bin/codesign", "-dvvv", "--strict", str(path)],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
        check=False,
    )
    text = completed.stdout
    if completed.returncode != 0:
        raise PlatformLaunchBindingError("macOS code signature verification failed")
    team = re.search(r"^TeamIdentifier=(.+)$", text, re.M)
    cdhash = re.search(r"^CDHash=([0-9A-Fa-f]+)$", text, re.M)
    if not cdhash:
        raise PlatformLaunchBindingError("macOS code signature did not expose a CDHash")
    team_id = team.group(1).strip().upper() if team else ""
    if team_id.lower() == "not set":
        team_id = ""
    return {
        "teamId": team_id,
        "codeDirectoryHash": cdhash.group(1).lower(),
        "raw": text[:1024],
    }


def macos_verify_and_launch(
    executable: Path,
    argv: Sequence[str] = (),
    *,
    expected_adapter_sha256: str | None = None,
    expected_team_id: str | None = None,
    expected_code_directory_hash: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[BoundProcess, dict]:
    if os.uname().sysname != "Darwin":
        raise PlatformLaunchBindingError("macOS launch binding is unavailable on this platform")
    path = _require_absolute_executable(executable)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    temp_dir: tempfile.TemporaryDirectory | None = None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not (info.st_mode & 0o111):
            raise PlatformLaunchBindingError("adapter executable is not a regular executable file")
        duplicate = os.dup(fd)
        with os.fdopen(duplicate, "rb", closefd=True) as stream:
            digest = _sha256_stream(stream)
        if expected_adapter_sha256:
            expected_digest = expected_adapter_sha256.removeprefix("sha256:").lower()
            if digest.lower() != expected_digest:
                raise PlatformLaunchBindingError("adapter SHA-256 mismatch")

        os.lseek(fd, 0, os.SEEK_SET)
        temp_dir = tempfile.TemporaryDirectory(prefix="stagemesh-launch-")
        staged = Path(temp_dir.name) / path.name
        read_fd = os.dup(fd)
        with os.fdopen(read_fd, "rb", closefd=True) as source, staged.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        staged.chmod(0o700)
        with staged.open("rb") as stream:
            staged_digest = _sha256_stream(stream)
        if staged_digest != digest:
            raise PlatformLaunchBindingError("private staged adapter copy hash mismatch")
        signature = _codesign_evidence(staged)

        if expected_team_id:
            wanted = expected_team_id.strip().upper()
            if not _TEAM.fullmatch(wanted) or signature["teamId"] != wanted:
                raise PlatformLaunchBindingError("adapter macOS Team ID mismatch")
        if expected_code_directory_hash:
            wanted_hash = expected_code_directory_hash.removeprefix("cdhash:").lower()
            if not _CDHASH.fullmatch(wanted_hash) or signature["codeDirectoryHash"] != wanted_hash:
                raise PlatformLaunchBindingError("adapter macOS code directory hash mismatch")

        process = subprocess.Popen(
            [str(staged), *map(str, argv)],
            env=dict(env) if env is not None else None,
        )
        evidence = {
            "binding": "macos-codesign-private-copy-v1",
            "adapterSha256": "sha256:" + digest,
            "teamId": signature["teamId"],
            "codeDirectoryHash": "cdhash:" + signature["codeDirectoryHash"],
            "fileId": f"{int(info.st_dev):x}:{int(info.st_ino):x}",
            "privateStagedCopyVerified": True,
            "stagedBasename": staged.name,
            "pid": int(process.pid),
            "physicalOutputsArmed": False,
        }
        bound = BoundProcess(int(process.pid), process, temp_dir)
        temp_dir = None
        return bound, evidence
    finally:
        os.close(fd)
        if temp_dir is not None:
            temp_dir.cleanup()
