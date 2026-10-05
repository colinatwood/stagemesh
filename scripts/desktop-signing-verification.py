#!/usr/bin/env python3
"""Verify signatures on exact StageMesh desktop artifacts when configured.

This is deliberately separate from the signing-input readiness report. It only
reports a verified result after a native platform verifier has accepted the
exact file or bundle and its contents match the generated artifact manifest.
With no provider selected it remains an advisory, non-failing report. A
required verification mode fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "desktop-artifacts.json"
SIGNABLE_SUFFIXES = {
    "windows": frozenset({".exe", ".msi"}),
    "macos": frozenset({".app", ".dmg", ".pkg"}),
    "linux": frozenset({".appimage", ".deb", ".rpm"}),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _files_in(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(item for item in path.rglob("*") if item.is_file())


def _tool(name: str, environment: Mapping[str, str]) -> str | None:
    configured = str(environment.get(name, "")).strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate)
        return None
    path = environment.get("PATH")
    return shutil.which(name, path=path)


def _platform(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {"windows": "windows", "win32": "windows", "macos": "macos", "darwin": "macos", "linux": "linux"}
    if normalized not in aliases:
        raise ValueError("platform must be Windows, macOS, or Linux")
    return aliases[normalized]


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("artifact manifest must be a JSON object")
    if payload.get("product") != "StageMesh":
        raise ValueError("artifact manifest product must be StageMesh")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("artifact manifest files must be a non-empty list")
    return payload


def _artifact_reference(root: Path, artifact: Path) -> tuple[str, bool]:
    """Return a stable report path and whether it is inside the bundle root."""
    try:
        return artifact.resolve().relative_to(root.resolve()).as_posix(), True
    except ValueError:
        return artifact.name or "selected-artifact", False


def _manifest_entries(manifest: dict[str, Any], root: Path, artifact: Path) -> tuple[list[dict[str, Any]], list[str]]:
    relative, inside_root = _artifact_reference(root, artifact)
    if not inside_root:
        return [], [f"artifact is outside manifest directory: {relative}"]
    files = [item for item in manifest["files"] if isinstance(item, dict)]
    if artifact.is_file():
        entries = [item for item in files if item.get("path") == relative]
    else:
        prefix = relative.rstrip("/") + "/"
        entries = [item for item in files if isinstance(item.get("path"), str) and item["path"].startswith(prefix)]
    if not entries:
        return [], [f"artifact is not represented in manifest: {relative}"]
    return entries, []


def _bind_artifact(manifest: dict[str, Any], root: Path, artifact: Path) -> tuple[dict[str, Any], list[str]]:
    report_path, inside_root = _artifact_reference(root, artifact)
    entries, blockers = _manifest_entries(manifest, root, artifact)
    if blockers:
        report = {"path": report_path, "status": "failed", "manifestEntries": []}
        if not inside_root:
            report["pathScope"] = "outside-manifest-directory"
        return report, blockers
    actual_by_path = {path.relative_to(root).as_posix(): path for path in _files_in(artifact)}
    expected_paths = {str(item["path"]) for item in entries}
    current_paths = set(actual_by_path)
    missing = sorted(expected_paths - current_paths)
    unexpected = sorted(current_paths - expected_paths)
    if missing:
        blockers.append("manifest files missing from artifact: " + ", ".join(missing))
    if unexpected:
        blockers.append("artifact contains files absent from manifest: " + ", ".join(unexpected))
    verified_entries: list[dict[str, Any]] = []
    for item in entries:
        path_text = str(item["path"])
        current = actual_by_path.get(path_text)
        if current is None:
            continue
        actual_bytes = current.stat().st_size
        actual_sha256 = _sha256(current)
        if item.get("bytes") != actual_bytes or item.get("sha256") != actual_sha256:
            blockers.append(f"manifest digest mismatch for {path_text}")
        verified_entries.append({
            "path": path_text,
            "bytes": actual_bytes,
            "sha256": actual_sha256,
        })
    return {
        "path": report_path,
        "status": "failed" if blockers else "bound",
        "manifestEntries": verified_entries,
    }, blockers


def _run_verifier(platform: str, artifact: Path, environment: Mapping[str, str]) -> tuple[str, str | None]:
    if platform == "linux":
        return "not-configured", "Linux package/repository signing policy has no verification adapter"
    mode = str(environment.get("STAGEMESH_SIGNING_VERIFICATION_MODE", "")).strip().lower()
    if mode not in {"advisory", "required"}:
        return "not-configured", "STAGEMESH_SIGNING_VERIFICATION_MODE is unset or invalid; provider verification is disabled"
    suffix = artifact.suffix.lower()
    if platform == "windows":
        tool = _tool("STAGEMESH_SIGNTOOL_PATH", environment) or _tool("signtool", environment)
        if not tool:
            return "not-configured", "Windows signtool is unavailable"
        command = [tool, "verify", "/pa", "/all", str(artifact)]
        method = "authenticode-signtool"
    elif platform == "macos":
        if suffix == ".app":
            tool = _tool("codesign", environment)
            command = [tool, "--verify", "--deep", "--strict", str(artifact)] if tool else []
            method = "codesign"
        elif suffix == ".dmg":
            tool = _tool("spctl", environment)
            command = [tool, "--assess", "--type", "open", "--context", "context:primary-signature", str(artifact)] if tool else []
            method = "spctl"
        elif suffix == ".pkg":
            tool = _tool("pkgutil", environment)
            command = [tool, "--check-signature", str(artifact)] if tool else []
            method = "pkgutil"
        else:
            tool = _tool("codesign", environment)
            command = [tool, "--verify", "--strict", str(artifact)] if tool else []
            method = "codesign"
        if not tool:
            return "not-configured", f"macOS {method} verifier is unavailable"
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "failed", f"{method} verifier could not complete"
    if result.returncode != 0:
        return "failed", f"{method} rejected the exact artifact"
    return "verified", None


def discover(directory: Path, platform: str) -> list[Path]:
    suffixes = SIGNABLE_SUFFIXES[platform]
    candidates: list[Path] = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        if path.suffix.lower() not in suffixes:
            continue
        if path.is_dir() and platform == "macos" and path.suffix.lower() == ".app":
            candidates.append(path)
        elif path.is_file():
            candidates.append(path)
    return candidates


def evaluate(
    platform: str,
    manifest_path: Path,
    artifacts: list[Path] | None = None,
    directory: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    normalized = _platform(platform)
    env = environment or os.environ
    manifest_path = manifest_path.resolve()
    root = manifest_path.parent
    blockers: list[str] = []
    try:
        manifest = _load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "schemaVersion": 1,
            "product": "StageMesh",
            "platform": normalized,
            "status": "failed",
            "readyForPublication": False,
            "exactArtifacts": [],
            "blockers": [f"artifact manifest check failed: {exc}"],
            "secretValuesIncluded": False,
        }
    manifest_binding = {
        "path": manifest_path.name,
        "sha256": _sha256(manifest_path),
    }

    selected = [path.resolve() for path in (artifacts or [])]
    if not selected and directory is not None:
        selected = discover(directory.resolve(), normalized)
    exact_reports: list[dict[str, Any]] = []
    if not selected:
        blockers.append("no exact signable artifacts were selected")

    for artifact in selected:
        if not artifact.exists():
            report_path, inside_root = _artifact_reference(root, artifact)
            report = {"path": report_path, "status": "failed", "manifestEntries": []}
            if not inside_root:
                report["pathScope"] = "outside-manifest-directory"
            exact_reports.append(report)
            blockers.append(f"artifact does not exist: {report_path}")
            continue
        binding, binding_blockers = _bind_artifact(manifest, root, artifact)
        blockers.extend(binding_blockers)
        if binding_blockers:
            exact_reports.append(binding)
            continue
        verification, verification_blocker = _run_verifier(normalized, artifact, env)
        binding["verification"] = verification
        exact_reports.append(binding)
        if verification_blocker:
            blockers.append(f"{artifact.name}: {verification_blocker}")

    statuses = [item.get("verification") for item in exact_reports]
    artifact_failed = any(
        item.get("status") == "failed" or item.get("verification") == "failed"
        for item in exact_reports
    )
    if artifact_failed:
        status = "failed"
    elif exact_reports and all(status == "verified" for status in statuses) and not blockers:
        status = "verified"
    else:
        status = "not-configured"
    return {
        "schemaVersion": 1,
        "product": "StageMesh",
        "platform": normalized,
        "status": status,
        "verificationMode": str(env.get("STAGEMESH_SIGNING_VERIFICATION_MODE", "")).strip().lower() or None,
        "artifactManifest": manifest_binding,
        "readyForPublication": False,
        "exactArtifacts": exact_reports,
        "blockers": blockers,
        "secretValuesIncluded": False,
        "publicationBoundary": [
            "A verified signature covers only the exact artifact and manifest contents checked here.",
            "This report does not establish legal approval, clean-host installation, or physical audio/MIDI qualification.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--artifact", action="append", type=Path, default=[])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-verified", action="store_true")
    args = parser.parse_args()
    try:
        report = evaluate(args.platform, args.manifest, args.artifact, args.directory)
    except ValueError as exc:
        parser.error(str(exc))
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    required = args.require_verified or report.get("verificationMode") == "required"
    return 0 if report["status"] == "verified" or (report["status"] == "not-configured" and not required) else 1


if __name__ == "__main__":
    sys.exit(main())
