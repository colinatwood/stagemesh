#!/usr/bin/env python3
"""Bind the verified desktop distribution bundles into one unsigned candidate.

The resulting index is a CI review artifact. It never publishes a release or
claims signing, legal approval, clean-host installation, accessibility, or
physical hardware qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_VERIFIER = Path(__file__).with_name("verify-desktop-download.py")
DOCUMENT_TYPE = "org.stagemesh.desktop-release-candidate"
INDEX_NAME = "desktop-release-index.json"
MANIFEST_NAME = "desktop-artifacts.json"
CHECKSUM_NAME = "SHA256SUMS"
SIGNING_NAME = "signing-verification.json"
REQUIRED_BUNDLES = (
    ("Linux", "standard"),
    ("macOS", "standard"),
    ("Windows", "online"),
    ("Windows", "offline"),
)
KNOWN_PLATFORMS = frozenset(platform for platform, _ in REQUIRED_BUNDLES)
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 5 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} is missing")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"{label} exceeds the 5 MiB input limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _relative(root: Path, path: Path, label: str) -> str:
    try:
        value = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} is outside the release-candidate directory") from exc
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValueError(f"{label} has an unsafe path")
    return value


def _verifier_module():
    spec = importlib.util.spec_from_file_location("verify_desktop_download", DOWNLOAD_VERIFIER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load download verifier: {DOWNLOAD_VERIFIER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest_summary(
    root: Path,
    manifest_path: Path,
    *,
    version: str,
    source_commit: str,
) -> dict[str, Any]:
    bundle = manifest_path.parent
    bundle_relative = _relative(root, bundle, "desktop bundle")
    if len(PurePosixPath(bundle_relative).parts) != 1:
        raise ValueError(f"desktop bundle must be one directory below the candidate root: {bundle_relative}")

    manifest = _load_object(manifest_path, f"{bundle_relative}/{MANIFEST_NAME}")
    if manifest.get("product") != "StageMesh" or manifest.get("schemaVersion") != 1:
        raise ValueError(f"{bundle_relative}: artifact manifest identity is invalid")
    if manifest.get("version") != version:
        raise ValueError(f"{bundle_relative}: artifact version does not match {version}")
    if manifest.get("sourceCommit") != source_commit:
        raise ValueError(f"{bundle_relative}: artifact source commit does not match {source_commit}")
    platform = manifest.get("platform")
    if platform not in KNOWN_PLATFORMS:
        raise ValueError(f"{bundle_relative}: platform must be Linux, macOS, or Windows")
    channel = manifest.get("distributionChannel")
    if (platform, channel) not in REQUIRED_BUNDLES:
        raise ValueError(f"{bundle_relative}: platform/distribution channel is invalid")
    expected_qualification = {
        "softwarePackageBuilt": True,
        "cleanHostInstallQualified": False,
        "physicalHardwareQualified": False,
    }
    if manifest.get("qualification") != expected_qualification:
        raise ValueError(f"{bundle_relative}: artifact qualification boundary is invalid")

    verification = _verifier_module().evaluate(bundle)
    if not verification.get("passed"):
        details = "; ".join(str(item) for item in verification.get("blockers", []))
        raise ValueError(f"{bundle_relative}: download verification failed: {details}")

    signing_path = bundle / SIGNING_NAME
    signing = _load_object(signing_path, f"{bundle_relative}/{SIGNING_NAME}")
    signing_status = signing.get("status")
    if signing_status not in {"failed", "not-configured", "verified"}:
        raise ValueError(f"{bundle_relative}: signing verification status is invalid")
    if signing_status == "failed":
        raise ValueError(f"{bundle_relative}: signing verification failed")
    if signing.get("readyForPublication") is not False:
        raise ValueError(f"{bundle_relative}: signing report publication boundary must remain false")
    expected_signing_platform = {"Linux": "linux", "macOS": "macos", "Windows": "windows"}[platform]
    if signing.get("platform") != expected_signing_platform:
        raise ValueError(f"{bundle_relative}: signing report platform does not match manifest")
    if signing.get("secretValuesIncluded") is not False:
        raise ValueError(f"{bundle_relative}: signing report secret boundary must remain false")
    if signing_status == "verified":
        exact_artifacts = signing.get("exactArtifacts")
        if not isinstance(exact_artifacts, list) or not exact_artifacts:
            raise ValueError(f"{bundle_relative}: verified signing report lacks exact artifacts")
        if any(
            not isinstance(item, dict)
            or item.get("status") == "failed"
            or item.get("verification") != "verified"
            for item in exact_artifacts
        ):
            raise ValueError(f"{bundle_relative}: exact artifact signature verification is incomplete")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError(f"{bundle_relative}: artifact manifest files are missing")
    payload_bytes = 0
    for item in files:
        if not isinstance(item, dict):
            raise ValueError(f"{bundle_relative}: artifact manifest file entry is invalid")
        size = item.get("bytes")
        digest = item.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"{bundle_relative}: artifact manifest byte count is invalid")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ValueError(f"{bundle_relative}: artifact manifest digest is invalid")
        payload_bytes += size

    checksum_path = bundle / CHECKSUM_NAME
    if not checksum_path.is_file():
        raise ValueError(f"{bundle_relative}/{CHECKSUM_NAME} is missing")
    return {
        "platform": platform,
        "distributionChannel": channel,
        "artifactName": bundle_relative,
        "manifestFileCount": len(files),
        "manifestPayloadBytes": payload_bytes,
        "artifactManifest": {
            "path": f"{bundle_relative}/{MANIFEST_NAME}",
            "bytes": manifest_path.stat().st_size,
            "sha256": _sha256(manifest_path),
        },
        "checksums": {
            "path": f"{bundle_relative}/{CHECKSUM_NAME}",
            "bytes": checksum_path.stat().st_size,
            "sha256": _sha256(checksum_path),
        },
        "signingVerification": {
            "path": f"{bundle_relative}/{SIGNING_NAME}",
            "bytes": signing_path.stat().st_size,
            "sha256": _sha256(signing_path),
            "status": signing_status,
            "exactArtifactCount": len(signing.get("exactArtifacts", []))
            if isinstance(signing.get("exactArtifacts"), list) else 0,
        },
        "downloadVerification": {
            "passed": True,
            "filesVerified": verification.get("filesVerified"),
            "signingVerificationStatus": verification.get("signingVerificationStatus"),
        },
        "qualification": expected_qualification,
    }


def build_index(
    directory: Path,
    *,
    version: str,
    source_commit: str,
    required_bundles: tuple[tuple[str, str], ...] = REQUIRED_BUNDLES,
) -> dict[str, Any]:
    root = Path(directory).resolve()
    if not root.is_dir():
        raise ValueError("release-candidate directory does not exist")
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("version must use MAJOR.MINOR.PATCH with an optional prerelease suffix")
    if not COMMIT_PATTERN.fullmatch(source_commit):
        raise ValueError("source commit must be a lowercase 40-character SHA")
    if not required_bundles or len(required_bundles) != len(set(required_bundles)):
        raise ValueError("required bundles must be unique and non-empty")
    if any(bundle not in REQUIRED_BUNDLES for bundle in required_bundles):
        raise ValueError("required platform/distribution channel is invalid")

    manifests = sorted(root.rglob(MANIFEST_NAME), key=lambda item: item.as_posix())
    if not manifests:
        raise ValueError("release candidate contains no desktop artifact manifests")
    summaries: dict[tuple[str, str], dict[str, Any]] = {}
    for manifest_path in manifests:
        summary = _manifest_summary(
            root,
            manifest_path,
            version=version,
            source_commit=source_commit,
        )
        key = (str(summary["platform"]), str(summary["distributionChannel"]))
        if key in summaries:
            raise ValueError(
                "release candidate contains duplicate "
                f"{key[0]}/{key[1]} bundles"
            )
        summaries[key] = summary

    missing = [bundle for bundle in required_bundles if bundle not in summaries]
    unexpected = [bundle for bundle in summaries if bundle not in required_bundles]
    if missing:
        raise ValueError(
            "release candidate is missing distribution bundles: "
            + ", ".join(f"{platform}/{channel}" for platform, channel in missing)
        )
    if unexpected:
        raise ValueError(
            "release candidate has unexpected distribution bundles: "
            + ", ".join(f"{platform}/{channel}" for platform, channel in unexpected)
        )

    platforms = [summaries[bundle] for bundle in required_bundles]
    all_signatures_verified = all(
        item["signingVerification"]["status"] == "verified" for item in platforms
    )
    return {
        "documentType": DOCUMENT_TYPE,
        "schemaVersion": 1,
        "product": "StageMesh",
        "version": version,
        "sourceCommit": source_commit,
        "candidateId": f"stagemesh-{version}-{source_commit[:12]}",
        "releaseChannel": "unsigned-ci-candidate",
        "platforms": platforms,
        "summary": {
            "requiredPlatformCount": len({platform for platform, _ in required_bundles}),
            "verifiedPlatformCount": len({item["platform"] for item in platforms}),
            "requiredBundleCount": len(required_bundles),
            "verifiedBundleCount": len(platforms),
            "allBundlesIntegrityVerified": True,
            "allSignaturesVerified": all_signatures_verified,
        },
        "readiness": {
            "readyForUnsignedTesting": True,
            "readyForPublication": False,
            "ownerLegalReviewComplete": False,
            "cleanHostInstallQualified": False,
            "accessibilityQualified": False,
            "physicalHardwareQualified": False,
            "blockers": [
                "Project-license and packaged-notice review requires owner/legal approval.",
                "Platform signing, notarization, and Linux package-signing policy are not fully verified.",
                "Clean-host installation, upgrade, uninstall, and second-user evidence remain external.",
                "Assistive-technology and physical audio/MIDI qualification remain external.",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, default=Path(INDEX_NAME))
    args = parser.parse_args(argv)
    try:
        report = build_index(args.directory, version=args.version, source_commit=args.commit)
        payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        output = args.output.resolve()
        inputs = {
            path.resolve()
            for path in args.directory.rglob("*.json")
            if path.is_file()
        }
        if output in inputs:
            raise ValueError("release index output cannot overwrite an input JSON file")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"desktop release index failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
