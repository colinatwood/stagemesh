from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, RLock
from time import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cluster_secrets import HmacKeySnapshot, RotatingHmacKeyring


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_request(payload: dict[str, Any], secret: bytes) -> str:
    return hmac.new(secret, _canonical(payload), hashlib.sha256).hexdigest()


def sign_response(result: dict[str, Any], request: dict[str, Any], operation: str, secret: bytes, key_id: str | None = None) -> dict[str, Any]:
    if not secret or operation not in ("acquire", "transfer", "recover"):
        raise ValueError("response signing requires a secret and valid operation")
    request = {key: value for key, value in request.items() if key != "hmacSha256"}
    payload = {**result, "responseVersion": 1, "operation": operation,
               "requestDigest": hashlib.sha256(_canonical(request)).hexdigest()}
    if key_id is not None:
        payload["keyId"] = str(key_id)
    signature = sign_request({"purpose": "org.upp.witness-response/1", "payload": payload}, secret)
    return {**payload, "responseHmacSha256": signature}


def verify_response(raw: Any, request: dict[str, Any], operation: str, secret: bytes, expected_key_id: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict) or not secret:
        raise ValueError("witness response authentication required")
    signature = raw.get("responseHmacSha256")
    payload = {key: value for key, value in raw.items() if key != "responseHmacSha256"}
    expected = sign_request({"purpose": "org.upp.witness-response/1", "payload": payload}, secret)
    if not isinstance(signature, str) or not hmac.compare_digest(expected, signature):
        raise ValueError("witness response authentication failed")
    request = {key: value for key, value in request.items() if key != "hmacSha256"}
    digest = hashlib.sha256(_canonical(request)).hexdigest()
    if (type(raw.get("responseVersion")) is not int or raw["responseVersion"] != 1 or
            raw.get("operation") != operation or raw.get("requestDigest") != digest or
            raw.get("keyId") != expected_key_id):
        raise ValueError("witness response request binding mismatch")
    return raw


def verify_request(request: dict[str, Any], secret: bytes) -> tuple[bool, str, dict[str, Any]]:
    try:
        payload = {
            "protocolVersion": int(request["protocolVersion"]),
            "clusterId": str(request["clusterId"]),
            "nodeId": str(request["nodeId"]),
            "ttlMs": int(request["ttlMs"]),
            "nonce": str(request["nonce"]),
        }
        if "keyId" in request:
            payload["keyId"] = str(request["keyId"])
    except (KeyError, TypeError, ValueError):
        return False, "malformed witness request", {}
    if payload["protocolVersion"] != 1 or not payload["clusterId"] or not payload["nodeId"]:
        return False, "unsupported witness request", payload
    if not 500 <= payload["ttlMs"] <= 60000:
        return False, "witness ttl must be 500..60000 ms", payload
    supplied = str(request.get("hmacSha256", ""))
    expected = sign_request(payload, secret)
    if not supplied or not hmac.compare_digest(expected, supplied):
        return False, "witness authentication failed", payload
    return True, "ok", payload


def verify_transfer_request(request: dict[str, Any], secret: bytes) -> tuple[bool, str, dict[str, Any]]:
    try:
        for key in ("clusterId", "sourceNodeId", "targetNodeId", "nonce"):
            if not isinstance(request[key], str):
                return False, "malformed witness transfer request", {}
        for key in ("protocolVersion", "sourceEpoch", "targetEpoch", "transactionId", "ttlMs"):
            if not isinstance(request[key], int) or isinstance(request[key], bool):
                return False, "malformed witness transfer request", {}
        payload = {
            "protocolVersion": int(request["protocolVersion"]),
            "clusterId": str(request["clusterId"]),
            "sourceNodeId": str(request["sourceNodeId"]),
            "targetNodeId": str(request["targetNodeId"]),
            "sourceEpoch": int(request["sourceEpoch"]),
            "targetEpoch": int(request["targetEpoch"]),
            "transactionId": int(request["transactionId"]),
            "ttlMs": int(request["ttlMs"]),
            "nonce": str(request["nonce"]),
        }
        if "keyId" in request:
            payload["keyId"] = str(request["keyId"])
    except (KeyError, TypeError, ValueError):
        return False, "malformed witness transfer request", {}
    if (payload["protocolVersion"] != 1 or not payload["clusterId"] or
            not payload["sourceNodeId"] or not payload["targetNodeId"] or
            payload["sourceNodeId"] == payload["targetNodeId"]):
        return False, "unsupported witness transfer request", payload
    if (len(payload["clusterId"]) > 64 or len(payload["sourceNodeId"]) > 64 or
            len(payload["targetNodeId"]) > 64 or not 1 <= len(payload["nonce"]) <= 128):
        return False, "witness transfer identity is out of bounds", payload
    if (payload["transactionId"] <= 0 or payload["sourceEpoch"] <= 0 or
            payload["targetEpoch"] != payload["sourceEpoch"] + 1):
        return False, "invalid witness transfer fencing facts", payload
    if not 500 <= payload["ttlMs"] <= 60000:
        return False, "witness ttl must be 500..60000 ms", payload
    supplied = str(request.get("hmacSha256", ""))
    expected = sign_request(payload, secret)
    if not supplied or not hmac.compare_digest(expected, supplied):
        return False, "witness authentication failed", payload
    return True, "ok", payload

def verify_recovery_request(request:dict[str,Any],secret:bytes)->tuple[bool,str,dict[str,Any]]:
    try:
        string_keys=("clusterId","nodeId","sourceNodeId","targetNodeId","recoveryId","fenceDigest","nonce")
        integer_keys=("protocolVersion","sourceEpoch","targetEpoch","transactionId")
        if any(not isinstance(request.get(key),str) for key in string_keys) or any(not isinstance(request.get(key),int) or isinstance(request.get(key),bool) for key in integer_keys):return False,"malformed witness recovery request",{}
        payload={key:request[key] for key in (*integer_keys,*string_keys)}
        if "keyId" in request:payload["keyId"]=str(request["keyId"])
    except (KeyError,TypeError,ValueError):return False,"malformed witness recovery request",{}
    if(payload["protocolVersion"]!=1 or not payload["clusterId"] or payload["nodeId"]!=payload["sourceNodeId"] or payload["sourceNodeId"]==payload["targetNodeId"] or
       payload["sourceEpoch"]<=0 or payload["targetEpoch"]!=payload["sourceEpoch"]+1 or payload["transactionId"]<=0 or not 1<=len(payload["recoveryId"])<=128 or
       len(payload["fenceDigest"])!=64 or any(c not in "0123456789abcdef" for c in payload["fenceDigest"]) or not 1<=len(payload["nonce"])<=128):return False,"invalid witness recovery fencing facts",payload
    supplied=str(request.get("hmacSha256",""));expected=sign_request(payload,secret)
    if not supplied or not hmac.compare_digest(supplied,expected):return False,"witness authentication failed",payload
    return True,"ok",payload


class WitnessLeaseStore:
    """Small persistent single-writer lease authority.

    A quorum is formed by running multiple independent instances. Each witness
    grants at most one node an unexpired lease for a cluster. Wall-clock expiry
    is persisted so a witness restart does not immediately forget an active
    holder and accidentally manufacture two primaries.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = RLock()
        self._leases: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text("utf-8"))
            if isinstance(raw, dict):
                self._leases = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, json.JSONDecodeError):
            self._leases = {}

    def _save(self) -> None:
        if not self._path:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(self._path.suffix + ".tmp")
        temp.write_text(json.dumps(self._leases, sort_keys=True, separators=(",", ":")), "utf-8")
        temp.replace(self._path)

    def acquire(self, cluster_id: str, node_id: str, ttl_ms: int) -> dict[str, Any]:
        now_ms = int(time() * 1000)
        ttl_ms = max(500, min(int(ttl_ms), 60000))
        with self._lock:
            lease = self._leases.get(cluster_id) or {}
            holder = str(lease.get("holderNodeId", ""))
            expires = int(lease.get("expiresAtUnixMs", 0) or 0)
            epoch = max(0, int(lease.get("epoch", 0) or 0))
            if holder and holder != node_id and expires > now_ms:
                return {
                    "granted": False,
                    "clusterId": cluster_id,
                    "holderNodeId": holder,
                    "epoch": epoch,
                    "expiresAtUnixMs": expires,
                    "serverUnixMs": now_ms,
                    "reason": "lease-held-by-other-node",
                }
            if holder != node_id:
                epoch += 1
            expires = now_ms + ttl_ms
            self._leases[cluster_id] = {
                "holderNodeId": node_id,
                "epoch": max(1, epoch),
                "expiresAtUnixMs": expires,
            }
            self._save()
            return {
                "granted": True,
                "clusterId": cluster_id,
                "holderNodeId": node_id,
                "epoch": max(1, epoch),
                "expiresAtUnixMs": expires,
                "serverUnixMs": now_ms,
                "reason": "granted",
            }

    def transfer(self, cluster_id: str, source_node_id: str, target_node_id: str,
                 source_epoch: int, target_epoch: int, transaction_id: int,
                 ttl_ms: int) -> dict[str, Any]:
        """Atomically move a live lease to one named successor.

        The transaction facts make exact retries idempotent. There is no
        generic release operation because an unowned interval would permit an
        unrelated node to race the intended successor.
        """
        now_ms = int(time() * 1000)
        ttl_ms = max(500, min(int(ttl_ms), 60000))
        with self._lock:
            lease = self._leases.get(cluster_id) or {}
            replay = (
                int(lease.get("lastTransferTransactionId", 0) or 0) == transaction_id and
                str(lease.get("lastTransferSourceNodeId", "")) == source_node_id and
                str(lease.get("holderNodeId", "")) == target_node_id and
                int(lease.get("epoch", 0) or 0) == target_epoch
            )
            if replay:
                return {
                    "granted": True,
                    "idempotent": True,
                    "clusterId": cluster_id,
                    "holderNodeId": target_node_id,
                    "epoch": target_epoch,
                    "expiresAtUnixMs": int(lease.get("expiresAtUnixMs", 0) or 0),
                    "serverUnixMs": now_ms,
                    "transactionId": transaction_id,
                    "reason": "already-transferred",
                }
            holder = str(lease.get("holderNodeId", ""))
            epoch = int(lease.get("epoch", 0) or 0)
            expires = int(lease.get("expiresAtUnixMs", 0) or 0)
            if holder != source_node_id or epoch != source_epoch or expires <= now_ms:
                return {
                    "granted": False,
                    "clusterId": cluster_id,
                    "holderNodeId": holder or None,
                    "epoch": epoch,
                    "expiresAtUnixMs": expires or None,
                    "serverUnixMs": now_ms,
                    "transactionId": transaction_id,
                    "reason": "source-lease-fencing-mismatch",
                }
            if target_epoch != source_epoch + 1:
                return {
                    "granted": False,
                    "clusterId": cluster_id,
                    "holderNodeId": holder,
                    "epoch": epoch,
                    "expiresAtUnixMs": expires,
                    "serverUnixMs": now_ms,
                    "transactionId": transaction_id,
                    "reason": "target-epoch-not-next",
                }
            transferred = {
                "holderNodeId": target_node_id,
                "epoch": target_epoch,
                "expiresAtUnixMs": now_ms + ttl_ms,
                "lastTransferTransactionId": transaction_id,
                "lastTransferSourceNodeId": source_node_id,
            }
            self._leases[cluster_id] = transferred
            self._save()
            return {
                "granted": True,
                "idempotent": False,
                "clusterId": cluster_id,
                "holderNodeId": target_node_id,
                "epoch": target_epoch,
                "expiresAtUnixMs": transferred["expiresAtUnixMs"],
                "serverUnixMs": now_ms,
                "transactionId": transaction_id,
                "reason": "transferred",
            }

    def status(self, cluster_id: str) -> dict[str, Any]:
        now_ms = int(time() * 1000)
        with self._lock:
            lease = dict(self._leases.get(cluster_id) or {})
        holder = str(lease.get("holderNodeId", ""))
        expires = int(lease.get("expiresAtUnixMs", 0) or 0)
        return {
            "clusterId": cluster_id,
            "holderNodeId": holder or None,
            "epoch": int(lease.get("epoch", 0) or 0),
            "expiresAtUnixMs": expires or None,
            "expired": not holder or expires <= now_ms,
            "serverUnixMs": now_ms,
        }

    def authorize_recovery(self,cluster_id:str,node_id:str,target_node_id:str,source_epoch:int,target_epoch:int,transaction_id:int,recovery_id:str,fence_digest:str)->dict[str,Any]:
        with self._lock:lease=dict(self._leases.get(cluster_id) or {})
        authorized=(node_id!=target_node_id and str(lease.get("holderNodeId",""))==target_node_id and int(lease.get("epoch",0) or 0)==target_epoch and
                    int(lease.get("lastTransferTransactionId",0) or 0)==transaction_id and str(lease.get("lastTransferSourceNodeId",""))==node_id and target_epoch==source_epoch+1)
        return {"authorized":authorized,"clusterId":cluster_id,"nodeId":node_id,"targetNodeId":target_node_id,"sourceEpoch":source_epoch,"targetEpoch":target_epoch,"transactionId":transaction_id,"recoveryId":recovery_id,"fenceDigest":fence_digest,"serverUnixMs":int(time()*1000),"reason":"authorized-standby-rejoin" if authorized else "recovery-fence-not-current"}


@dataclass(frozen=True)
class WitnessResult:
    url: str
    granted: bool
    epoch: int = 0
    expires_at_unix_ms: int = 0
    holder_node_id: str | None = None
    error: str | None = None
    witness_id: str | None = None
    failure_domain: str | None = None
    server_unix_ms: int = 0
    clock_skew_ms: int | None = None


class WitnessQuorumClient:
    def __init__(self, urls: list[str], cluster_id: str, node_id: str, secret: bytes, *, ttl_ms: int = 3000, timeout_seconds: float = 0.5, fence_path: Path | None = None, keyring: RotatingHmacKeyring | None = None, independent_topology: dict[str, Any] | None = None) -> None:
        self._independent_topology = independent_topology if isinstance(independent_topology, dict) else None
        if self._independent_topology is not None:
            entries = list(self._independent_topology.get("witnesses") or [])
            self._urls = [str(item["url"]).rstrip("/") for item in entries]
            self._configured_quorum = int(self._independent_topology["quorum"])
            self._max_clock_skew_ms = int(self._independent_topology["maxClockSkewMs"])
            self._endpoint_meta = {
                str(item["url"]).rstrip("/"): {
                    "witnessId": str(item["witnessId"]),
                    "failureDomain": str(item["failureDomain"]),
                    "keyring": RotatingHmacKeyring(str(item["keyringFile"])),
                }
                for item in entries
            }
        else:
            self._urls = [url.rstrip("/") for url in urls if url.startswith(("http://", "https://"))]
            self._configured_quorum = 0
            self._max_clock_skew_ms = 0
            self._endpoint_meta = {}
        if len(self._urls) != len(set(self._urls)):
            raise ValueError("duplicate witness URLs cannot count as independent votes")
        self.cluster_id = cluster_id.strip()[:64] or "stagemesh-local"
        self.node_id = node_id.strip()[:64] or "node-local"
        self.secret = secret
        self._keyring = keyring
        self._operation_auth: HmacKeySnapshot | None = None
        self._operation_endpoint_auth: dict[str, HmacKeySnapshot] | None = None
        self.ttl_ms = max(500, min(int(ttl_ms), 60000))
        self.timeout_seconds = max(0.05, min(float(timeout_seconds), 3.0))
        self._lock = RLock()
        self._operation_lock = Lock()
        self._last_results: list[WitnessResult] = []
        self._lease_epoch = 0
        self._lease_expires_at = 0
        self._last_attempt_at = 0
        self._fence_path = fence_path
        self._acquisition_suspended = self._fence_present()

    def _fence_present(self) -> bool:
        if self._fence_path is None:
            return False
        try:
            self._fence_path.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            # Inaccessible evidence must never be interpreted as no fence.
            return True
        return True

    def _persist_transfer_fence(self, payload: dict[str, Any]) -> None:
        if self._fence_path is None:
            return
        # Presence is authoritative: partial writes and malformed contents
        # remain fenced on restart. No recovery path deletes this marker.
        self._fence_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self._fence_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise RuntimeError("persistent handoff fence already exists; recovery required")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"documentType": "org.upp.handoff-acquisition-fence", **payload}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(self._fence_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    @property
    def independent_mode(self) -> bool:
        return self._independent_topology is not None

    @property
    def configured(self) -> bool:
        if not self._urls:
            return False
        if self.independent_mode:
            return len(self._endpoint_meta) == len(self._urls) and all(meta["keyring"].configured for meta in self._endpoint_meta.values())
        return bool(self._keyring.configured if self._keyring is not None else self.secret)

    def _auth_snapshot(self) -> HmacKeySnapshot:
        if self._keyring is not None:
            return self._keyring.snapshot()
        keys = {"legacy": self.secret} if self.secret else {}
        from types import MappingProxyType
        return HmacKeySnapshot(None, MappingProxyType(keys), False)

    def _auth_for_url(self, url: str) -> HmacKeySnapshot:
        if self.independent_mode:
            if self._operation_endpoint_auth is not None:
                return self._operation_endpoint_auth[url]
            return self._endpoint_meta[url]["keyring"].snapshot()
        return self._operation_auth or self._auth_snapshot()

    def _pin_operation_auth(self) -> None:
        if self.independent_mode:
            self._operation_endpoint_auth = {url: self._endpoint_meta[url]["keyring"].snapshot() for url in self._urls}
        else:
            self._operation_auth = self._auth_snapshot()

    def _clear_operation_auth(self) -> None:
        self._operation_auth = None
        self._operation_endpoint_auth = None

    @staticmethod
    def _signed_body(payload: dict[str, Any], auth: HmacKeySnapshot) -> tuple[dict[str, Any], bytes, str | None]:
        if not auth.configured:
            raise PermissionError("witness authentication required")
        key_id = auth.active_key_id if auth.keyring_mode else None
        body = dict(payload)
        if key_id is not None:
            body["keyId"] = key_id
        secret = auth.active_secret
        body["hmacSha256"] = sign_request(body, secret)
        return body, secret, key_id

    @property
    def quorum_size(self) -> int:
        if self.independent_mode:
            return self._configured_quorum
        return len(self._urls) // 2 + 1 if self._urls else 0

    def _one(self, url: str) -> WitnessResult:
        auth = self._auth_for_url(url)
        payload = {
            "protocolVersion": 1,
            "clusterId": self.cluster_id,
            "nodeId": self.node_id,
            "ttlMs": self.ttl_ms,
            "nonce": secrets.token_hex(12),
        }
        body, secret, key_id = self._signed_body(payload, auth)
        request = Request(
            url + "/api/v1/lease/acquire",
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "StageMesh-Witness/1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read(16384).decode("utf-8"))
            raw = verify_response(raw, body, "acquire", secret, expected_key_id=key_id)
            return self._parse_result(url, raw, self.node_id)
        except HTTPError as exc:
            return WitnessResult(url, False, error=f"HTTP {exc.code}")
        except (URLError, OSError, TimeoutError, ValueError, TypeError) as exc:
            return WitnessResult(url, False, error=str(getattr(exc, "reason", exc))[:200])

    def _response_identity(self, url: str, raw: dict[str, Any]) -> tuple[str | None, str | None, int, int | None]:
        server_unix_ms = raw.get("serverUnixMs")
        witness_id = raw.get("witnessId")
        failure_domain = raw.get("failureDomain")
        if self.independent_mode:
            if type(server_unix_ms) is not int or server_unix_ms <= 0:
                raise ValueError("witness response missing server clock")
            now_ms = int(time() * 1000)
            skew = abs(server_unix_ms - now_ms)
            expected = self._endpoint_meta[url]
            if witness_id != expected["witnessId"] or failure_domain != expected["failureDomain"]:
                raise ValueError("witness identity/failure-domain mismatch")
            if skew > self._max_clock_skew_ms:
                raise ValueError("witness clock skew exceeds configured bound")
            return str(witness_id), str(failure_domain), server_unix_ms, skew
        witness_id = str(witness_id) if witness_id is not None else None
        failure_domain = str(failure_domain) if failure_domain is not None else None
        if type(server_unix_ms) is int and server_unix_ms > 0:
            return witness_id, failure_domain, server_unix_ms, abs(server_unix_ms - int(time() * 1000))
        return witness_id, failure_domain, 0, None

    def _parse_result(self, url: str, raw: Any, holder: str,
                      transaction_id: int | None = None) -> WitnessResult:
        if not isinstance(raw, dict) or type(raw.get("granted")) is not bool:
            raise ValueError("malformed witness grant")
        if raw.get("clusterId") != self.cluster_id:
            raise ValueError("witness cluster mismatch")
        witness_id, failure_domain, server_unix_ms, skew = self._response_identity(url, raw)
        if not raw["granted"]:
            return WitnessResult(url, False, error=str(raw.get("reason", "denied"))[:200],
                                 witness_id=witness_id, failure_domain=failure_domain,
                                 server_unix_ms=server_unix_ms, clock_skew_ms=skew)
        if raw.get("holderNodeId") != holder:
            raise ValueError("witness holder mismatch")
        for key in ("epoch", "expiresAtUnixMs"):
            if type(raw.get(key)) is not int or raw[key] <= 0:
                raise ValueError("malformed witness fencing value")
        if transaction_id is not None and (type(raw.get("transactionId")) is not int or raw["transactionId"] != transaction_id):
            raise ValueError("witness transaction mismatch")
        return WitnessResult(url, True, raw["epoch"], raw["expiresAtUnixMs"], holder, None,
                             witness_id, failure_domain, server_unix_ms, skew)

    def acquire(self) -> dict[str, Any]:
        with self._operation_lock:
            with self._lock:
                if self._acquisition_suspended:
                    return self.status()
            return self._acquire_locked()

    def _acquire_locked(self) -> dict[str, Any]:
        try:
            self._pin_operation_auth()
            results = [self._one(url) for url in self._urls]
        except PermissionError as exc:
            results = [WitnessResult(url, False, error=str(exc)) for url in self._urls]
        finally:
            self._clear_operation_auth()
        now_ms = int(time() * 1000)
        grants = [r for r in results if r.granted and r.holder_node_id == self.node_id and r.expires_at_unix_ms > now_ms]
        quorum = self.quorum_size
        granted = len(grants) >= quorum > 0
        # A safe lease only lasts until the earliest expiry among the quorum
        # grants we rely on. Sort longest first, then take the shortest of the
        # selected quorum set.
        lease_expires = 0
        epoch = 0
        if granted:
            selected = sorted(grants, key=lambda r: r.expires_at_unix_ms, reverse=True)[:quorum]
            lease_expires = min(r.expires_at_unix_ms for r in selected)
            epoch = max(r.epoch for r in selected)
        with self._lock:
            self._last_results = results
            self._last_attempt_at = now_ms
            if granted:
                self._lease_expires_at = lease_expires
                self._lease_epoch = max(self._lease_epoch, epoch)
        return self.status()

    def _transfer_one(self, url: str, payload: dict[str, Any]) -> WitnessResult:
        auth = self._auth_for_url(url)
        unsigned = {**payload, "nonce": secrets.token_hex(12)}
        body, secret, key_id = self._signed_body(unsigned, auth)
        request = Request(
            url + "/api/v1/lease/transfer",
            data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "StageMesh-Witness/1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read(16384).decode("utf-8"))
            raw = verify_response(raw, body, "transfer", secret, expected_key_id=key_id)
            return self._parse_result(url, raw, payload["targetNodeId"], payload["transactionId"])
        except HTTPError as exc:
            return WitnessResult(url, False, error=f"HTTP {exc.code}")
        except (URLError, OSError, TimeoutError, ValueError, TypeError) as exc:
            return WitnessResult(url, False, error=str(getattr(exc, "reason", exc))[:200])

    def transfer(self, *, target_node_id: str, source_epoch: int,
                 target_epoch: int, transaction_id: int) -> dict[str, Any]:
        payload = {
            "protocolVersion": 1,
            "clusterId": self.cluster_id,
            "sourceNodeId": self.node_id,
            "targetNodeId": str(target_node_id),
            "sourceEpoch": int(source_epoch),
            "targetEpoch": int(target_epoch),
            "transactionId": int(transaction_id),
            "ttlMs": self.ttl_ms,
        }
        with self._operation_lock:
            # A transfer attempt is irreversible at any witness that accepts
            # it. The source must therefore stop considering its cached lease
            # valid even if fewer than a quorum respond successfully.
            with self._lock:
                self._acquisition_suspended = True
                self._lease_expires_at = 0
            self._persist_transfer_fence(payload)
            try:
                self._pin_operation_auth()
                results = [self._transfer_one(url, payload) for url in self._urls]
            except PermissionError as exc:
                results = [WitnessResult(url, False, error=str(exc)) for url in self._urls]
            finally:
                self._clear_operation_auth()
            now_ms = int(time() * 1000)
            grants = [result for result in results if (
                result.granted and result.holder_node_id == target_node_id and
                result.epoch == target_epoch and result.expires_at_unix_ms > now_ms
            )]
            with self._lock:
                self._last_results = results
                self._last_attempt_at = int(time() * 1000)
            return {
                "transferred": len(grants) >= self.quorum_size > 0,
                "clusterId": self.cluster_id,
                "sourceNodeId": self.node_id,
                "targetNodeId": target_node_id,
                "sourceEpoch": source_epoch,
                "targetEpoch": target_epoch,
                "transactionId": transaction_id,
                "witnesses": len(self._urls),
                "quorum": self.quorum_size,
                "grants": len(grants),
                "results": [result.__dict__ for result in results],
            }

    def _recovery_facts(self)->tuple[dict[str,Any],str,tuple[int,int]]:
        if self._fence_path is None:raise RuntimeError("persistent recovery requires a configured fence path")
        try:
            fd=os.open(self._fence_path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0));metadata=os.fstat(fd)
            try:raw=os.read(fd,65537)
            finally:os.close(fd)
            if not stat.S_ISREG(metadata.st_mode) or len(raw)>65536:raise RuntimeError("recovery fence must be a bounded regular file")
            marker=json.loads(raw.decode("utf-8"))
        except (OSError,UnicodeDecodeError,json.JSONDecodeError) as exc:raise RuntimeError("recovery fence is unreadable or malformed") from exc
        required=("clusterId","sourceNodeId","targetNodeId","sourceEpoch","targetEpoch","transactionId")
        if marker.get("documentType")!="org.upp.handoff-acquisition-fence" or any(key not in marker for key in required) or marker["clusterId"]!=self.cluster_id or marker["sourceNodeId"]!=self.node_id:raise RuntimeError("recovery fence identity does not match this node")
        return marker,hashlib.sha256(raw).hexdigest(),(metadata.st_dev,metadata.st_ino)

    def _recover_one(self,url:str,payload:dict[str,Any])->WitnessResult:
        auth=self._auth_for_url(url);unsigned={**payload,"nonce":secrets.token_hex(12)};body,secret,key_id=self._signed_body(unsigned,auth)
        request=Request(url+"/api/v1/lease/recover",data=json.dumps(body,separators=(",",":")).encode("utf-8"),method="POST",headers={"Content-Type":"application/json","User-Agent":"StageMesh-Witness/1"})
        try:
            with urlopen(request,timeout=self.timeout_seconds) as response:raw=json.loads(response.read(16384).decode("utf-8"))
            raw=verify_response(raw,body,"recover",secret,expected_key_id=key_id)
            if type(raw.get("authorized")) is not bool or raw.get("clusterId")!=self.cluster_id or raw.get("nodeId")!=self.node_id or raw.get("recoveryId")!=payload["recoveryId"] or raw.get("fenceDigest")!=payload["fenceDigest"]:raise ValueError("malformed witness recovery authorization")
            witness_id,failure_domain,server_unix_ms,skew=self._response_identity(url,raw)
            return WitnessResult(url,bool(raw["authorized"]),int(raw.get("targetEpoch",0) or 0),0,self.node_id,None if raw["authorized"] else str(raw.get("reason","denied"))[:200],witness_id,failure_domain,server_unix_ms,skew)
        except HTTPError as exc:return WitnessResult(url,False,error=f"HTTP {exc.code}")
        except (URLError,OSError,TimeoutError,ValueError,TypeError) as exc:return WitnessResult(url,False,error=str(getattr(exc,"reason",exc))[:200])

    def recover(self,recovery_id:str)->dict[str,Any]:
        recovery_id=str(recovery_id).strip()
        if not recovery_id or len(recovery_id)>128:raise ValueError("recoveryId must contain 1..128 characters")
        with self._operation_lock:
            with self._lock:
                if not self._acquisition_suspended:raise RuntimeError("node has no active acquisition fence")
            if not self.configured:raise RuntimeError("authorized recovery requires configured witness quorum")
            marker,digest,fence_identity=self._recovery_facts();payload={"protocolVersion":1,"clusterId":self.cluster_id,"nodeId":self.node_id,"sourceNodeId":marker["sourceNodeId"],"targetNodeId":marker["targetNodeId"],"sourceEpoch":int(marker["sourceEpoch"]),"targetEpoch":int(marker["targetEpoch"]),"transactionId":int(marker["transactionId"]),"recoveryId":recovery_id,"fenceDigest":digest}
            try:
                self._pin_operation_auth();results=[self._recover_one(url,payload) for url in self._urls]
            except PermissionError as exc:
                results=[WitnessResult(url,False,error=str(exc)) for url in self._urls]
            finally:self._clear_operation_auth()
            grants=[item for item in results if item.granted and item.epoch==payload["targetEpoch"]]
            if len(grants)<self.quorum_size:return {"recovered":False,"recoveryId":recovery_id,"grants":len(grants),"quorum":self.quorum_size,"results":[item.__dict__ for item in results],"acquisitionSuspended":True,"physicalOutputsArmed":False}
            receipt_path=self._fence_path.with_name(self._fence_path.name+".recovery.json");receipt={"documentType":"org.upp.handoff-recovery-receipt","schemaVersion":1,**payload,"grants":len(grants),"quorum":self.quorum_size,"results":[item.__dict__ for item in results]}
            temp=receipt_path.with_suffix(receipt_path.suffix+".tmp")
            with temp.open("x",encoding="utf-8") as handle:json.dump(receipt,handle,sort_keys=True,separators=(",",":"));handle.flush();os.fsync(handle.fileno())
            temp.replace(receipt_path);directory_fd=os.open(receipt_path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
            try:
                os.fsync(directory_fd);current_fd=os.open(self._fence_path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0));current=os.fstat(current_fd)
                try:current_raw=os.read(current_fd,65537)
                finally:os.close(current_fd)
                if (current.st_dev,current.st_ino)!=fence_identity or hashlib.sha256(current_raw).hexdigest()!=digest:raise RuntimeError("recovery fence changed before removal")
                self._fence_path.unlink();os.fsync(directory_fd)
            finally:os.close(directory_fd)
            with self._lock:self._acquisition_suspended=False;self._lease_epoch=0;self._lease_expires_at=0;self._last_results=results;self._last_attempt_at=int(time()*1000)
            return {"recovered":True,"recoveryId":recovery_id,"grants":len(grants),"quorum":self.quorum_size,"receiptPersisted":True,"startsAsStandby":True,"acquisitionSuspended":False,"physicalOutputsArmed":False}

    def valid(self, safety_margin_ms: int = 100) -> bool:
        with self._lock:
            return self.configured and not self._acquisition_suspended and self._lease_expires_at > int(time() * 1000) + max(0, int(safety_margin_ms))

    def status(self) -> dict[str, Any]:
        now_ms = int(time() * 1000)
        with self._lock:
            results = list(self._last_results)
            expiry = self._lease_expires_at
            epoch = self._lease_epoch
            last = self._last_attempt_at
            suspended = self._acquisition_suspended
        return {
            "configured": self.configured,
            "independentMode": self.independent_mode,
            "independentWitnessIds": [self._endpoint_meta[url]["witnessId"] for url in self._urls] if self.independent_mode else [],
            "declaredFailureDomains": [self._endpoint_meta[url]["failureDomain"] for url in self._urls] if self.independent_mode else [],
            "maxClockSkewMs": self._max_clock_skew_ms if self.independent_mode else None,
            "physicalIndependenceQualified": False,
            "clusterId": self.cluster_id,
            "nodeId": self.node_id,
            "witnesses": len(self._urls),
            "quorum": self.quorum_size,
            "leaseValid": bool(not suspended and expiry > now_ms),
            "acquisitionSuspended": suspended,
            "recoveryReceiptPresent":bool(self._fence_path and self._fence_path.with_name(self._fence_path.name+".recovery.json").is_file()),
            "leaseEpoch": epoch,
            "leaseExpiresInMs": max(0, expiry - now_ms) if expiry else None,
            "lastAttemptAgeMs": max(0, now_ms - last) if last else None,
            "results": [r.__dict__ for r in results],
        }
