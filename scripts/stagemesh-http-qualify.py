#!/usr/bin/env python3
"""Qualify the StageMesh proxy-HTTPS deployment contract without exposing secrets."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from http_credentials import credential_environment
from http_deployment import qualify_loopback_backend, qualify_tls_edge, validate_proxy_https_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind-host", default="127.0.0.1",
                        help="StageMesh backend bind host used for static deployment validation")
    parser.add_argument("--backend-url", help="Loopback HTTP backend origin, e.g. http://127.0.0.1:8765")
    parser.add_argument("--edge-url", help="Public/private HTTPS reverse-proxy origin")
    parser.add_argument("--json", action="store_true", help="emit compact JSON")
    args = parser.parse_args()
    report = {"ok": False, "profile": None, "backend": None, "edge": None}
    try:
        effective = credential_environment(os.environ)
        profile = validate_proxy_https_profile(args.bind_host, effective)
        if not profile.get("active"):
            raise RuntimeError("STAGEMESH_DEPLOYMENT_PROFILE=proxy-https is required for qualification")
        report["profile"] = profile
        host = profile["allowedHosts"][0]
        origin = profile["allowedOrigins"][0]
        if args.backend_url:
            report["backend"] = qualify_loopback_backend(
                args.backend_url, host, origin, effective["STAGEMESH_API_TOKEN"])
        if args.edge_url:
            report["edge"] = qualify_tls_edge(args.edge_url)
        if not args.backend_url and not args.edge_url:
            report["configurationOnly"] = True
        report["ok"] = all(section is None or section.get("ok", True)
                           for section in (report["backend"], report["edge"]))
    except (OSError, ValueError, PermissionError, RuntimeError) as exc:
        report["error"] = str(exc)
        report["ok"] = False
    print(json.dumps(report, indent=None if args.json else 2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
