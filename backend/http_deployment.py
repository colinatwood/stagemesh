"""Deployment-profile validation and non-secret HTTP qualification helpers.

The StageMesh HTTP bridge is intentionally plain HTTP. A deployed browser/API
surface terminates TLS at a reviewed reverse proxy and keeps this process on
loopback. This module makes that contract executable without teaching the bridge
to trust forwarding headers or to terminate TLS itself.
"""
from __future__ import annotations

import http.client
import ipaddress
import os
import ssl
from typing import Any, Mapping
from urllib.parse import urlparse

from http_authorization import authorization_policy


PROXY_HTTPS_PROFILE = "proxy-https"
_REQUIRED_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
    "cache-control": "no-store",
}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _loopback_host(value: str) -> bool:
    if value.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _allowed_hosts(raw: str) -> tuple[str, ...]:
    values = tuple(item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip())
    if not values or len(set(values)) != len(values):
        raise ValueError("proxy-https profile requires unique STAGEMESH_ALLOWED_HOSTS")
    for value in values:
        # STAGEMESH_ALLOWED_HOSTS is intentionally hostname-only. Ports belong in
        # Origin, not in the Host allowlist value.
        parsed = urlparse("//" + value)
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or parsed.path or parsed.query or parsed.fragment
                or parsed.hostname.lower().rstrip(".") != value):
            raise ValueError("proxy-https allowed hosts must be bare hostnames")
        if value in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("proxy-https profile requires a non-loopback public/private hostname")
    return values


def _allowed_origins(raw: str, hosts: tuple[str, ...]) -> tuple[str, ...]:
    values = tuple(item.strip().rstrip("/") for item in raw.split(",") if item.strip())
    if not values or len(set(values)) != len(values):
        raise ValueError("proxy-https profile requires unique STAGEMESH_ALLOWED_ORIGINS")
    host_set = set(hosts)
    for value in values:
        parsed = urlparse(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("proxy-https origins must be exact HTTPS origins without paths")
        if parsed.hostname.lower().rstrip(".") not in host_set:
            raise ValueError("proxy-https origin hostname must be in STAGEMESH_ALLOWED_HOSTS")
    return values


def validate_proxy_https_profile(bind_host: str, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Validate the strict deployed reverse-proxy profile.

    An unset profile preserves the local-development behavior. Selecting
    ``proxy-https`` deliberately raises the bar: the backend must stay on loopback,
    secrets must come from the private credential file, browser origins must be
    HTTPS, and per-user authorization must be configured behind the trusted auth
    proxy credential.
    """
    env = os.environ if environ is None else environ
    profile = str(env.get("STAGEMESH_DEPLOYMENT_PROFILE", "")).strip().lower()
    if not profile:
        return {"active": False, "profile": "development"}
    if profile != PROXY_HTTPS_PROFILE:
        raise ValueError("unsupported STAGEMESH_DEPLOYMENT_PROFILE")
    if not _loopback_host(bind_host):
        raise ValueError("proxy-https backend must bind to loopback")
    if not _truthy(env.get("STAGEMESH_REQUIRE_API_TOKEN")):
        raise ValueError("proxy-https profile requires STAGEMESH_REQUIRE_API_TOKEN=1")
    if not str(env.get("STAGEMESH_HTTP_CREDENTIAL_FILE", "")).strip():
        raise ValueError("proxy-https profile requires STAGEMESH_HTTP_CREDENTIAL_FILE")
    if not str(env.get("STAGEMESH_API_TOKEN", "")):
        raise ValueError("proxy-https profile requires the control credential")
    hosts = _allowed_hosts(str(env.get("STAGEMESH_ALLOWED_HOSTS", "")))
    origins = _allowed_origins(str(env.get("STAGEMESH_ALLOWED_ORIGINS", "")), hosts)
    if not str(env.get("STAGEMESH_HTTP_AUTHORIZATION_FILE", "")).strip():
        raise ValueError("proxy-https profile requires STAGEMESH_HTTP_AUTHORIZATION_FILE")
    if not str(env.get("STAGEMESH_AUTH_PROXY_TOKEN", "")):
        raise ValueError("proxy-https profile requires the trusted auth-proxy credential")
    # Parse the policy now so a deployed service does not start with a malformed or
    # weakly-permissioned role file and discover that fact only on the first mutation.
    policy = authorization_policy(env)
    if policy is None:
        raise ValueError("proxy-https authorization policy is unavailable")
    return {
        "active": True,
        "profile": PROXY_HTTPS_PROFILE,
        "backendLoopback": True,
        "requireApiToken": True,
        "credentialFile": True,
        "authorizationPolicy": True,
        "trustedForwardedPeerHeaders": False,
        "allowedHosts": list(hosts),
        "allowedOrigins": list(origins),
        "authorizationUsers": len(policy["users"]),
    }


def evaluate_security_headers(headers: Mapping[str, str], require_hsts: bool = False) -> list[str]:
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    failures: list[str] = []
    for name, expected in _REQUIRED_SECURITY_HEADERS.items():
        if normalized.get(name, "").lower() != expected.lower():
            failures.append(f"{name} missing or unexpected")
    csp = normalized.get("content-security-policy", "")
    for directive in ("default-src 'self'", "object-src 'none'", "frame-ancestors 'none'"):
        if directive not in csp:
            failures.append(f"content-security-policy missing {directive}")
    if require_hsts:
        hsts = normalized.get("strict-transport-security", "").lower()
        if "max-age=" not in hsts:
            failures.append("strict-transport-security missing max-age")
    return failures


def _request(connection, method: str, path: str, headers: Mapping[str, str]) -> tuple[int, dict[str, str], bytes]:
    connection.request(method, path, headers=dict(headers))
    response = connection.getresponse()
    body = response.read(1_048_577)
    if len(body) > 1_048_576:
        raise RuntimeError("qualification response exceeds 1 MiB")
    return response.status, {key.lower(): value for key, value in response.getheaders()}, body


def qualify_loopback_backend(base_url: str, public_host: str, public_origin: str,
                             api_token: str, timeout: float = 5.0,
                             connection_factory=None) -> dict[str, Any]:
    """Exercise the StageMesh backend boundary from the proxy host.

    This intentionally talks to the loopback HTTP bridge, not the public TLS edge.
    It proves the backend's Host/Origin/token contract while leaving TLS to the edge
    probe below.
    """
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.path not in {"", "/"}:
        raise ValueError("backend URL must be a plain HTTP origin")
    if not parsed.hostname or not _loopback_host(parsed.hostname):
        raise ValueError("backend qualification URL must resolve syntactically to loopback")
    if not api_token:
        raise ValueError("backend qualification requires the control credential")
    factory = connection_factory or http.client.HTTPConnection
    port = parsed.port or 80

    def run(headers):
        connection = factory(parsed.hostname, port, timeout=timeout)
        try:
            return _request(connection, "GET", "/healthz", headers)
        finally:
            connection.close()

    valid_headers = {"Host": public_host, "Origin": public_origin,
                     "X-StageMesh-API-Token": api_token}
    status, headers, _ = run(valid_headers)
    failures = []
    if status != 200:
        failures.append(f"authorized backend health returned {status}")
    failures.extend(evaluate_security_headers(headers, require_hsts=False))

    invalid = dict(valid_headers)
    invalid["X-StageMesh-API-Token"] = "stagemesh-invalid-qualification-token"
    invalid_status, _, _ = run(invalid)
    if invalid_status != 403:
        failures.append(f"invalid backend credential returned {invalid_status}, expected 403")

    hostile_host = dict(valid_headers)
    hostile_host["Host"] = "attacker.invalid"
    hostile_host_status, _, _ = run(hostile_host)
    if hostile_host_status != 403:
        failures.append(f"hostile Host returned {hostile_host_status}, expected 403")

    hostile_origin = dict(valid_headers)
    hostile_origin["Origin"] = "https://attacker.invalid"
    hostile_origin_status, _, _ = run(hostile_origin)
    if hostile_origin_status != 403:
        failures.append(f"hostile Origin returned {hostile_origin_status}, expected 403")

    return {
        "ok": not failures,
        "url": base_url,
        "authorizedStatus": status,
        "invalidCredentialStatus": invalid_status,
        "hostileHostStatus": hostile_host_status,
        "hostileOriginStatus": hostile_origin_status,
        "failures": failures,
    }


def qualify_tls_edge(base_url: str, timeout: float = 5.0, ssl_context=None,
                     connection_factory=None) -> dict[str, Any]:
    """Verify certificate-checked HTTPS and browser security headers at the edge."""
    parsed = urlparse(base_url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("edge URL must be an HTTPS origin")
    context = ssl_context or ssl.create_default_context()
    factory = connection_factory or http.client.HTTPSConnection
    port = parsed.port or 443
    connection = factory(parsed.hostname, port, timeout=timeout, context=context)
    try:
        connection.request("GET", "/", headers={"Host": parsed.netloc})
        # Capture negotiated TLS immediately after request transmission. HTTP/1.0
        # or Connection: close responses may detach the socket during getresponse().
        tls_version = connection.sock.version() if getattr(connection, "sock", None) is not None else None
        response = connection.getresponse()
        body = response.read(1_048_577)
        if len(body) > 1_048_576:
            raise RuntimeError("qualification response exceeds 1 MiB")
        status = response.status
        headers = {key.lower(): value for key, value in response.getheaders()}
    finally:
        connection.close()
    failures = []
    if status != 200:
        failures.append(f"TLS edge root returned {status}")
    failures.extend(evaluate_security_headers(headers, require_hsts=True))
    if tls_version not in {"TLSv1.2", "TLSv1.3"}:
        failures.append(f"unexpected TLS version {tls_version or 'unknown'}")
    return {
        "ok": not failures,
        "url": base_url,
        "status": status,
        "tlsVersion": tls_version,
        "certificateVerified": True,
        "failures": failures,
    }
