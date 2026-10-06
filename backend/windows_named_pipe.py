from __future__ import annotations

import ctypes
import re
from dataclasses import dataclass
from typing import Iterable

from local_ipc import MAX_FRAME, _SIZE, validate_windows_pipe_name

_SID = re.compile(r"^S-1-(?:[0-9]+)(?:-[0-9]+)+$", re.I)
_FORBIDDEN_ALIASES = {"WD", "AU", "BU", "AN", "AC", "RC"}
_SDDL_REVISION_1 = 1
_LPTR = 0x0040
_PIPE_ACCESS_DUPLEX = 0x00000003
_FILE_FLAG_FIRST_PIPE_INSTANCE = 0x00080000
_PIPE_TYPE_MESSAGE = 0x00000004
_PIPE_READMODE_MESSAGE = 0x00000002
_PIPE_WAIT = 0x00000000
_ERROR_PIPE_CONNECTED = 535
_ERROR_MORE_DATA = 234
_SE_KERNEL_OBJECT = 6
_DACL_SECURITY_INFORMATION = 0x00000004
_SE_DACL_PROTECTED = 0x1000
_ACCESS_ALLOWED_ACE_TYPE = 0x00
_GENERIC_ALL = 0x10000000
_FILE_ALL_ACCESS = 0x001F01FF
_ACL_SIZE_INFORMATION = 2
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class WindowsNamedPipeError(RuntimeError):
    pass


def normalize_windows_sid(value: str) -> str:
    sid = str(value or "").strip().upper()
    if sid in _FORBIDDEN_ALIASES:
        raise ValueError("broad Windows security principals are not permitted for StageMesh named pipes")
    if not _SID.fullmatch(sid):
        raise ValueError("Windows named-pipe principals must be explicit SID strings")
    return sid


def expected_windows_pipe_sids(allowed_sids: Iterable[str], *, allow_administrators: bool = False) -> tuple[str, ...]:
    normalized = []
    seen = set()
    for value in allowed_sids:
        sid = normalize_windows_sid(value)
        if sid not in seen:
            normalized.append(sid)
            seen.add(sid)
    if not normalized:
        raise ValueError("at least one explicit service/operator SID is required")
    values = ["S-1-5-18"]
    if allow_administrators:
        values.append("S-1-5-32-544")
    values.extend(normalized)
    return tuple(values)


def build_windows_pipe_sddl(allowed_sids: Iterable[str], *, allow_administrators: bool = False) -> str:
    expected = expected_windows_pipe_sids(allowed_sids, allow_administrators=allow_administrators)
    aces = ["(A;;GA;;;SY)"]
    if allow_administrators:
        aces.append("(A;;GA;;;BA)")
    aces.extend(f"(A;;GA;;;{sid})" for sid in expected if sid not in {"S-1-5-18", "S-1-5-32-544"})
    return "D:P" + "".join(aces)


def validate_windows_pipe_acl_facts(policy: "WindowsPipePolicy", facts: dict) -> dict:
    expected = set(expected_windows_pipe_sids(policy.allowed_sids, allow_administrators=policy.allow_administrators))
    actual = set(str(value).upper() for value in facts.get("allowedSids", ()))
    if facts.get("daclProtected") is not True:
        raise PermissionError("Windows named-pipe DACL is not protected")
    if facts.get("nullDacl") is True:
        raise PermissionError("Windows named-pipe DACL must not be null")
    if facts.get("unsupportedAceCount", 0) != 0:
        raise PermissionError("Windows named-pipe DACL contains unsupported ACE types")
    if actual != expected:
        raise PermissionError("Windows named-pipe DACL principals do not match configured policy")
    masks = {str(k).upper(): int(v) for k, v in facts.get("accessMasks", {}).items()}
    for sid in expected:
        if masks.get(sid, -1) not in {_GENERIC_ALL, _FILE_ALL_ACCESS}:
            raise PermissionError(
                f"Windows named-pipe DACL access mask does not match configured policy for {sid}: {masks.get(sid, -1):#x}"
            )
    return {
        "daclProtected": True,
        "allowedSids": sorted(actual),
        "accessMasks": {sid: masks[sid] for sid in sorted(actual)},
    }


@dataclass(frozen=True)
class WindowsPipePolicy:
    allowed_sids: tuple[str, ...]
    allow_administrators: bool = False

    def sddl(self) -> str:
        return build_windows_pipe_sddl(self.allowed_sids, allow_administrators=self.allow_administrators)


class _Win32Api:
    def __init__(self) -> None:
        if not hasattr(ctypes, "windll"):
            raise WindowsNamedPipeError("Win32 named-pipe APIs are unavailable on this platform")
        self.kernel32 = ctypes.windll.kernel32
        self.advapi32 = ctypes.windll.advapi32
        self.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_ulong),
        ]
        self.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = ctypes.c_int
        self.kernel32.CreateNamedPipeW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
        ]
        self.kernel32.CreateNamedPipeW.restype = ctypes.c_void_p
        self.kernel32.ConnectNamedPipe.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.kernel32.ConnectNamedPipe.restype = ctypes.c_int
        self.kernel32.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
        self.kernel32.ReadFile.restype = ctypes.c_int
        self.kernel32.WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
        self.kernel32.WriteFile.restype = ctypes.c_int
        self.kernel32.FlushFileBuffers.argtypes = [ctypes.c_void_p]
        self.kernel32.FlushFileBuffers.restype = ctypes.c_int
        self.kernel32.DisconnectNamedPipe.argtypes = [ctypes.c_void_p]
        self.kernel32.DisconnectNamedPipe.restype = ctypes.c_int
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel32.CloseHandle.restype = ctypes.c_int
        self.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self.kernel32.LocalFree.restype = ctypes.c_void_p
        self.advapi32.GetSecurityInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.advapi32.GetSecurityInfo.restype = ctypes.c_ulong
        self.advapi32.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ulong)]
        self.advapi32.GetSecurityDescriptorControl.restype = ctypes.c_int
        self.advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
        self.advapi32.ConvertSidToStringSidW.restype = ctypes.c_int
        self.advapi32.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]
        self.advapi32.GetAclInformation.restype = ctypes.c_int
        self.advapi32.GetAce.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
        self.advapi32.GetAce.restype = ctypes.c_int

    def last_error(self) -> int:
        return int(ctypes.get_last_error())


def inspect_windows_pipe_dacl(handle: int, api: _Win32Api) -> dict:
    class ACL_SIZE_INFORMATION(ctypes.Structure):
        _fields_ = [("AceCount", ctypes.c_ulong), ("AclBytesInUse", ctypes.c_ulong), ("AclBytesFree", ctypes.c_ulong)]

    class ACE_HEADER(ctypes.Structure):
        _fields_ = [("AceType", ctypes.c_ubyte), ("AceFlags", ctypes.c_ubyte), ("AceSize", ctypes.c_ushort)]

    class ACCESS_ALLOWED_ACE(ctypes.Structure):
        _fields_ = [("Header", ACE_HEADER), ("Mask", ctypes.c_ulong), ("SidStart", ctypes.c_ulong)]

    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    result = api.advapi32.GetSecurityInfo(
        ctypes.c_void_p(handle),
        _SE_KERNEL_OBJECT,
        _DACL_SECURITY_INFORMATION,
        None,
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != 0 or not descriptor.value:
        raise WindowsNamedPipeError(f"could not inspect Windows named-pipe DACL ({result})")
    try:
        control = ctypes.c_ushort(0)
        revision = ctypes.c_ulong(0)
        if not api.advapi32.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise WindowsNamedPipeError(f"could not inspect Windows security-descriptor control ({api.last_error()})")
        if not dacl.value:
            return {
                "daclProtected": bool(control.value & _SE_DACL_PROTECTED),
                "nullDacl": True,
                "allowedSids": [],
                "accessMasks": {},
                "unsupportedAceCount": 0,
            }
        info = ACL_SIZE_INFORMATION()
        if not api.advapi32.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), _ACL_SIZE_INFORMATION):
            raise WindowsNamedPipeError(f"could not inspect Windows named-pipe ACL ({api.last_error()})")
        allowed = []
        masks = {}
        unsupported = 0
        for index in range(int(info.AceCount)):
            ace_ptr = ctypes.c_void_p()
            if not api.advapi32.GetAce(dacl, index, ctypes.byref(ace_ptr)) or not ace_ptr.value:
                raise WindowsNamedPipeError(f"could not inspect Windows named-pipe ACE ({api.last_error()})")
            header = ctypes.cast(ace_ptr, ctypes.POINTER(ACE_HEADER)).contents
            if int(header.AceType) != _ACCESS_ALLOWED_ACE_TYPE:
                unsupported += 1
                continue
            ace = ctypes.cast(ace_ptr, ctypes.POINTER(ACCESS_ALLOWED_ACE)).contents
            sid_ptr = ctypes.c_void_p(ace_ptr.value + ACCESS_ALLOWED_ACE.SidStart.offset)
            sid_text = ctypes.c_wchar_p()
            if not api.advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_text)) or not sid_text.value:
                raise WindowsNamedPipeError(f"could not stringify Windows named-pipe SID ({api.last_error()})")
            try:
                sid = sid_text.value.upper()
            finally:
                api.kernel32.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
            allowed.append(sid)
            masks[sid] = int(ace.Mask)
        return {
            "daclProtected": bool(control.value & _SE_DACL_PROTECTED),
            "nullDacl": False,
            "allowedSids": allowed,
            "accessMasks": masks,
            "unsupportedAceCount": unsupported,
        }
    finally:
        api.kernel32.LocalFree(descriptor)


def attest_windows_pipe_dacl(handle: int, policy: WindowsPipePolicy, api: _Win32Api) -> dict:
    return validate_windows_pipe_acl_facts(policy, inspect_windows_pipe_dacl(handle, api))


class Win32MessagePipeConnection:
    def __init__(self, handle: int, api: _Win32Api) -> None:
        self._handle = handle
        self._api = api
        self._closed = False

    def recv_bytes(self, maxlength: int | None = None) -> bytes:
        if self._closed:
            raise EOFError("Windows named-pipe connection is closed")
        limit = MAX_FRAME + _SIZE.size if maxlength is None else int(maxlength)
        if limit <= 0 or limit > MAX_FRAME + _SIZE.size:
            raise ValueError("Windows named-pipe receive bound is invalid")
        buffer = ctypes.create_string_buffer(limit)
        read = ctypes.c_ulong(0)
        ok = self._api.kernel32.ReadFile(ctypes.c_void_p(self._handle), buffer, ctypes.c_ulong(limit), ctypes.byref(read), None)
        if not ok:
            err = self._api.last_error()
            if err == _ERROR_MORE_DATA:
                raise ValueError("Windows named-pipe message exceeds transport bound")
            raise EOFError(f"Windows named-pipe read failed ({err})")
        return bytes(buffer.raw[: int(read.value)])

    def send_bytes(self, payload: bytes) -> None:
        if self._closed:
            raise EOFError("Windows named-pipe connection is closed")
        data = bytes(payload)
        if len(data) > MAX_FRAME + _SIZE.size:
            raise ValueError("Windows named-pipe message exceeds transport bound")
        written = ctypes.c_ulong(0)
        buf = ctypes.create_string_buffer(data, len(data))
        ok = self._api.kernel32.WriteFile(ctypes.c_void_p(self._handle), buf, ctypes.c_ulong(len(data)), ctypes.byref(written), None)
        if not ok or int(written.value) != len(data):
            raise WindowsNamedPipeError(f"Windows named-pipe write failed ({self._api.last_error()})")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._api.kernel32.FlushFileBuffers(ctypes.c_void_p(self._handle))
        finally:
            self._api.kernel32.DisconnectNamedPipe(ctypes.c_void_p(self._handle))
            self._api.kernel32.CloseHandle(ctypes.c_void_p(self._handle))


class Win32NamedPipeListener:
    acl_policy_enforced = True

    def __init__(self, name: str, policy: WindowsPipePolicy, *, api: _Win32Api | None = None) -> None:
        self.name = validate_windows_pipe_name(name)
        self.policy = policy
        self._api = api or _Win32Api()
        self._closed = False
        self.security_descriptor_sddl = policy.sddl()

    def _security_attributes(self):
        descriptor = ctypes.c_void_p()
        ok = self._api.advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            ctypes.c_wchar_p(self.security_descriptor_sddl),
            ctypes.c_ulong(_SDDL_REVISION_1),
            ctypes.byref(descriptor),
            None,
        )
        if not ok or not descriptor.value:
            raise WindowsNamedPipeError(f"could not create Windows named-pipe security descriptor ({self._api.last_error()})")

        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("nLength", ctypes.c_ulong), ("lpSecurityDescriptor", ctypes.c_void_p), ("bInheritHandle", ctypes.c_int)]

        attrs = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), descriptor, 0)
        return descriptor, attrs

    def accept(self) -> Win32MessagePipeConnection:
        if self._closed:
            raise WindowsNamedPipeError("Windows named-pipe listener is closed")
        descriptor, attrs = self._security_attributes()
        try:
            handle = self._api.kernel32.CreateNamedPipeW(
                ctypes.c_wchar_p(self.name),
                ctypes.c_ulong(_PIPE_ACCESS_DUPLEX | _FILE_FLAG_FIRST_PIPE_INSTANCE),
                ctypes.c_ulong(_PIPE_TYPE_MESSAGE | _PIPE_READMODE_MESSAGE | _PIPE_WAIT),
                ctypes.c_ulong(1),
                ctypes.c_ulong(MAX_FRAME + _SIZE.size),
                ctypes.c_ulong(MAX_FRAME + _SIZE.size),
                ctypes.c_ulong(5000),
                ctypes.byref(attrs),
            )
            if handle == _INVALID_HANDLE_VALUE or handle is None:
                raise WindowsNamedPipeError(f"could not create Windows named pipe ({self._api.last_error()})")
            try:
                attest_windows_pipe_dacl(int(handle), self.policy, self._api)
            except Exception:
                self._api.kernel32.CloseHandle(ctypes.c_void_p(handle))
                raise
            connected = self._api.kernel32.ConnectNamedPipe(ctypes.c_void_p(handle), None)
            if not connected and self._api.last_error() != _ERROR_PIPE_CONNECTED:
                self._api.kernel32.CloseHandle(ctypes.c_void_p(handle))
                raise WindowsNamedPipeError(f"could not accept Windows named-pipe client ({self._api.last_error()})")
            return Win32MessagePipeConnection(int(handle), self._api)
        finally:
            self._api.kernel32.LocalFree(descriptor)

    def close(self) -> None:
        self._closed = True


def create_secure_windows_pipe_listener(
    name: str,
    allowed_sids: Iterable[str],
    *,
    allow_administrators: bool = False,
    api: _Win32Api | None = None,
) -> Win32NamedPipeListener:
    policy = WindowsPipePolicy(tuple(allowed_sids), allow_administrators=allow_administrators)
    return Win32NamedPipeListener(name, policy, api=api)
