#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import mimetypes
import os
import threading
import io
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs, urlparse

from runtime import StageForgeRuntime
from state import RevisionConflict
from stage_templates import StageTemplateConflict
from adaptation import AdaptationRevisionConflict
from http_credentials import credential_environment
from http_authorization import authorization_policy, authorize_control_request, specialized_authorization_route, classify_control_action
from http_deployment import validate_proxy_https_profile


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = Path(os.environ.get("STAGEFORGE_FRONTEND_DIR", str(ROOT / "frontend"))).resolve()
DATA_DIR = Path(os.environ.get("STAGEFORGE_DATA_DIR", str(ROOT / ".runtime"))).resolve()
RUNTIME = StageForgeRuntime(DATA_DIR)
MONITOR_READ_PATHS = frozenset({"/healthz", "/api/v1/native", "/api/v1/node"})
DESKTOP_SESSION_COOKIE = "stagemesh-session"

# Known control-plane operations that can perform filesystem, discovery, graph/planning
# or catalog work. Admission is deliberately non-blocking so these requests cannot
# consume all HTTP workers while waiting on one another. In-flight work is not
# force-cancelled: rejecting excess admission is safer than timing out a mutation.
_EXPENSIVE_OPERATION_EXACT = {
    ("POST", "/api/v1/checkpoint"): "maintenance",
    ("POST", "/api/v1/daw/temp-resources/cleanup"): "maintenance",
    ("GET", "/api/v1/public-record/verify"): "maintenance",
    ("GET", "/api/v1/security/authorization-audit"): "maintenance",
    ("POST", "/api/v1/community/public-record/reconcile"): "maintenance",
    ("POST", "/api/v1/audio/scan"): "discovery",
    ("POST", "/api/v1/midi/scan"): "discovery",
    ("GET", "/api/v1/hardware/diagnostics"): "discovery",
    ("POST", "/api/v1/compatibility/show-plan"): "planning",
    ("POST", "/api/v1/venue/plan"): "planning",
    ("POST", "/api/v1/technology/negotiate"): "planning",
    ("GET", "/api/v1/technology/assessment"): "planning",
    ("POST", "/api/v1/interoperability/offer"): "planning",
    ("POST", "/api/v1/daw/media/ingest"): "storage",
    ("POST", "/api/v1/daw/media/verify"): "storage",
    ("POST", "/api/v1/daw/render"): "storage",
    ("POST", "/api/v1/daw/autosave"): "storage",
}


def expensive_operation_class(method: str, path: str) -> str | None:
    kind = _EXPENSIVE_OPERATION_EXACT.get((method.upper(), path))
    if kind is not None:
        return kind
    if method.upper() == "POST" and path.startswith("/api/v1/community/proposals/") and path.endswith("/email-voters"):
        return "external"
    return None


def token_matches(configured: str, supplied: str) -> bool:
    # HTTP tokens are ASCII. Invalid input must deny, not raise TypeError.
    return bool(configured and supplied and configured.isascii() and supplied.isascii()
                and hmac.compare_digest(configured, supplied))


def desktop_cookie_token(headers: Mapping[str, str], client_host: str, environ: Mapping[str, str]) -> str:
    if environ.get("STAGEFORGE_RUNTIME_MODE", "").strip().lower() != "desktop":
        return ""
    try:
        if not ipaddress.ip_address(client_host).is_loopback:
            return ""
    except ValueError:
        return ""
    raw_cookie = headers.get("Cookie", "")
    if len(raw_cookie) > 4096:
        return ""
    values = []
    for part in raw_cookie.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == DESKTOP_SESSION_COOKIE:
            values.append(value.strip())
    return values[0] if len(values) == 1 else ""


def validate_http_boundary(headers: Mapping[str, str], client_host: str, path: str, method: str, environ: Mapping[str, str] | None = None) -> None:
    """Reject DNS-rebinding/cross-origin requests and authenticate remote API access."""
    env=os.environ if environ is None else environ
    authority=headers.get("Host","").strip()
    try:
        parsed_host=urlparse("//"+authority);hostname=(parsed_host.hostname or "").lower();host_port=parsed_host.port
    except ValueError as exc:raise ValueError("invalid Host header") from exc
    allowed={"localhost","127.0.0.1","::1"}
    allowed.update(value.strip().lower().rstrip(".") for value in env.get("STAGEFORGE_ALLOWED_HOSTS","").split(",") if value.strip())
    if (not hostname or hostname.rstrip(".") not in allowed or parsed_host.username is not None
            or parsed_host.password is not None or parsed_host.path or parsed_host.query or parsed_host.fragment):
        raise PermissionError("request Host is not allowed")
    origin=headers.get("Origin","").strip()
    if origin:
        parsed_origin=urlparse(origin)
        if (parsed_origin.scheme not in {"http","https"} or not parsed_origin.hostname
                or parsed_origin.username is not None or parsed_origin.password is not None
                or parsed_origin.path or parsed_origin.query or parsed_origin.fragment):
            raise PermissionError("request Origin is not allowed")
        configured={value.strip().rstrip("/") for value in env.get("STAGEFORGE_ALLOWED_ORIGINS","").split(",") if value.strip()}
        default_port=443 if parsed_origin.scheme=="https" else 80
        same_host=(parsed_origin.scheme == "http" and parsed_origin.hostname.lower().rstrip(".")==hostname.rstrip(".") and (parsed_origin.port or default_port)==(host_port or 80))
        if origin.rstrip("/") not in configured and not same_host:raise PermissionError("request Origin is not allowed")
    try:loopback=ipaddress.ip_address(client_host).is_loopback
    except ValueError:loopback=False
    require_token=env.get("STAGEFORGE_REQUIRE_API_TOKEN","").strip().lower() in {"1","true","yes","on"}
    supplied = headers.get("X-StageForge-API-Token", "")
    if not supplied:
        supplied = desktop_cookie_token(headers, client_host, env)
    monitor = env.get("STAGEFORGE_MONITOR_API_TOKEN", "")
    control = env.get("STAGEFORGE_API_TOKEN", "")
    if monitor and token_matches(monitor, control):
        raise PermissionError("monitor and control credentials must be distinct")
    monitor_request = token_matches(monitor, supplied)
    if monitor_request and (method != "GET" or path not in MONITOR_READ_PATHS):
        raise PermissionError("monitor credential is not authorized for this route")
    if (path.startswith("/api/") or path == "/healthz") and (not loopback or require_token):
        if not monitor_request and not token_matches(control, supplied):raise PermissionError("remote API authentication failed")
    if method in {"POST","PATCH","PUT","DELETE"} and path.startswith("/api/"):
        content_type=headers.get("Content-Type","").split(";",1)[0].strip().lower()
        if content_type!="application/json":raise ValueError("API mutations require Content-Type application/json")


class RequestRateLimiter:
    """Bounded per-peer and aggregate token buckets; no forwarded identity trust."""
    def __init__(self, clock=time.monotonic, peer_rate=100, peer_burst=200,
                 total_rate=200, total_burst=400, max_peers=1024):
        self.clock = clock
        self.peer_rate, self.peer_burst = peer_rate, peer_burst
        self.total_rate, self.total_burst = total_rate, total_burst
        self.max_peers = max_peers
        self.peers = {}
        self.total = (float(total_burst), clock())
        self.lock = threading.Lock()

    def allow(self, peer):
        with self.lock:
            now = self.clock()
            tokens, stamp = self.total
            total = min(self.total_burst, tokens + max(0, now - stamp) * self.total_rate)
            self.total = (total, now)
            if peer not in self.peers and len(self.peers) >= self.max_peers:
                # Only forget fully refilled identities, never reset depleted buckets.
                self.peers = {key: value for key, value in self.peers.items()
                              if value[0] + max(0, now - value[1]) * self.peer_rate < self.peer_burst}
                if len(self.peers) >= self.max_peers:
                    return False
            tokens, stamp = self.peers.get(peer, (float(self.peer_burst), now))
            available = min(self.peer_burst, tokens + max(0, now - stamp) * self.peer_rate)
            if total < 1 or available < 1:
                self.peers[peer] = (available, now)
                return False
            self.total = (total - 1, now)
            self.peers[peer] = (available - 1, now)
            return True


class OperationCostLimiter:
    """Non-blocking admission for known expensive control-plane work."""
    DEFAULT_CLASS_LIMITS = {"maintenance": 1, "discovery": 2, "planning": 3, "storage": 2, "external": 2}

    def __init__(self, total_limit: int = 4, class_limits: Mapping[str, int] | None = None):
        self.total_limit = max(1, int(total_limit))
        limits = dict(self.DEFAULT_CLASS_LIMITS if class_limits is None else class_limits)
        self.class_limits = {str(name): max(1, int(limit)) for name, limit in limits.items()}
        self._total = threading.BoundedSemaphore(self.total_limit)
        self._classes = {name: threading.BoundedSemaphore(limit) for name, limit in self.class_limits.items()}
        self._lock = threading.Lock()
        self._active = {name: 0 for name in self.class_limits}
        self._rejected = {name: 0 for name in self.class_limits}

    def acquire(self, kind: str) -> bool:
        slot = self._classes.get(kind)
        if slot is None:
            raise ValueError("unknown operation cost class")
        if not self._total.acquire(blocking=False):
            with self._lock:self._rejected[kind] += 1
            return False
        if not slot.acquire(blocking=False):
            self._total.release()
            with self._lock:self._rejected[kind] += 1
            return False
        with self._lock:self._active[kind] += 1
        return True

    def release(self, kind: str) -> None:
        slot = self._classes[kind]
        with self._lock:
            if self._active[kind] <= 0:
                raise RuntimeError("operation cost slot released without acquisition")
            self._active[kind] -= 1
        slot.release();self._total.release()

    def status(self) -> dict[str, object]:
        with self._lock:
            return {"totalLimit": self.total_limit, "classLimits": dict(self.class_limits),
                    "active": dict(self._active), "rejected": dict(self._rejected)}


class StageForgeHTTPServer(ThreadingHTTPServer):
    """Bound accepted worker connections before creating handler threads."""
    daemon_threads = True
    max_connections = 32
    max_event_streams = 8
    socket_timeout = 10.0
    request_read_timeout = 15.0
    max_expensive_operations = 4
    expensive_class_limits = OperationCostLimiter.DEFAULT_CLASS_LIMITS

    def __init__(self, *args, **kwargs):
        self.request_limiter = RequestRateLimiter()
        self.operation_limiter = OperationCostLimiter(self.max_expensive_operations, self.expensive_class_limits)
        self._connection_slots = threading.BoundedSemaphore(self.max_connections)
        self._event_slots = threading.BoundedSemaphore(min(self.max_event_streams, max(0, self.max_connections - 1)))
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._connection_slots.acquire(blocking=False):
            # Never block the accept loop trying to send to an unknown peer.
            self.shutdown_request(request)
            return
        try:
            request.settimeout(self.socket_timeout)
            super().process_request(request, client_address)
        except BaseException:
            self._connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()


class DeadlineReader(io.RawIOBase):
    """Apply the remaining monotonic budget before every underlying read."""
    def __init__(self, raw, handler):
        self.raw = raw
        self.handler = handler

    def readable(self):
        return True

    def readinto(self, buffer):
        handler = self.handler
        remaining = handler._read_deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("request receive deadline exceeded")
        handler.connection.settimeout(min(handler.server.socket_timeout, remaining))
        return self.raw.readinto(buffer)

    def close(self):
        try:
            self.raw.close()
        finally:
            super().close()


class StageForgeHandler(BaseHTTPRequestHandler):
    server_version = "StageForgeDev/0.7"
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        if isinstance(self.server, StageForgeHTTPServer):
            self.rfile.close()
            self.rfile = io.BufferedReader(DeadlineReader(self.connection.makefile('rb', buffering=0), self))

    def handle_one_request(self):
        self._credential_snapshot = None
        self._authorization_loaded = False
        self._authorization_snapshot = None
        self._operation_cost_kind = None
        self._read_deadline = time.monotonic() + getattr(self.server, 'request_read_timeout', 15.0)
        try:
            super().handle_one_request()
        finally:
            kind = getattr(self, "_operation_cost_kind", None)
            limiter = getattr(self.server, "operation_limiter", None)
            if kind is not None and limiter is not None:
                self._operation_cost_kind = None
                limiter.release(kind)

    def _credentials(self):
        if getattr(self, '_credential_snapshot', None) is None:
            self._credential_snapshot = credential_environment()
        return self._credential_snapshot

    def _authorization_policy(self):
        if not getattr(self, '_authorization_loaded', False):
            self._authorization_snapshot = authorization_policy(self._credentials())
            self._authorization_loaded = True
        return self._authorization_snapshot

    def _finish_request_read(self):
        if isinstance(self.server, StageForgeHTTPServer):
            if time.monotonic() >= self._read_deadline:
                raise TimeoutError("request receive deadline exceeded")
            self.connection.settimeout(self.server.socket_timeout)

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        # Reject ambiguous framing before dispatch (including Expect: 100-continue).
        lengths = self.headers.get_all("Content-Length", [])
        security_headers = ('Origin', 'Content-Type', 'X-StageForge-API-Token',
                            'Cookie', 'X-StageForge-Desktop-Token',
                            'X-StageForge-Admin-Token', 'X-StageForge-Adapter-Token',
                            'X-StageForge-Authenticated-User', 'X-StageForge-Auth-Proxy-Token',
                            'X-StageForge-Command-Id')
        invalid = (len(self.headers.get_all("Host", [])) != 1
                   or any(len(self.headers.get_all(name, [])) > 1 for name in security_headers)
                   or bool(self.headers.get_all("Transfer-Encoding", []))
                   or len(lengths) > 1
                   or bool(lengths and (len(lengths[0]) > 10 or not lengths[0].isascii() or not lengths[0].isdecimal())))
        if invalid:
            self._json(400, {"error": "invalid or unsupported request framing"})
            return False
        if self.command == "GET" and lengths and int(lengths[0]):
            self._json(400, {"error": "GET request body is not supported"})
            return False
        if self.command not in {"POST", "PATCH"}:
            self._finish_request_read()
        limiter = getattr(self.server, "request_limiter", None)
        if limiter is not None and not limiter.allow(self.client_address[0]):
            self._json(429, {"error": "request rate limit exceeded"}, {"Retry-After": "2"})
            return False
        return True

    def handle_expect_100(self) -> bool:
        self._json(417, {"error": "Expect: 100-continue is not supported"})
        return False

    def log_message(self, fmt: str, *args) -> None:
        # Base-handler diagnostics can include attacker-controlled request lines.
        print('[stageforge] HTTP diagnostic; request details omitted')

    def log_request(self, code='-', size='-') -> None:
        method = getattr(self, 'command', '')
        if method not in {'GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'}:
            method = 'OTHER'
        status = int(code) if str(code).isdigit() else 0
        print(json.dumps({'component': 'http', 'method': method, 'status': status}, separators=(',', ':')))

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

    def _guard_request(self, path: str) -> bool:
        try:
            validate_http_boundary(self.headers,self.client_address[0],path,self.command,self._credentials())
            self._enforce_control_roles(path)
        except PermissionError as exc:self._json(403,{"error":str(exc)});return False
        except ValueError as exc:self._json(400,{"error":str(exc)});return False
        except OSError:self._json(503,{"error":"authorization audit unavailable"});return False
        kind = expensive_operation_class(self.command, path)
        limiter = getattr(self.server, "operation_limiter", None)
        if kind is not None and limiter is not None:
            if not limiter.acquire(kind):
                self._json(503,{"error":"operation capacity exceeded","operationClass":kind},{"Retry-After":"1"})
                return False
            self._operation_cost_kind = kind
        return True

    def _enforce_control_roles(self, path: str) -> None:
        if self.command not in {"POST", "PATCH", "PUT", "DELETE"} or not path.startswith("/api/v1/"):
            return
        if specialized_authorization_route(self.command, path):
            return
        policy = self._authorization_policy()
        if policy is None:
            return
        # The trusted proxy token authenticates this identity header. A shared API
        # token alone never acquires a per-user role when policy mode is enabled.
        actor = self._authenticated_user_id()
        decision = authorize_control_request(policy, actor, self.command, path)
        if decision is None:
            return
        event = {
            "type": "http-authorization",
            "timestampNs": time.time_ns(),
            "actor": decision.actor,
            "roles": list(decision.roles),
            "method": self.command,
            "action": decision.action,
            "target": decision.target,
            "decision": "allow" if decision.allowed else "deny",
            "reason": decision.reason,
        }
        # Persist the decision before route code or request-body execution. Losing
        # the durable audit is fail-closed for role-controlled mutations.
        RUNTIME.repository.append_authorization_audit(event)
        if not decision.allowed:
            raise PermissionError("authenticated user is not authorized for this control action")

    def _json(self, status: int, payload: object, extra_headers: dict[str, str] | None = None) -> None:
        # Unread rejected body bytes must never become a subsequent request.
        if status >= 400:
            self.close_connection = True
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        if self.close_connection:
            self.send_header("Connection", "close")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _raw(self, status: int, data: bytes, content_type: str, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _state_headers(self, state: dict, deduplicated: bool = False, resource_key: str | None = None) -> dict[str, str]:
        headers = {
            "ETag": f'"rev-{state["revision"]}"',
            "X-UPP-API-Version": str(state.get("apiVersion", 1)),
            "X-UPP-Minimum-Reader-Version": str((state.get("compatibility") or {}).get("minimumReaderApiVersion", 1)),
        }
        if resource_key:
            resource_revision = (state.get("resourceRevisions") or {}).get(resource_key)
            if resource_revision is not None:
                headers["X-StageForge-Resource-ETag"] = f'"{resource_key}@{resource_revision}"'
        if deduplicated:
            headers["X-StageForge-Deduplicated"] = "true"
        return headers

    def _append_specialized_authorization(
        self, credential_class: str, allowed: bool, reason: str, *,
        action: str | None = None, actor: str | None = None, key_id: str | None = None,
    ) -> None:
        # Private authorization helpers are also exercised directly by focused
        # unit tests and non-HTTP compatibility seams. Only emit a durable
        # request decision when a real BaseHTTPRequestHandler request context
        # exists; production HTTP dispatch always provides both attributes.
        raw_path = getattr(self, "path", None)
        method = getattr(self, "command", None)
        if not isinstance(raw_path, str) or not raw_path or not isinstance(method, str) or not method:
            return
        path = urlparse(raw_path).path
        if action is None:
            classified, target, _ = classify_control_action(method, path)
            action = f"{credential_class}.{classified}"
        else:
            target = None
        event = {
            "type": "specialized-authorization",
            "timestampNs": time.time_ns(),
            "actor": actor,
            "roles": [],
            "method": method,
            "action": action,
            "target": target,
            "decision": "allow" if allowed else "deny",
            "reason": str(reason)[:128],
            "credentialClass": credential_class,
        }
        if key_id:
            event["keyId"] = str(key_id)[:64]
        try:
            RUNTIME.repository.append_authorization_audit(event)
        except OSError:
            raise RuntimeError("authorization audit unavailable") from None

    def _machine_authorization_hook(self, action: str):
        def record(allowed: bool, reason: str, metadata: dict[str, Any]) -> None:
            self._append_specialized_authorization(
                "machine-hmac", allowed, reason, action=action,
                actor=metadata.get("actor") if allowed else None,
                key_id=metadata.get("keyId") if allowed else None,
            )
        return record

    def _require_admin_auth(self) -> None:
        configured = self._credentials().get("STAGEFORGE_ADMIN_API_TOKEN", "")
        supplied = self.headers.get("X-StageForge-Admin-Token", "")
        if configured:
            allowed = token_matches(configured, supplied)
            self._append_specialized_authorization(
                "admin-token", allowed, "admin-token" if allowed else "admin-token-invalid"
            )
            if not allowed:
                raise PermissionError("admin API authentication failed")
            return
        local_allowed = False
        try:
            local_allowed = (
                ipaddress.ip_address(self.client_address[0]).is_loopback
                and self._credentials().get("STAGEFORGE_REQUIRE_API_TOKEN", "").strip().lower() not in {"1", "true", "yes", "on"}
            )
        except ValueError:
            local_allowed = False
        self._append_specialized_authorization(
            "loopback-admin", local_allowed, "loopback-development" if local_allowed else "admin-credential-required"
        )
        if local_allowed:
            return
        raise PermissionError("admin API requires localhost or STAGEFORGE_ADMIN_API_TOKEN")

    def _authenticated_user_id(self) -> str | None:
        user_id = self.headers.get("X-StageForge-Authenticated-User", "").strip()
        if len(user_id) > 128:
            raise PermissionError("authenticated user identity is too long")
        if any(ord(char) < 32 or ord(char) == 127 for char in user_id):
            raise PermissionError("authenticated user identity contains control characters")
        if not user_id:
            return None
        configured = self._credentials().get("STAGEFORGE_AUTH_PROXY_TOKEN", "")
        supplied = self.headers.get("X-StageForge-Auth-Proxy-Token", "")
        if not token_matches(configured, supplied):
            raise PermissionError("authenticated user identity requires a trusted auth proxy token")
        return user_id

    def _require_adapter_report_auth(self) -> None:
        configured = self._credentials().get("STAGEFORGE_ADAPTER_REPORT_TOKEN", "")
        supplied = self.headers.get("X-StageForge-Adapter-Token", "")
        if configured:
            allowed = token_matches(configured, supplied)
            self._append_specialized_authorization(
                "adapter-token", allowed, "adapter-token" if allowed else "adapter-token-invalid"
            )
            if not allowed:
                raise PermissionError("adapter execution report authentication failed")
            return
        local_allowed = False
        try:
            local_allowed = (
                ipaddress.ip_address(self.client_address[0]).is_loopback
                and self._credentials().get("STAGEFORGE_REQUIRE_API_TOKEN", "").strip().lower() not in {"1", "true", "yes", "on"}
            )
        except ValueError:
            local_allowed = False
        self._append_specialized_authorization(
            "loopback-adapter", local_allowed, "loopback-development" if local_allowed else "adapter-credential-required"
        )
        if local_allowed:
            return
        raise PermissionError("adapter execution reports require localhost or STAGEFORGE_ADAPTER_REPORT_TOKEN")

    def _read_json(self, max_bytes: int = 64 * 1024) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > max_bytes:
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        if length and len(raw) != length:
            raise ValueError("incomplete request body")
        self._finish_request_read()
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _expected_revision(self) -> int | None:
        raw = self.headers.get("If-Match")
        if not raw or raw.strip() == "*":
            return None
        raw = raw.strip().strip('"')
        if raw.startswith("rev-"):
            raw = raw[4:]
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError("If-Match must be an ETag like \"rev-12\"") from exc


    def _expected_resource_revision(self, resource_key: str) -> int | None:
        raw = self.headers.get("X-StageForge-Resource-If-Match")
        if not raw:
            return None
        token = raw.strip().strip('"')
        key, separator, revision = token.rpartition("@")
        if not separator or key != resource_key:
            raise ValueError(f"resource revision must be formatted as {resource_key}@<revision>")
        try:
            return int(revision)
        except ValueError as exc:
            raise ValueError("resource revision must end with an integer") from exc

    def _command_id(self) -> str | None:
        value = self.headers.get("X-StageForge-Command-Id")
        value = value.strip() if value else ""
        if len(value) > 128:
            raise ValueError("command ID must not exceed 128 characters")
        return value or None

    def _mutation(self, operation, resource_key: str) -> None:
        command_id = self._command_id()
        state, deduplicated = RUNTIME.mutate(command_id, operation)
        self._json(200, state, self._state_headers(state, deduplicated, resource_key))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._guard_request(path):return
        if path == "/healthz":
            self._json(200, RUNTIME.health())
            return
        if path == "/api/v1/state":
            state = RUNTIME.state.snapshot()
            self._json(200, state, self._state_headers(state))
            return
        if path == "/api/v1/adapters":
            self._json(200, {"adapters": RUNTIME.adapters.snapshot()})
            return
        if path == "/api/v1/native":
            native = RUNTIME.native.status()
            self._json(200 if native.get("available") else 503, native)
            return
        if path == "/api/v1/realtime/audit":
            self._json(200,RUNTIME.realtime_audit_status());return
        if path == "/api/v1/node":
            self._json(200, RUNTIME.node_status())
            return
        if path == "/api/v1/replication/status":
            self._json(200, RUNTIME.replication_status())
            return
        if path == "/api/v1/failover":
            self._json(200, RUNTIME.failover_status())
            return
        if path == "/api/v1/failover/continuity":
            self._json(200, RUNTIME.failover_continuity_status())
            return
        if path == "/api/v1/failover/readiness":
            self._json(200, RUNTIME.handoff_readiness_status())
            return
        if path == "/api/v1/handoff/decision":
            self._json(200, RUNTIME.handoff_decision_status())
            return
        if path == "/api/v1/handoff/execution":
            self._json(200, RUNTIME.handoff_execution_status())
            return
        if path == "/api/v1/handoff/planned":
            self._json(200, RUNTIME.planned_handoff_status())
            return
        if path == "/api/v1/compatibility":
            self._json(200, RUNTIME.compatibility_local_profile())
            return
        if path == "/api/v1/compatibility/show-state":
            self._json(200, RUNTIME.state.compatibility_status())
            return
        if path == "/api/v1/profile":
            self._json(200, RUNTIME.user_profile())
            return
        if path == "/api/v1/profile/resolved":
            self._json(200, RUNTIME.user_profile_resolved())
            return
        if path == "/api/v1/profile/projection":
            self._json(200, RUNTIME.user_profile_projection())
            return
        if path == "/api/v1/interoperability/registry":
            self._json(200, RUNTIME.interoperability_registry())
            return
        if path == "/api/v1/security/status":
            self._json(200, RUNTIME.security_status())
            return
        if path == "/api/v1/security/authorization-audit":
            try:
                self._require_admin_auth()
                result = RUNTIME.repository.verify_authorization_audit()
                self._json(200 if result.get("ok") else 503, result)
            except PermissionError as exc:
                self._json(403, {"error": str(exc)})
            return
        if path == "/api/v1/daw/session":
            self._json(200, RUNTIME.daw_session())
            return
        if path == "/api/v1/daw/tempo":
            self._json(200, RUNTIME.daw_tempo_status())
            return
        if path == "/api/v1/daw/plugins":
            self._json(200, RUNTIME.daw_plugin_catalog())
            return
        if path == "/api/v1/daw/plugin-hosts/lifecycle":
            self._json(200, RUNTIME.plugin_host_lifecycle_status())
            return
        if path == "/api/v1/daw/playback":
            self._json(200, RUNTIME.daw_playback_status())
            return
        if path == "/api/v1/daw/production":
            self._json(200, RUNTIME.daw_production_status())
            return
        if path == "/api/v1/daw/temp-resources":
            self._json(200, RUNTIME.daw_temporary_resource_status())
            return
        if path == "/api/v1/daw/sampler":
            self._json(200, RUNTIME.daw_sampler_status())
            return
        if path == "/api/v1/daw/streaming-banks":
            self._json(200, RUNTIME.streaming_bank_status())
            return
        if path == "/api/v1/daw/capture":
            self._json(200, RUNTIME.daw_capture_status())
            return
        if path == "/api/v1/daw/capture/recovery":
            self._json(200, RUNTIME.daw_recovery_status())
            return
        if path == "/api/v1/daw/plugin-delay-graph":
            self._json(200,RUNTIME.plugin_delay_graph_status());return
        if path == "/api/v1/stage/launcher":
            self._json(200, RUNTIME.stage_launcher_status())
            return
        if path == "/api/v1/templates":
            self._json(200, RUNTIME.stage_template_list())
            return
        template_prefix = "/api/v1/templates/"
        if path.startswith(template_prefix) and path.count("/") == 4:
            try: self._json(200, RUNTIME.stage_template_get(path[len(template_prefix):]))
            except KeyError: self._json(404, {"error": "template not found"})
            return
        if path == "/api/v1/hardware/qualification":
            self._json(200, RUNTIME.hardware_qualification())
            return
        if path == "/api/v1/hardware/diagnostics":
            self._json(200, RUNTIME.hardware_diagnostics())
            return
        if path == "/api/v1/interoperability/session":
            session_id = (parse_qs(parsed.query).get("sessionId") or [""])[0]
            self._json(200, RUNTIME.interoperability_session_status(session_id))
            return
        if path == "/api/v1/venue/profile":
            self._json(200, RUNTIME.venue_profile())
            return
        if path == "/api/v1/venue/adaptations":
            self._json(200, RUNTIME.venue_adaptation_status())
            return
        if path == "/api/v1/venue/reconciliation":
            query = parse_qs(parsed.query)
            use_local = (query.get("useLocalDiscovery") or [None])[0]
            data = {} if use_local is None else {"useLocalDiscovery": str(use_local).lower() in {"1", "true", "yes", "on"}}
            self._json(200, RUNTIME.venue_reconciliation_report(data))
            return
        if path == "/api/v1/venue/reconciliation/evidence":
            self._json(200, RUNTIME.venue_reconciliation_evidence())
            return
        if path == "/api/v1/venue/authority":
            self._json(200, RUNTIME.venue_authority_status())
            return
        if path == "/api/v1/public-record":
            self._json(200, RUNTIME.public_record_status())
            return
        if path == "/api/v1/venue/adaptations/active":
            self._json(200, {"active": RUNTIME.venue_adaptation_status().get("active")})
            return
        adaptation_prefix = "/api/v1/venue/adaptations/"
        if path.startswith(adaptation_prefix) and path.count("/") == 5:
            transaction_id = path[len(adaptation_prefix):].strip("/")
            try:
                self._json(200, RUNTIME.venue_adaptation_get(transaction_id))
            except KeyError:
                self._json(404, {"error": "venue adaptation transaction not found"})
            return
        if path == "/api/v1/technology":
            self._json(200, RUNTIME.state.technology_snapshot())
            return
        if path == "/api/v1/technology/assessment":
            self._json(200, RUNTIME.technology_assessment())
            return
        if path == "/api/v1/community":
            self._json(200, RUNTIME.community_status())
            return
        if path == "/api/v1/community/monitor":
            at = (parse_qs(parsed.query).get("at") or [None])[0]
            self._json(200, RUNTIME.community_monitor(at))
            return
        if path == "/api/v1/community/admin":
            try:
                self._require_admin_auth()
                self._json(200, RUNTIME.community_detail())
            except PermissionError as exc:
                self._json(403, {"error": str(exc)})
            return
        if path == "/api/v1/community/vote/context":
            token = (parse_qs(parsed.query).get("token") or [""])[0]
            try:
                self._json(200, RUNTIME.community_vote_context(token))
            except PermissionError as exc:
                self._json(403, {"error": str(exc)})
            return
        community_prefix = "/api/v1/community/proposals/"
        if path.startswith(community_prefix) and path.endswith("/tally"):
            proposal_id = path[len(community_prefix):-len("/tally")].strip("/")
            at = (parse_qs(parsed.query).get("at") or [None])[0]
            try:
                self._json(200, RUNTIME.community_tally(proposal_id, at))
            except KeyError:
                self._json(404, {"error": "proposal not found"})
            return
        if path == "/api/v1/witness":
            self._json(200, RUNTIME.witness_status())
            return
        if path == "/api/v1/replication/export":
            try:
                self._json(200, RUNTIME.export_replica())
            except RuntimeError as exc:
                self._json(409, {"error": str(exc)})
            return
        if path == "/api/v1/audio/devices":
            self._json(200, RUNTIME.audio_devices())
            return
        if path == "/api/v1/audio/hotplug":
            raw_after=(parse_qs(parsed.query).get("after") or ["0"])[0]
            try:self._json(200,RUNTIME.audio_hotplug_status(max(0,int(raw_after))))
            except ValueError:self._json(400,{"error":"after must be an integer generation"})
            return
        if path == "/api/v1/audio/stream":
            self._json(200, RUNTIME.audio_stream_status())
            return
        if path == "/api/v1/audio/outputs":
            self._json(200, RUNTIME.audio_outputs_status())
            return
        audio_output_prefix = "/api/v1/audio/outputs/"
        if path.startswith(audio_output_prefix):
            try:
                slot = int(path[len(audio_output_prefix):].strip("/"))
                self._json(200, RUNTIME.audio_stream_status(slot))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            return
        if path == "/api/v1/audio/input":
            self._json(200, RUNTIME.audio_input_status())
            return
        if path == "/api/v1/audio/inputs":
            self._json(200, RUNTIME.audio_inputs_status())
            return
        le_uwb_node_prefix = "/api/v1/le-uwb/nodes/"
        if path.startswith(le_uwb_node_prefix):
            try:
                node_id = int(path[len(le_uwb_node_prefix):].strip("/"))
                self._json(200, RUNTIME.le_uwb_node_status(node_id))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except RuntimeError as exc:
                self._json(503, {"error": str(exc)})
            return
        audio_input_prefix = "/api/v1/audio/inputs/"
        if path.startswith(audio_input_prefix):
            try:
                slot = int(path[len(audio_input_prefix):].strip("/"))
                self._json(200, RUNTIME.audio_input_status(slot))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            return
        if path == "/api/v1/midi/devices":
            self._json(200, RUNTIME.midi_devices())
            return
        if path == "/api/v1/midi/mappings":
            self._json(200, RUNTIME.midi_mapping_status())
            return
        if path == "/api/v1/midi/mapping-targets":
            self._json(200, RUNTIME.midi_mapping_targets())
            return
        if path == "/api/v1/clock":
            self._json(200, RUNTIME.clock_status())
            return
        if path == "/api/v1/clock/transport-discipline":
            self._json(200,RUNTIME.transport_discipline_status())
            return
        if path == "/api/v1/midi/clock":
            self._json(200,RUNTIME.midi_clock_status())
            return
        if path == "/api/v1/lighting/network":
            self._json(200, RUNTIME.lighting_network_status())
            return
        lighting_prefix = "/api/v1/lighting/universe/"
        if path.startswith(lighting_prefix):
            try:
                universe = int(path[len(lighting_prefix):].strip("/"))
                self._json(200, RUNTIME.lighting_universe_info(universe))
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
            except RuntimeError as exc:
                self._json(503, {"error": str(exc)})
            return
        if path == "/api/v1/system/plan":
            state = RUNTIME.state.snapshot()
            self._json(200, RUNTIME.adapters.plan(state["system"]["capacity"], state["system"]["mode"]))
            return
        if path == "/api/v1/public-record/verify":
            result = RUNTIME.repository.verify_ledger()
            self._json(200 if result.get("ok") else 503, result)
            return
        prefix = "/api/v1/players/"
        if path.startswith(prefix) and path.endswith("/notation.musicxml"):
            player_id = path[len(prefix):-len("/notation.musicxml")].strip("/")
            try:
                xml = RUNTIME.state.notation_musicxml(player_id).encode("utf-8")
            except KeyError:
                self._json(404, {"error": f"unknown player: {player_id}"})
                return
            self._raw(200, xml, "application/vnd.recordare.musicxml+xml; charset=utf-8", {"Content-Disposition": f'attachment; filename="{player_id}.musicxml"'})
            return
        if path.startswith(prefix) and path.endswith("/notation"):
            player_id = path[len(prefix):-len("/notation")].strip("/")
            try:
                part = RUNTIME.state.notation_snapshot(player_id)
            except KeyError:
                self._json(404, {"error": f"unknown player: {player_id}"})
                return
            state = RUNTIME.state.snapshot()
            self._json(200, part, self._state_headers(state, resource_key=f"notation:{player_id}"))
            return
        if path == "/api/v1/events":
            query = parse_qs(parsed.query)
            raw_after = query.get("after", [self.headers.get("Last-Event-ID", "0")])[0]
            try:
                after = max(0, int(raw_after or 0))
            except ValueError:
                self._json(400, {"error": "after must be an integer event id"})
                return
            self._serve_events(after)
            return
        self._serve_frontend(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/desktop/session":
            self._desktop_session()
            return
        if not self._guard_request(path):return
        try:
            body = self._read_json(4 * 1024 * 1024 if path == "/api/v1/replication/apply" else 64 * 1024)
            expected = self._expected_revision()
            if path == "/api/v1/hardware/audio-preflight":
                self._json(200, RUNTIME.audio_hardware_preflight(body))
                return
            if path == "/api/v1/templates":
                self._json(201, RUNTIME.stage_template_create(body)); return
            template_prefix = "/api/v1/templates/"
            if path.startswith(template_prefix) and path.endswith("/validate"):
                self._json(200, RUNTIME.stage_template_validate(path[len(template_prefix):-len("/validate")].strip("/"))); return
            if path.startswith(template_prefix) and path.endswith("/publish"):
                self._json(200, RUNTIME.stage_template_publish(path[len(template_prefix):-len("/publish")].strip("/"))); return
            if path == "/api/v1/hardware/audio-conversion-plan":
                self._json(200, RUNTIME.audio_conversion_plan(body))
                return
            if path == "/api/v1/audio/overload/plan":
                self._json(200, RUNTIME.overload_shedding_plan(body))
                return
            if path == "/api/v1/audio/overload/prepare":
                self._json(200, RUNTIME.overload_transaction_prepare(body))
                return
            if path == "/api/v1/audio/identity/rebind":
                self._json(200, RUNTIME.replace_audio_identity(body))
                return
            if path == "/api/v1/witness/recover":
                self._json(200,RUNTIME.recover_fenced_node(body));return
            if path == "/api/v1/node/role":
                self._json(200, RUNTIME.set_node_role(body))
                return
            if path == "/api/v1/replication/apply":
                self._json(200, RUNTIME.apply_replica(
                    body, authorization_hook=self._machine_authorization_hook("machine.replication.apply")
                ))
                return
            if path == "/api/v1/failover/promote":
                self._json(200, RUNTIME.promote_after_failure(body))
                return
            if path == "/api/v1/handoff/execution/shadow":
                self._require_adapter_report_auth()
                self._json(200, RUNTIME.report_shadow_prebuffer(body))
                return
            if path == "/api/v1/handoff/execution/live":
                self._require_adapter_report_auth()
                self._json(200, RUNTIME.report_live_feed_ready(body))
                return
            if path == "/api/v1/handoff/planned/offer":
                self._json(201, RUNTIME.planned_handoff_offer(body)); return
            if path == "/api/v1/handoff/planned/accept":
                self._json(200, RUNTIME.planned_handoff_accept(body)); return
            if path == "/api/v1/handoff/planned/acknowledge":
                self._json(200, RUNTIME.planned_handoff_acknowledge(body)); return
            if path == "/api/v1/handoff/planned/peer-ready":
                self._json(200,RUNTIME.planned_handoff_peer_ready(
                    body, authorization_hook=self._machine_authorization_hook("machine.handoff.peer-ready")
                ));return
            if path == "/api/v1/handoff/planned/release-authority":
                self._json(200, RUNTIME.planned_handoff_release_authority(body)); return
            if path == "/api/v1/handoff/planned/commit":
                self._json(200, RUNTIME.planned_handoff_commit(body)); return
            if path == "/api/v1/handoff/planned/abort":
                self._json(200, RUNTIME.planned_handoff_abort(body)); return
            if path == "/api/v1/compatibility/negotiate":
                self._json(200, RUNTIME.compatibility_with(body))
                return
            if path == "/api/v1/compatibility/show-plan":
                self._json(200, RUNTIME.show_compatibility(body))
                return
            if path == "/api/v1/compatibility/inspect-show-state":
                result = RUNTIME.compatibility_inspect_show_state(body)
                self._json(200 if result.get("readable") else 409, result)
                return
            if path == "/api/v1/compatibility/migrate-show-state":
                self._json(200, RUNTIME.compatibility_migrate_show_state(body))
                return
            if path == "/api/v1/profile/inspect":
                result = RUNTIME.user_profile_inspect(body)
                self._json(200 if result.get("readable") else 409, result)
                return
            if path == "/api/v1/profile":
                self._json(200, RUNTIME.save_user_profile(body))
                return
            if path == "/api/v1/daw/session":
                self._json(200, RUNTIME.save_daw_session(body))
                return
            if path == "/api/v1/daw/temp-resources/cleanup":
                self._json(200, RUNTIME.daw_temporary_resource_cleanup(body))
                return
            if path == "/api/v1/daw/render-plan":
                self._json(200, RUNTIME.daw_render_plan(body))
                return
            if path == "/api/v1/daw/media/inspect":
                self._json(200, RUNTIME.daw_inspect_media(body))
                return
            if path == "/api/v1/daw/edit":
                self._json(200, RUNTIME.daw_edit(body))
                return
            if path == "/api/v1/daw/markers":
                self._json(200, RUNTIME.daw_marker_edit(body))
                return
            if path == "/api/v1/daw/automation":
                self._json(200, RUNTIME.daw_automation_edit(body))
                return
            if path == "/api/v1/daw/undo":
                self._json(200, RUNTIME.daw_undo())
                return
            if path == "/api/v1/daw/redo":
                self._json(200, RUNTIME.daw_redo())
                return
            if path == "/api/v1/daw/media/ingest":
                self._json(201, RUNTIME.daw_ingest_media(body))
                return
            if path == "/api/v1/daw/media/verify":
                self._json(200, RUNTIME.daw_verify_media(body))
                return
            if path == "/api/v1/daw/beat-frame":
                self._json(200, RUNTIME.daw_beat_frame(body))
                return
            if path == "/api/v1/daw/takes/prepare":
                self._json(201, RUNTIME.daw_prepare_take(body))
                return
            if path == "/api/v1/daw/takes/finalize":
                self._json(200, RUNTIME.daw_finalize_take(body))
                return
            if path == "/api/v1/daw/render":
                self._json(201, RUNTIME.daw_render(body))
                return
            if path == "/api/v1/daw/autosave":
                self._json(201, RUNTIME.daw_autosave())
                return
            if path == "/api/v1/daw/playback/prefetch":
                self._json(200, RUNTIME.daw_playback_prefetch(body))
                return
            if path == "/api/v1/daw/sampler/preload":
                self._json(201, RUNTIME.daw_sampler_preload(body))
                return
            if path == "/api/v1/daw/streaming-banks":
                self._json(201, RUNTIME.streaming_bank_replace(body))
                return
            if path == "/api/v1/daw/streaming-banks/trigger":
                self._json(200, RUNTIME.streaming_bank_trigger(body))
                return
            if path == "/api/v1/daw/streaming-banks/stop":
                self._json(200,RUNTIME.streaming_voice_stop(body));return
            if path == "/api/v1/daw/playback":
                self._json(200, RUNTIME.daw_playback_control(body))
                return
            if path == "/api/v1/daw/capture":
                self._json(200, RUNTIME.daw_capture_control(body))
                return
            if path == "/api/v1/stage/launcher/action":
                self._json(200, RUNTIME.stage_launcher_action(body))
                return
            if path == "/api/v1/daw/plugin-delay-plan":
                self._json(200, RUNTIME.daw_plugin_delay_plan(body))
                return
            if path == "/api/v1/daw/plugin-delay-graph":
                self._json(200,RUNTIME.plugin_delay_graph_control(body));return
            if path == "/api/v1/interoperability/capabilities":
                self._json(201, RUNTIME.register_interoperability_capability(body))
                return
            if path == "/api/v1/interoperability/adapters":
                self._json(201, RUNTIME.register_interoperability_adapter(body))
                return
            if path == "/api/v1/interoperability/offer":
                self._json(201, RUNTIME.interoperability_offer(body))
                return
            if path == "/api/v1/interoperability/accept":
                self._json(200, RUNTIME.interoperability_accept(body))
                return
            if path == "/api/v1/interoperability/consent":
                self._json(200, RUNTIME.interoperability_consent(body))
                return
            if path == "/api/v1/interoperability/activate":
                self._json(200, RUNTIME.interoperability_activate(body))
                return
            if path == "/api/v1/venue/plan":
                self._json(200, RUNTIME.venue_compatibility(body))
                return
            if path == "/api/v1/venue/reconciliation/report":
                self._require_adapter_report_auth()
                self._json(200, RUNTIME.venue_reconciliation_report_execution(body))
                return
            if path == "/api/v1/venue/reconciliation/repair":
                self._json(201, RUNTIME.venue_reconciliation_propose_repair(body))
                return
            if path == "/api/v1/public-record/witness":
                self._json(201, RUNTIME.public_record_attest(body))
                return
            if path == "/api/v1/venue/authority/leases":
                self._json(201, RUNTIME.venue_authority_grant(body))
                return
            authority_prefix = "/api/v1/venue/authority/leases/"
            if path.startswith(authority_prefix) and path.endswith("/revoke"):
                lease_id = path[len(authority_prefix):-len("/revoke")].strip("/")
                self._json(200, RUNTIME.venue_authority_revoke(lease_id, body))
                return
            if path == "/api/v1/venue/adaptations/propose":
                self._json(201, RUNTIME.venue_adaptation_propose(body))
                return
            if path == "/api/v1/venue/adaptations/cue":
                self._json(200, RUNTIME.venue_adaptation_trigger_cue(body))
                return
            adaptation_prefix = "/api/v1/venue/adaptations/"
            if path.startswith(adaptation_prefix):
                tail = path[len(adaptation_prefix):].strip("/").split("/")
                if len(tail) == 2 and tail[1] in {"validate", "commit", "rollback"}:
                    transaction_id, action = tail
                    if action == "validate":
                        self._json(200, RUNTIME.venue_adaptation_validate(transaction_id, body))
                    elif action == "commit":
                        self._json(200, RUNTIME.venue_adaptation_commit(transaction_id, body))
                    else:
                        self._json(200, RUNTIME.venue_adaptation_rollback(transaction_id, body))
                    return
            if path == "/api/v1/venue/profile/inspect":
                result = RUNTIME.venue_profile_inspect(body)
                self._json(200 if result.get("valid") else 409, result)
                return
            if path == "/api/v1/venue/profile":
                self._require_admin_auth()
                self._json(200, RUNTIME.save_venue_profile(body))
                return
            if path == "/api/v1/technology/negotiate":
                self._json(200, RUNTIME.negotiate_technology(body))
                return
            if path == "/api/v1/technology/conformance-receipt":
                self._require_admin_auth()
                self._json(201, RUNTIME.technology_publish_conformance(body))
                return
            if path == "/api/v1/community/accounts":
                self._require_admin_auth()
                self._json(200, RUNTIME.community_upsert_account(body))
                return
            if path == "/api/v1/community/proposals":
                self._require_admin_auth()
                self._json(201, RUNTIME.community_create_proposal(body))
                return
            if path == "/api/v1/community/session":
                self._json(201, RUNTIME.community_issue_session(self._authenticated_user_id()))
                return
            if path == "/api/v1/community/session/revoke":
                self._json(200, RUNTIME.community_revoke_sessions(self._authenticated_user_id()))
                return
            if path == "/api/v1/community/public-record/reconcile":
                self._require_admin_auth()
                proposal_id = str(body.get("proposalId", "")).strip() or None
                self._json(200, RUNTIME.community_public_record_reconcile(proposal_id))
                return
            if path == "/api/v1/community/vote":
                self._json(200, RUNTIME.community_cast_vote(body, self._authenticated_user_id()))
                return
            community_prefix = "/api/v1/community/proposals/"
            if path.startswith(community_prefix) and path.endswith("/email-voters"):
                self._require_admin_auth()
                proposal_id = path[len(community_prefix):-len("/email-voters")].strip("/")
                self._json(200, RUNTIME.community_issue_vote_emails(proposal_id, body))
                return
            if path.startswith(community_prefix) and path.endswith("/apply"):
                self._require_admin_auth()
                proposal_id = path[len(community_prefix):-len("/apply")].strip("/")
                self._json(200, RUNTIME.community_apply_change(proposal_id))
                return
            if path == "/api/v1/transport":
                resource = "transport"
                resource_revision = self._expected_resource_revision(resource)
                self._mutation(lambda: RUNTIME.state.transport(str(body.get("action", "")), expected, resource_revision), resource)
                return
            if path == "/api/v1/checkpoint":
                state = RUNTIME.state.snapshot()
                RUNTIME.repository.save_snapshot(RUNTIME.state.persistence_snapshot())
                self._json(200, {"ok": True, "revision": state["revision"]}, self._state_headers(state))
                return
            if path == "/api/v1/timing/plan":
                self._json(200, RUNTIME.timing_plan(body))
                return
            if path == "/api/v1/lighting/schedule":
                self._json(200, RUNTIME.schedule_lighting(body))
                return
            if path == "/api/v1/lighting/network":
                resource = "lighting-network"
                resource_revision = self._expected_resource_revision(resource)
                state, deduplicated = RUNTIME.patch_lighting_network(body, expected, resource_revision, self._command_id())
                self._json(200, state, self._state_headers(state, deduplicated, resource))
                return
            if path == "/api/v1/lighting/network/arm":
                self._json(200, RUNTIME.arm_lighting_network(body))
                return
            if path == "/api/v1/audio/scan":
                self._json(200, RUNTIME.audio_devices(rescan=True))
                return
            if path == "/api/v1/le-uwb/configure":
                self._json(200, RUNTIME.configure_le_uwb_hub(body))
                return
            if path == "/api/v1/le-uwb/nodes":
                self._json(201, RUNTIME.register_le_uwb_node(body))
                return
            if path == "/api/v1/le-uwb/observations/uwb":
                self._require_adapter_report_auth()
                self._json(200, RUNTIME.report_uwb_observation(body))
                return
            if path == "/api/v1/le-uwb/observations/le":
                self._require_adapter_report_auth()
                self._json(200, RUNTIME.report_le_isochronous_observation(body))
                return
            if path == "/api/v1/le-uwb/plan":
                self._json(200, RUNTIME.plan_le_uwb_sync(body))
                return
            if path == "/api/v1/audio/activate":
                self._json(200, RUNTIME.activate_audio(body))
                return
            if path == "/api/v1/audio/deactivate":
                self._json(200, RUNTIME.deactivate_audio())
                return
            if path == "/api/v1/audio/recover":
                self._json(200, RUNTIME.recover_audio(body))
                return
            audio_output_prefix = "/api/v1/audio/outputs/"
            if path.startswith(audio_output_prefix) and path.endswith("/activate"):
                slot = int(path[len(audio_output_prefix):-len("/activate")].strip("/"))
                self._json(200, RUNTIME.activate_audio(body, slot))
                return
            if path.startswith(audio_output_prefix) and path.endswith("/deactivate"):
                slot = int(path[len(audio_output_prefix):-len("/deactivate")].strip("/"))
                self._json(200, RUNTIME.deactivate_audio(slot))
                return
            if path.startswith(audio_output_prefix) and path.endswith("/recover"):
                slot = int(path[len(audio_output_prefix):-len("/recover")].strip("/"))
                self._json(200, RUNTIME.recover_audio(body, slot))
                return
            if path == "/api/v1/audio/input/activate":
                self._json(200, RUNTIME.activate_audio_input(body))
                return
            if path == "/api/v1/audio/input/deactivate":
                self._json(200, RUNTIME.deactivate_audio_input())
                return
            if path == "/api/v1/audio/input/recover":
                self._json(200, RUNTIME.recover_audio_input(body))
                return
            audio_input_prefix = "/api/v1/audio/inputs/"
            if path.startswith(audio_input_prefix) and path.endswith("/activate"):
                slot = int(path[len(audio_input_prefix):-len("/activate")].strip("/"))
                self._json(200, RUNTIME.activate_audio_input(body, slot))
                return
            if path.startswith(audio_input_prefix) and path.endswith("/deactivate"):
                slot = int(path[len(audio_input_prefix):-len("/deactivate")].strip("/"))
                self._json(200, RUNTIME.deactivate_audio_input(slot))
                return
            if path.startswith(audio_input_prefix) and path.endswith("/recover"):
                slot = int(path[len(audio_input_prefix):-len("/recover")].strip("/"))
                self._json(200, RUNTIME.recover_audio_input(body, slot))
                return
            if path == "/api/v1/audio":
                resource = "audio"
                resource_revision = self._expected_resource_revision(resource)
                state, deduplicated = RUNTIME.patch_audio(body, expected, resource_revision, self._command_id())
                self._json(200, state, self._state_headers(state, deduplicated, resource))
                return
            if path == "/api/v1/midi/scan":
                self._json(200, RUNTIME.midi_devices(rescan=True))
                return
            if path == "/api/v1/midi/learn":
                self._json(200, RUNTIME.midi_mapping_learn(body))
                return
            if path == "/api/v1/midi/learn/cancel":
                self._json(200, RUNTIME.midi_mapping_cancel())
                return
            mapping_prefix = "/api/v1/midi/mappings/"
            if path.startswith(mapping_prefix) and path.endswith("/delete"):
                mapping_id=path[len(mapping_prefix):-len("/delete")].strip("/")
                if not mapping_id:raise ValueError("mapping id required")
                self._json(200, RUNTIME.midi_mapping_delete(mapping_id))
                return
            if path == "/api/v1/clock/source":
                self._json(200, RUNTIME.set_clock_source(str(body.get("source", ""))))
                return
            if path == "/api/v1/clock/observe":
                self._json(200, RUNTIME.observe_clock(body))
                return
            if path == "/api/v1/clock/transport-discipline/configure":
                self._json(200,RUNTIME.configure_transport_discipline(body))
                return
            if path == "/api/v1/clock/transport-discipline/observe":
                self._json(200,RUNTIME.observe_transport_discipline(body))
                return
            if path == "/api/v1/midi/clock":
                self._json(200,RUNTIME.midi_clock_control(body))
                return
            midi_prefix = "/api/v1/midi/devices/"
            if path.startswith(midi_prefix) and path.endswith("/attach"):
                device_id = path[len(midi_prefix):-len("/attach")].strip("/")
                player_id = str(body.get("playerId", "")).strip()
                if not device_id or not player_id:
                    raise ValueError("device id and playerId are required")
                resource = "midi-bindings"
                resource_revision = self._expected_resource_revision(resource)
                state, deduplicated = RUNTIME.bind_midi_device(
                    device_id, player_id, expected, resource_revision, self._command_id()
                )
                self._json(200, state, self._state_headers(state, deduplicated, resource))
                return
            if path.startswith(midi_prefix) and path.endswith("/detach"):
                device_id = path[len(midi_prefix):-len("/detach")].strip("/")
                if not device_id:
                    raise ValueError("device id is required")
                resource = "midi-bindings"
                resource_revision = self._expected_resource_revision(resource)
                state, deduplicated = RUNTIME.unbind_midi_device(
                    device_id, expected, resource_revision, self._command_id()
                )
                self._json(200, state, self._state_headers(state, deduplicated, resource))
                return
            prefix = "/api/v1/players/"
            if path.startswith(prefix) and path.endswith("/midi/input"):
                player_id = path[len(prefix):-len("/midi/input")].strip("/")
                if not player_id:
                    raise ValueError("player id required")
                resource = f"midi:{player_id}"
                resource_revision = self._expected_resource_revision(resource)
                self._mutation(lambda: RUNTIME.ingest_midi(player_id, body, expected, resource_revision), resource)
                return
            if path.startswith(prefix) and path.endswith("/notation/note"):
                player_id = path[len(prefix):-len("/notation/note")].strip("/")
                if not player_id:
                    raise ValueError("player id required")
                resource = f"notation:{player_id}"
                resource_revision = self._expected_resource_revision(resource)
                self._mutation(lambda: RUNTIME.state.notation_note(player_id, body, expected, resource_revision), resource)
                return
            if path.startswith(prefix) and path.endswith("/notation/clear"):
                player_id = path[len(prefix):-len("/notation/clear")].strip("/")
                if not player_id:
                    raise ValueError("player id required")
                resource = f"notation:{player_id}"
                resource_revision = self._expected_resource_revision(resource)
                self._mutation(lambda: RUNTIME.state.clear_notation(player_id, expected, resource_revision), resource)
                return
            self._json(404, {"error": "route not found"})
        except RevisionConflict as exc:
            current = RUNTIME.state.snapshot()
            self._json(409, {"error": str(exc), "current": current}, self._state_headers(current))
        except PermissionError as exc:
            self._json(403, {"error": str(exc)})
        except AdaptationRevisionConflict as exc:
            self._json(409, {"error": str(exc), "expected": exc.expected, "current": exc.actual})
        except OSError as exc:
            self._json(503, {"error": str(exc)})
        except RuntimeError as exc:
            self._json(503, {"error": str(exc)})
        except (ValueError, KeyError) as exc:
            self._json(400, {"error": str(exc)})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if not self._guard_request(path): return
        try:
            body = self._read_json()
            if not isinstance(body, dict):
                raise ValueError("template request must be an object")
            template_prefix = "/api/v1/templates/"
            if not path.startswith(template_prefix) or path.count("/") != 4:
                self._json(404, {"error": "route not found"})
                return
            template_id = path[len(template_prefix):].strip("/")
            expected_revision = body.get("expectedRevision")
            if not template_id:
                raise ValueError("template id is required")
            if type(expected_revision) is not int:
                raise ValueError("expectedRevision must be an integer")
            try:
                self._json(200, RUNTIME.stage_template_delete(template_id, expected_revision))
            except KeyError:
                self._json(404, {"error": "template not found"})
        except StageTemplateConflict as exc:
            self._json(409, {"error": str(exc)})
        except PermissionError as exc:
            self._json(403, {"error": str(exc)})
        except OSError as exc:
            self._json(503, {"error": str(exc)})
        except RuntimeError as exc:
            self._json(503, {"error": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})

    def _desktop_session(self) -> None:
        credentials = self._credentials()
        try:
            validate_http_boundary(
                self.headers, self.client_address[0], "/desktop/session", "POST", credentials
            )
        except PermissionError as exc:
            self._json(403, {"error": str(exc)})
            return
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        try:
            loopback = ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            loopback = False
        configured = credentials.get("STAGEFORGE_DESKTOP_SESSION_TOKEN", "")
        supplied = self.headers.get("X-StageForge-Desktop-Token", "")
        desktop_mode = credentials.get("STAGEFORGE_RUNTIME_MODE", "").strip().lower() == "desktop"
        if not desktop_mode or not loopback or not token_matches(configured, supplied):
            self._json(403, {"error": "desktop session authentication failed"})
            return
        api_token = credentials.get("STAGEFORGE_API_TOKEN", "")
        if not api_token:
            self._json(503, {"error": "desktop API credential is unavailable"})
            return
        self._json(200, {"ready": True}, {
            "Set-Cookie": f"{DESKTOP_SESSION_COOKIE}={api_token}; Path=/; HttpOnly; SameSite=Strict",
        })

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        if not self._guard_request(path):return
        try:
            body = self._read_json()
            expected = self._expected_revision()
            if path == "/api/v1/community/policy":
                self._require_admin_auth()
                self._json(200, RUNTIME.community_patch_policy(body))
                return
            community_prefix = "/api/v1/community/proposals/"
            if path.startswith(community_prefix):
                self._require_admin_auth()
                proposal_id = path[len(community_prefix):].strip("/")
                if proposal_id:
                    self._json(200, RUNTIME.community_update_proposal(proposal_id, body))
                    return
            template_prefix = "/api/v1/templates/"
            if path.startswith(template_prefix) and path.count("/") == 4:
                template_id = path[len(template_prefix):].strip("/")
                if not template_id:
                    raise ValueError("template id is required")
                if not isinstance(body, dict):
                    raise ValueError("template request must be an object")
                expected_template_revision = body.get("expectedRevision")
                if type(expected_template_revision) is not int:
                    raise ValueError("expectedRevision must be an integer")
                document = body.get("document")
                if document is None:
                    document = {key: value for key, value in body.items() if key != "expectedRevision"}
                try:
                    self._json(200, RUNTIME.stage_template_update(template_id, expected_template_revision, document))
                except KeyError:
                    self._json(404, {"error": "template not found"})
                return
            if path == "/api/v1/show":
                resource = "show"
                resource_revision = self._expected_resource_revision(resource)
                self._mutation(lambda: RUNTIME.state.patch_show(body, expected, resource_revision), resource)
                return
            if path == "/api/v1/system":
                resource = "system"
                resource_revision = self._expected_resource_revision(resource)
                self._mutation(lambda: RUNTIME.state.patch_system(body, expected, resource_revision), resource)
                return
            if path == "/api/v1/handoff":
                resource = "handoff"
                resource_revision = self._expected_resource_revision(resource)
                state, deduplicated = RUNTIME.patch_handoff(body, expected, resource_revision, self._command_id())
                self._json(200, state, self._state_headers(state, deduplicated, resource))
                return
            if path == "/api/v1/technology":
                resource = "technology"
                resource_revision = self._expected_resource_revision(resource)
                state, deduplicated = RUNTIME.patch_technology(body, expected, resource_revision, self._command_id())
                self._json(200, state, self._state_headers(state, deduplicated, resource))
                return
            prefix = "/api/v1/players/"
            if path.startswith(prefix) and path.endswith("/notation/settings"):
                player_id = path[len(prefix):-len("/notation/settings")].strip("/")
                if not player_id:
                    raise ValueError("player id required")
                resource = f"notation:{player_id}"
                resource_revision = self._expected_resource_revision(resource)
                self._mutation(lambda: RUNTIME.state.patch_notation_settings(player_id, body, expected, resource_revision), resource)
                return
            suffix = "/monitor"
            if path.startswith(prefix) and path.endswith(suffix):
                player_id = path[len(prefix):-len(suffix)].strip("/")
                if not player_id:
                    raise ValueError("player id required")
                resource = f"monitor:{player_id}"
                resource_revision = self._expected_resource_revision(resource)
                self._mutation(lambda: RUNTIME.state.patch_monitor(player_id, body, expected, resource_revision), resource)
                return
            self._json(404, {"error": "route not found"})
        except KeyError as exc:
            self._json(404, {"error": f"unknown player: {exc.args[0]}"})
        except StageTemplateConflict as exc:
            self._json(409, {"error": str(exc)})
        except RevisionConflict as exc:
            current = RUNTIME.state.snapshot()
            self._json(409, {"error": str(exc), "current": current}, self._state_headers(current))
        except PermissionError as exc:
            self._json(403, {"error": str(exc)})
        except AdaptationRevisionConflict as exc:
            self._json(409, {"error": str(exc), "expected": exc.expected, "current": exc.actual})
        except OSError as exc:
            self._json(503, {"error": str(exc)})
        except RuntimeError as exc:
            self._json(503, {"error": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})

    def _serve_events(self, after: int) -> None:
        slots = getattr(self.server, "_event_slots", None)
        if slots is not None and not slots.acquire(blocking=False):
            self._json(503, {"error": "event stream capacity exhausted"}, {"Retry-After": "5"})
            return
        try:
            self._stream_events(after)
        finally:
            # An unframed SSE response cannot resume HTTP request parsing.
            self.close_connection = True
            if slots is not None:
                slots.release()

    def _stream_events(self, after: int) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._security_headers()
        self.end_headers()
        current = after
        try:
            while True:
                self._revalidate_event_authority()
                events = RUNTIME.state.wait_for_events(current, timeout=1.0)
                self._revalidate_event_authority()
                if not events:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                for event in events:
                    self._revalidate_event_authority()
                    current = max(current, int(event["eventId"]))
                    payload = json.dumps({"revision": event["revision"], "event": event}, separators=(",", ":"))
                    message = f"id: {event['eventId']}\nevent: stageforge\ndata: {payload}\n\n".encode("utf-8")
                    self.wfile.write(message)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, PermissionError, ValueError):
            return

    def _revalidate_event_authority(self):
        # Re-read the configured credential source without altering this request's
        # pinned snapshot. Revoked streams close; never send a second HTTP response.
        fresh = credential_environment(self._credentials())
        validate_http_boundary(self.headers, self.client_address[0], urlparse(self.path).path, 'GET', fresh)

    def _serve_frontend(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        candidate = (FRONTEND / relative).resolve()
        try:
            candidate.relative_to(FRONTEND.resolve())
        except ValueError:
            self._json(403, {"error": "forbidden"})
            return
        if not candidate.is_file():
            self._json(404, {"error": "not found"})
            return
        data = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or content_type == "application/javascript" else ""))
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="StageForge development UI/API bridge")
    parser.add_argument("--host", default=os.environ.get("STAGEFORGE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("STAGEFORGE_PORT", "8787")))
    args = parser.parse_args()
    try:loopback_bind=args.host.lower()=="localhost" or ipaddress.ip_address(args.host).is_loopback
    except ValueError:loopback_bind=False
    try:
        startup_credentials = credential_environment()
        deployment = validate_proxy_https_profile(args.host, startup_credentials)
    except (PermissionError, ValueError) as exc:
        parser.error(str(exc))
    if not loopback_bind and (not startup_credentials.get("STAGEFORGE_ALLOWED_HOSTS","").strip() or not startup_credentials.get("STAGEFORGE_API_TOKEN","")):
        parser.error("non-loopback binding requires STAGEFORGE_ALLOWED_HOSTS and STAGEFORGE_API_TOKEN")
    server = StageForgeHTTPServer((args.host, args.port), StageForgeHandler)
    print(f"StageForge dev bridge: http://{args.host}:{args.port}")
    print(f"State directory: {DATA_DIR}")
    if deployment.get("active"):
        print("HTTP deployment profile: proxy-https (TLS terminates at reviewed loopback proxy)")
    print("Local development bridge only; native real-time engine remains a separate process/library target.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        RUNTIME.close()


if __name__ == "__main__":
    main()
