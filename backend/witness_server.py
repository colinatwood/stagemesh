from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from witness import WitnessLeaseStore, verify_request, verify_transfer_request, verify_recovery_request, sign_response
from cluster_secrets import RotatingHmacKeyring

HOST = os.environ.get("STAGEMESH_WITNESS_HOST", "127.0.0.1")
PORT = int(os.environ.get("STAGEMESH_WITNESS_PORT", "8790"))
SECRET = os.environ.get("STAGEMESH_WITNESS_SECRET", os.environ.get("STAGEMESH_REPLICATION_SECRET", "")).encode("utf-8")
EXPLICIT_KEYRING_PATH = os.environ.get("STAGEMESH_WITNESS_KEYRING_FILE", "").strip()
KEYRING_PATH = EXPLICIT_KEYRING_PATH or os.environ.get("STAGEMESH_REPLICATION_KEYRING_FILE", "")
KEYRING = RotatingHmacKeyring(KEYRING_PATH, SECRET)
WITNESS_ID = os.environ.get("STAGEMESH_WITNESS_ID", "").strip()[:64]
FAILURE_DOMAIN = os.environ.get("STAGEMESH_WITNESS_FAILURE_DOMAIN", "").strip()[:64]
INDEPENDENT_MODE = os.environ.get("STAGEMESH_WITNESS_INDEPENDENT", "0").strip().lower() in {"1", "true", "yes", "on"}
DATA = Path(os.environ.get("STAGEMESH_WITNESS_DATA", ".stagemesh-witness/leases.json"))
STORE = WitnessLeaseStore(DATA)

def independent_configuration_error() -> str | None:
    if not INDEPENDENT_MODE:
        return None
    if not WITNESS_ID or not FAILURE_DOMAIN:
        return "independent witness requires STAGEMESH_WITNESS_ID and STAGEMESH_WITNESS_FAILURE_DOMAIN"
    if not EXPLICIT_KEYRING_PATH:
        return "independent witness requires its own STAGEMESH_WITNESS_KEYRING_FILE"
    if SECRET:
        return "independent witness forbids environment/shared-secret fallback"
    return None

class Handler(BaseHTTPRequestHandler):
    server_version = "StageMeshWitness/1"
    def log_message(self, format: str, *args) -> None:
        return
    def _json(self, code: int, value: object) -> None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            error = independent_configuration_error()
            self._json(200 if error is None else 503, {"ok": error is None, "service": "stagemesh-witness", "witnessId": WITNESS_ID or None, "failureDomain": FAILURE_DOMAIN or None, "independentMode": INDEPENDENT_MODE, "error": error})
            return
        if parsed.path == "/api/v1/lease/status":
            cluster = parse_qs(parsed.query).get("clusterId", [""])[0]
            self._json(200, STORE.status(cluster)); return
        self._json(404, {"error": "route not found"})
    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/v1/lease/acquire", "/api/v1/lease/transfer", "/api/v1/lease/recover"}: self._json(404, {"error": "route not found"}); return
        config_error = independent_configuration_error()
        if config_error: self._json(503, {"error": config_error}); return
        if not (KEYRING.keyring_mode or SECRET): self._json(503, {"error": "witness authentication not configured"}); return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 65536)
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError): self._json(400, {"error": "invalid JSON"}); return
        try:
            auth = KEYRING.snapshot() if KEYRING.keyring_mode else RotatingHmacKeyring(None, SECRET).snapshot()
            key_id = body.get("keyId")
            secret = auth.resolve(key_id)
        except PermissionError as exc:
            self._json(403, {"error": str(exc)}); return
        verify = verify_transfer_request if path.endswith("/transfer") else (verify_recovery_request if path.endswith("/recover") else verify_request)
        ok, reason, payload = verify(body, secret)
        if not ok: self._json(403, {"error": reason}); return
        if path.endswith("/transfer"):
            result = STORE.transfer(payload["clusterId"], payload["sourceNodeId"], payload["targetNodeId"],
                                    payload["sourceEpoch"], payload["targetEpoch"], payload["transactionId"], payload["ttlMs"])
            operation="transfer"
        elif path.endswith("/recover"):
            result=STORE.authorize_recovery(payload["clusterId"],payload["nodeId"],payload["targetNodeId"],payload["sourceEpoch"],payload["targetEpoch"],payload["transactionId"],payload["recoveryId"],payload["fenceDigest"]);operation="recover"
        else:
            result = STORE.acquire(payload["clusterId"], payload["nodeId"], payload["ttlMs"]);operation="acquire"
        result = {**result, "witnessId": WITNESS_ID or None, "failureDomain": FAILURE_DOMAIN or None}
        self._json(200, sign_response(result, payload, operation, secret, key_id=key_id if auth.keyring_mode else None))

if __name__ == "__main__":
    error = independent_configuration_error()
    if error:
        raise SystemExit(error)
    print(f"StageMesh witness {WITNESS_ID or 'legacy'} listening on http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
