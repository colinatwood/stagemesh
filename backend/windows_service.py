"""Minimal Windows Service Control Manager host for StageMesh service adapters.

The host owns only the SCM lifecycle. Product-specific resources are supplied through
on_start/on_stop callbacks so service control remains separate from audio/plugin logic.
"""
from __future__ import annotations

import ctypes
import threading
from typing import Callable

_SERVICE_WIN32_OWN_PROCESS = 0x00000010
_SERVICE_STOPPED = 0x00000001
_SERVICE_START_PENDING = 0x00000002
_SERVICE_STOP_PENDING = 0x00000003
_SERVICE_RUNNING = 0x00000004
_SERVICE_ACCEPT_STOP = 0x00000001
_SERVICE_CONTROL_STOP = 0x00000001
_NO_ERROR = 0


class WindowsServiceError(RuntimeError):
    pass


class SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", ctypes.c_ulong),
        ("dwCurrentState", ctypes.c_ulong),
        ("dwControlsAccepted", ctypes.c_ulong),
        ("dwWin32ExitCode", ctypes.c_ulong),
        ("dwServiceSpecificExitCode", ctypes.c_ulong),
        ("dwCheckPoint", ctypes.c_ulong),
        ("dwWaitHint", ctypes.c_ulong),
    ]


class SERVICE_TABLE_ENTRYW(ctypes.Structure):
    _fields_ = [("lpServiceName", ctypes.c_wchar_p), ("lpServiceProc", ctypes.c_void_p)]


class _WindowsServiceApi:
    def __init__(self) -> None:
        if not hasattr(ctypes, "windll") or not hasattr(ctypes, "WINFUNCTYPE"):
            raise WindowsServiceError("Windows SCM APIs are unavailable on this platform")
        self.advapi32 = ctypes.windll.advapi32
        self.advapi32.StartServiceCtrlDispatcherW.argtypes = [ctypes.POINTER(SERVICE_TABLE_ENTRYW)]
        self.advapi32.StartServiceCtrlDispatcherW.restype = ctypes.c_int
        self.advapi32.RegisterServiceCtrlHandlerExW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self.advapi32.RegisterServiceCtrlHandlerExW.restype = ctypes.c_void_p
        self.advapi32.SetServiceStatus.argtypes = [ctypes.c_void_p, ctypes.POINTER(SERVICE_STATUS)]
        self.advapi32.SetServiceStatus.restype = ctypes.c_int

    def last_error(self) -> int:
        return int(ctypes.get_last_error())


class WindowsServiceHost:
    """Run bounded StageMesh callbacks under the Windows SCM dispatcher."""

    def __init__(
        self,
        service_name: str,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        *,
        api: _WindowsServiceApi | None = None,
    ) -> None:
        name = str(service_name or "").strip()
        if not name or len(name) > 256 or any(ch in name for ch in "\\/"):
            raise ValueError("Windows service name is invalid")
        self.service_name = name
        self.on_start = on_start
        self.on_stop = on_stop
        self._api = api or _WindowsServiceApi()
        self._stop = threading.Event()
        self._status_handle: int | None = None
        self._handler_callback = None
        self._main_callback = None
        self._failure: BaseException | None = None

    def _report(self, state: int, *, exit_code: int = 0, wait_hint_ms: int = 0) -> None:
        if self._status_handle is None:
            return
        controls = _SERVICE_ACCEPT_STOP if state == _SERVICE_RUNNING else 0
        status = SERVICE_STATUS(
            _SERVICE_WIN32_OWN_PROCESS,
            state,
            controls,
            int(exit_code),
            0,
            0,
            int(wait_hint_ms),
        )
        if not self._api.advapi32.SetServiceStatus(ctypes.c_void_p(self._status_handle), ctypes.byref(status)):
            raise WindowsServiceError(f"SetServiceStatus failed ({self._api.last_error()})")

    def run(self) -> None:
        handler_type = ctypes.WINFUNCTYPE(
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        main_type = ctypes.WINFUNCTYPE(None, ctypes.c_ulong, ctypes.POINTER(ctypes.c_wchar_p))

        def handler(control, event_type, event_data, context):
            del event_type, event_data, context
            if int(control) == _SERVICE_CONTROL_STOP:
                try:
                    self._report(_SERVICE_STOP_PENDING, wait_hint_ms=5000)
                finally:
                    self._stop.set()
            return _NO_ERROR

        def service_main(argc, argv):
            del argc, argv
            handle = self._api.advapi32.RegisterServiceCtrlHandlerExW(
                ctypes.c_wchar_p(self.service_name),
                ctypes.cast(self._handler_callback, ctypes.c_void_p),
                None,
            )
            if not handle:
                self._failure = WindowsServiceError(
                    f"RegisterServiceCtrlHandlerExW failed ({self._api.last_error()})"
                )
                return
            self._status_handle = int(handle)
            try:
                self._report(_SERVICE_START_PENDING, wait_hint_ms=10000)
                self.on_start()
                self._report(_SERVICE_RUNNING)
                self._stop.wait()
                self._report(_SERVICE_STOP_PENDING, wait_hint_ms=10000)
                self.on_stop()
                self._report(_SERVICE_STOPPED)
            except BaseException as exc:
                self._failure = exc
                try:
                    self._report(_SERVICE_STOPPED, exit_code=1)
                except BaseException:
                    pass

        self._handler_callback = handler_type(handler)
        self._main_callback = main_type(service_main)
        table = (SERVICE_TABLE_ENTRYW * 2)()
        table[0].lpServiceName = self.service_name
        table[0].lpServiceProc = ctypes.cast(self._main_callback, ctypes.c_void_p)
        table[1].lpServiceName = None
        table[1].lpServiceProc = None
        if not self._api.advapi32.StartServiceCtrlDispatcherW(table):
            raise WindowsServiceError(
                f"StartServiceCtrlDispatcherW failed ({self._api.last_error()})"
            )
        if self._failure is not None:
            raise WindowsServiceError(str(self._failure)) from self._failure
