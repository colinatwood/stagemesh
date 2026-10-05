#!/usr/bin/env python3
"""Report StageMesh desktop signing input readiness without exposing secrets."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Mapping


WINDOWS_PFX = (
    "WINDOWS_CERTIFICATE",
    "WINDOWS_CERTIFICATE_PASSWORD",
    "STAGEMESH_WINDOWS_CERTIFICATE_THUMBPRINT",
    "STAGEMESH_WINDOWS_TIMESTAMP_URL",
)
WINDOWS_AZURE = (
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_TENANT_ID",
    "STAGEMESH_WINDOWS_SIGNING_ENDPOINT",
    "STAGEMESH_WINDOWS_SIGNING_ACCOUNT",
    "STAGEMESH_WINDOWS_SIGNING_PROFILE",
)
MACOS_CERTIFICATE = (
    "APPLE_CERTIFICATE",
    "APPLE_CERTIFICATE_PASSWORD",
    "KEYCHAIN_PASSWORD",
)
MACOS_APPLE_ID = ("APPLE_ID", "APPLE_PASSWORD", "APPLE_TEAM_ID")
MACOS_API_KEY = ("APPLE_API_KEY", "APPLE_API_ISSUER")


def _presence(environment: Mapping[str, str], names: tuple[str, ...]) -> tuple[list[str], list[str]]:
    present = [name for name in names if str(environment.get(name, "")).strip()]
    missing = [name for name in names if name not in present]
    return present, missing


def evaluate(platform: str, environment: Mapping[str, str]) -> dict[str, object]:
    normalized = platform.strip().lower()
    if normalized in {"windows", "win32"}:
        mode = str(environment.get("STAGEMESH_WINDOWS_SIGNING_MODE", "")).strip().lower()
        required = WINDOWS_PFX if mode == "pfx" else WINDOWS_AZURE if mode == "azure-artifact-signing" else ()
        present, missing = _presence(environment, required)
        blockers = [] if required else ["select STAGEMESH_WINDOWS_SIGNING_MODE=pfx or azure-artifact-signing"]
        if missing:
            blockers.append("missing Windows signing inputs: " + ", ".join(missing))
        ready = bool(required) and not missing
        return {
            "schemaVersion": 1,
            "platform": "windows",
            "mode": mode or None,
            "readyForPlatformSigning": ready,
            "presentInputs": present,
            "missingInputs": missing,
            "blockers": blockers,
            "secretValuesIncluded": False,
        }

    if normalized in {"macos", "darwin"}:
        certificate_present, certificate_missing = _presence(environment, MACOS_CERTIFICATE)
        apple_present, apple_missing = _presence(environment, MACOS_APPLE_ID)
        api_present, api_missing = _presence(environment, MACOS_API_KEY)
        key_location = bool(
            str(environment.get("APPLE_API_KEY_PATH", "")).strip()
            or str(environment.get("API_PRIVATE_KEYS_DIR", "")).strip()
        )
        api_location_name = "APPLE_API_KEY_PATH or API_PRIVATE_KEYS_DIR"
        api_complete = not api_missing and key_location
        apple_complete = not apple_missing
        notarization_mode = "apple-id" if apple_complete else "app-store-connect-api" if api_complete else None
        present = certificate_present + (apple_present if apple_complete else api_present)
        if api_complete:
            present.append(api_location_name)
        missing = list(certificate_missing)
        blockers: list[str] = []
        if certificate_missing:
            blockers.append("missing macOS signing inputs: " + ", ".join(certificate_missing))
        if not notarization_mode:
            missing.append("complete Apple ID trio or App Store Connect API key set")
            blockers.append(
                "configure notarization with APPLE_ID/APPLE_PASSWORD/APPLE_TEAM_ID or "
                "APPLE_API_KEY/APPLE_API_ISSUER plus an API key path"
            )
        return {
            "schemaVersion": 1,
            "platform": "macos",
            "mode": "developer-id",
            "notarizationMode": notarization_mode,
            "readyForPlatformSigning": not certificate_missing and notarization_mode is not None,
            "presentInputs": present,
            "missingInputs": missing,
            "blockers": blockers,
            "secretValuesIncluded": False,
        }

    if normalized == "linux":
        return {
            "schemaVersion": 1,
            "platform": "linux",
            "mode": "checksums-only",
            "readyForPlatformSigning": False,
            "presentInputs": [],
            "missingInputs": ["Linux package/repository signing policy"],
            "blockers": ["select a Linux package/repository signing policy before public publication"],
            "secretValuesIncluded": False,
        }
    raise ValueError("platform must be Windows, macOS, or Linux")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        report = evaluate(args.platform, os.environ)
    except ValueError as exc:
        parser.error(str(exc))
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 1 if args.require_ready and not report["readyForPlatformSigning"] else 0


if __name__ == "__main__":
    sys.exit(main())
