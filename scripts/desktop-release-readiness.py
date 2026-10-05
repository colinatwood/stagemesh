#!/usr/bin/env python3
"""Check software-only desktop release readiness without making release claims.

This gate validates the inputs that can be checked in source/CI. It deliberately
does not sign, notarize, approve a license, or convert clean-host or hardware
evidence into a qualification claim.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION_SCRIPT = Path(__file__).with_name("verify-desktop-version.py")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_DISTRIBUTION_FILES = ("LICENSE", "THIRD_PARTY_NOTICES.md")


def version_module():
    spec = importlib.util.spec_from_file_location("verify_desktop_version", VERSION_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load version verifier: {VERSION_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest_error(manifest: dict[str, Any], version: str) -> str | None:
    if manifest.get("schemaVersion") != 1:
        return "artifact manifest schemaVersion must be 1"
    if manifest.get("product") != "StageMesh":
        return "artifact manifest product must be StageMesh"
    if manifest.get("version") != version:
        return f"artifact manifest version {manifest.get('version')!r} does not match {version}"
    platform = manifest.get("platform")
    if not isinstance(platform, str) or not platform.strip():
        return "artifact manifest platform is missing"
    commit = manifest.get("sourceCommit")
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        return "artifact manifest sourceCommit must be a 40-character lowercase commit"
    if not isinstance(manifest.get("signed"), bool):
        return "artifact manifest signed must be boolean"
    if manifest.get("signed") is not False:
        return "unsigned readiness requires artifact manifest signed=false"
    qualification = manifest.get("qualification")
    if not isinstance(qualification, dict):
        return "artifact manifest qualification must be an object"
    if qualification.get("softwarePackageBuilt") is not True:
        return "artifact manifest must mark softwarePackageBuilt=true"
    forbidden = [
        name for name in ("cleanHostInstallQualified", "physicalHardwareQualified")
        if qualification.get(name) is not False
    ]
    if forbidden:
        return "artifact manifest cannot claim qualification: " + ", ".join(forbidden)
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return "artifact manifest files must be a non-empty list"
    for item in files:
        if not isinstance(item, dict):
            return "artifact manifest file entries must be objects"
        path = item.get("path")
        path_parts = Path(path).parts if isinstance(path, str) else ()
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in path_parts:
            return "artifact manifest file paths must be safe relative paths"
        if not isinstance(item.get("bytes"), int) or item["bytes"] < 0:
            return f"artifact manifest byte count is invalid for {path}"
        digest = item.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return f"artifact manifest SHA-256 is invalid for {path}"
    return None


def evaluate(root: Path, tag: str | None = None, manifest_path: Path | None = None) -> dict[str, Any]:
    """Return a deterministic readiness report; ``passed`` covers software checks only."""
    root = root.resolve()
    blockers: list[str] = []
    version_report: dict[str, Any] | None = None
    try:
        version_report = version_module().verify(root, tag)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        blockers.append(f"desktop version check failed: {exc}")

    missing = [name for name in REQUIRED_DISTRIBUTION_FILES if not (root / name).is_file()]
    if missing:
        blockers.append("missing required distribution file(s): " + ", ".join(missing))

    manifest_report: dict[str, Any] | None = None
    if manifest_path is not None:
        path = manifest_path.resolve()
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("artifact manifest must be a JSON object")
            manifest_report = {
                "path": str(path),
                "signed": manifest.get("signed"),
                "platform": manifest.get("platform"),
                "sourceCommit": manifest.get("sourceCommit"),
            }
            if version_report is not None:
                error = _manifest_error(manifest, str(version_report["version"]))
                if error:
                    blockers.append(error)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            blockers.append(f"artifact manifest check failed: {exc}")

    passed = not blockers
    return {
        "schemaVersion": 1,
        "passed": passed,
        "version": version_report.get("version") if version_report else None,
        "tag": tag,
        "manifests": version_report.get("manifests") if version_report else None,
        "distributionFilesPresent": not missing,
        "artifactManifest": manifest_report,
        "readyForUnsignedTesting": passed,
        "readyForPublication": False,
        "blockers": blockers,
        "publicationBoundary": [
            "Platform signing and notarization evidence is not produced or verified here.",
            "The project-license decision and dependency notice review remain owner/legal work.",
            "Clean-host installation and physical audio/MIDI qualification remain external evidence.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--tag", default="")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    report = evaluate(args.root, args.tag or None, args.manifest)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
