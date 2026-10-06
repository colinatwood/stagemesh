from __future__ import annotations

import json
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class PeerPushResult:
    ok: bool
    status: int
    error: str | None = None


class ReplicationPushClient:
    """Tiny authenticated-envelope transport for primary -> standby state.

    Authentication lives in the signed/HMAC replication envelope. This class
    intentionally owns only delivery, timeout/error reporting, and heartbeat
    bookkeeping so the transport can later be replaced by QUIC, a local socket,
    or another UPP transport without changing replica semantics.
    """

    def __init__(self, peer_url: str, *, timeout_seconds: float = 0.75) -> None:
        self._lock = RLock()
        self._peer_url = peer_url.rstrip("/")
        self._timeout = max(0.05, min(float(timeout_seconds), 5.0))
        self._last_attempt_at = 0.0
        self._last_success_at = 0.0
        self._last_revision = 0
        self._pushes = 0
        self._failures = 0
        self._last_error: str | None = None
        self._last_status = 0
        self._handoff_ready_attempts = 0
        self._handoff_ready_deliveries = 0
        self._handoff_ready_failures = 0
        self._handoff_ready_last_error: str | None = None

    @property
    def configured(self) -> bool:
        return self._peer_url.startswith("http://") or self._peer_url.startswith("https://")

    def push(self, envelope: dict[str, Any]) -> PeerPushResult:
        if not self.configured:
            return PeerPushResult(False, 0, "peer URL is not configured")
        payload = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        request = Request(
            self._peer_url + "/api/v1/replication/apply",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "StageMesh-Replication/1"},
        )
        with self._lock:
            self._last_attempt_at = monotonic()
        try:
            with urlopen(request, timeout=self._timeout) as response:
                status = int(getattr(response, "status", 200))
                response.read(4096)
            if not 200 <= status < 300:
                raise OSError(f"peer returned HTTP {status}")
            with self._lock:
                self._last_success_at = monotonic()
                self._last_revision = int(envelope.get("revision", 0))
                self._pushes += 1
                self._last_status = status
                self._last_error = None
            return PeerPushResult(True, status)
        except HTTPError as exc:
            error = f"peer HTTP {exc.code}"
            status = int(exc.code)
        except (URLError, OSError, TimeoutError) as exc:
            error = str(getattr(exc, "reason", exc))
            status = 0
        with self._lock:
            self._failures += 1
            self._last_status = status
            self._last_error = error[:240]
        return PeerPushResult(False, status, error[:240])

    def deliver_planned_handoff_ready(self, receipt: dict[str, Any]) -> PeerPushResult:
        with self._lock:
            self._handoff_ready_attempts += 1
        if not self.configured:
            result = PeerPushResult(False, 0, "peer URL is not configured")
            with self._lock:
                self._handoff_ready_failures += 1
                self._handoff_ready_last_error = result.error
            return result
        payload = json.dumps(receipt, separators=(",", ":")).encode("utf-8")
        request = Request(
            self._peer_url + "/api/v1/handoff/planned/peer-ready",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "StageMesh-Handoff/1"},
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                status = int(getattr(response, "status", 200))
                response.read(4096)
            result = PeerPushResult(
                200 <= status < 300,
                status,
                None if 200 <= status < 300 else f"peer returned HTTP {status}",
            )
        except HTTPError as exc:
            result = PeerPushResult(False, int(exc.code), f"peer HTTP {exc.code}")
        except (URLError, OSError, TimeoutError) as exc:
            result = PeerPushResult(False, 0, str(getattr(exc, "reason", exc))[:240])
        with self._lock:
            if result.ok:
                self._handoff_ready_deliveries += 1
                self._handoff_ready_last_error = None
            else:
                self._handoff_ready_failures += 1
                self._handoff_ready_last_error = result.error
        return result

    def status(self) -> dict[str, Any]:
        with self._lock:
            now = monotonic()
            return {
                "configured": self.configured,
                "peerUrl": self._peer_url or None,
                "pushes": self._pushes,
                "failures": self._failures,
                "lastRevision": self._last_revision,
                "lastHttpStatus": self._last_status or None,
                "lastError": self._last_error,
                "lastAttemptAgeMs": int((now - self._last_attempt_at) * 1000) if self._last_attempt_at else None,
                "lastSuccessAgeMs": int((now - self._last_success_at) * 1000) if self._last_success_at else None,
                "handoffReadyAttempts": self._handoff_ready_attempts,
                "handoffReadyDeliveries": self._handoff_ready_deliveries,
                "handoffReadyFailures": self._handoff_ready_failures,
                "handoffReadyLastError": self._handoff_ready_last_error,
            }
