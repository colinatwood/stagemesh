#!/usr/bin/env python3
"""Bind clean-host reports to one exact StageMesh desktop candidate.

This is a fail-closed evidence reviewer, not a qualification authority.  It
never marks clean-host installation, accessibility, signing, or physical
hardware as qualified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


DOCUMENT_TYPE = "org.stagemesh.desktop-clean-host-evidence-review"
INDEX_DOCUMENT_TYPE = "org.stagemesh.desktop-release-candidate"
EVIDENCE_DOCUMENT_TYPES = {
    "Windows": "org.stagemesh.windows-desktop-clean-host-evidence",
    "macOS": "org.stagemesh.posix-desktop-clean-host-evidence",
    "Linux": "org.stagemesh.posix-desktop-clean-host-evidence",
}
REQUIRED_TRACKS = (
    ("Windows", "exe"),
    ("Windows", "msi"),
    ("macOS", "dmg"),
    ("Linux", "deb"),
    ("Linux", "appimage"),
)
REQUIRED_PHASES = ("baseline", "installed", "restarted", "upgraded", "uninstalled")
MAX_JSON_BYTES = 5 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


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
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _index_platforms(index: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    if (
        index.get("documentType") != INDEX_DOCUMENT_TYPE
        or index.get("schemaVersion") != 1
        or index.get("product") != "StageMesh"
    ):
        raise ValueError("release index identity is invalid")
    version = index.get("version")
    commit = index.get("sourceCommit")
    candidate_id = index.get("candidateId")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("release index version is invalid")
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("release index source commit is invalid")
    if candidate_id != f"stagemesh-{version}-{commit[:12]}":
        raise ValueError("release index candidate identity is invalid")
    index_readiness = index.get("readiness")
    if not isinstance(index_readiness, dict) or index_readiness.get("cleanHostInstallQualified") is not False:
        raise ValueError("release index clean-host qualification boundary is invalid")

    entries = index.get("platforms")
    if not isinstance(entries, list):
        raise ValueError("release index platforms are invalid")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    channelled = any(isinstance(entry, dict) and "distributionChannel" in entry for entry in entries)
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("platform") not in EVIDENCE_DOCUMENT_TYPES:
            raise ValueError("release index platform entry is invalid")
        platform = str(entry["platform"])
        channel = entry.get("distributionChannel") if channelled else "legacy"
        allowed = {"online", "offline"} if platform == "Windows" else {"standard"}
        if channelled and channel not in allowed:
            raise ValueError(f"release index {platform} distribution channel is invalid")
        key = (platform, str(channel))
        if key in result:
            raise ValueError(f"release index contains duplicate {platform}/{channel} platform entries")
        manifest = entry.get("artifactManifest")
        if not isinstance(manifest, dict):
            raise ValueError(f"release index {platform} manifest binding is invalid")
        _require_digest(manifest.get("sha256"), f"release index {platform} manifest digest")
        if type(manifest.get("bytes")) is not int or manifest["bytes"] <= 0:
            raise ValueError(f"release index {platform} manifest size is invalid")
        qualification = entry.get("qualification")
        if not isinstance(qualification, dict) or qualification.get("cleanHostInstallQualified") is not False:
            raise ValueError(f"release index {platform} qualification boundary is invalid")
        result[key] = entry
    expected = ({("Linux", "standard"), ("macOS", "standard"), ("Windows", "online"), ("Windows", "offline")}
                if channelled else {(platform, "legacy") for platform in EVIDENCE_DOCUMENT_TYPES})
    if set(result) != expected:
        raise ValueError("release index must contain exactly the required platform/channel bundles")
    return result


def _evidence_summary(
    path: Path,
    evidence: dict[str, Any],
    index: dict[str, Any],
    platforms: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    document_type = evidence.get("documentType")
    candidates = [name for name, expected in EVIDENCE_DOCUMENT_TYPES.items() if expected == document_type]
    candidate = evidence.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError(f"{path.name}: evidence candidate is invalid")
    platform = candidate.get("platform")
    if document_type == EVIDENCE_DOCUMENT_TYPES["Windows"]:
        platform = "Windows"
    if platform not in candidates:
        raise ValueError(f"{path.name}: evidence platform and document type do not match")
    if evidence.get("schemaVersion") != 1 or evidence.get("product") != "StageMesh":
        raise ValueError(f"{path.name}: evidence identity is invalid")
    if candidate.get("version") != index["version"]:
        raise ValueError(f"{path.name}: candidate version does not match the release index")
    if candidate.get("sourceCommit") != index["sourceCommit"]:
        raise ValueError(f"{path.name}: candidate source commit does not match the release index")

    manifest = candidate.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError(f"{path.name}: candidate manifest binding is invalid")
    matches = [channel for (name, channel), entry in platforms.items()
               if name == platform and manifest.get("sha256") == entry["artifactManifest"]["sha256"]
               and manifest.get("bytes") == entry["artifactManifest"]["bytes"]]
    if len(matches) != 1:
        raise ValueError(f"{path.name}: candidate manifest does not match exactly one release index bundle")
    channel = matches[0]
    evidence_channel = candidate.get("distributionChannel")
    if channel == "legacy":
        if evidence_channel is not None:
            raise ValueError(f"{path.name}: legacy candidate must not claim a distribution channel")
    elif evidence_channel != channel:
        raise ValueError(f"{path.name}: candidate distribution channel does not match its manifest")

    installer = candidate.get("installer")
    if not isinstance(installer, dict):
        raise ValueError(f"{path.name}: installer binding is invalid")
    installer_format = installer.get("format")
    track = (str(platform), str(installer_format))
    if track not in REQUIRED_TRACKS:
        raise ValueError(f"{path.name}: unsupported clean-host evidence track {track[0]}/{track[1]}")
    _require_digest(installer.get("sha256"), f"{path.name}: installer digest")
    if type(installer.get("bytes")) is not int or installer["bytes"] <= 0:
        raise ValueError(f"{path.name}: installer size is invalid")
    installer_name = installer.get("name")
    if (
        not isinstance(installer_name, str)
        or not installer_name
        or installer_name in {".", ".."}
        or "/" in installer_name
        or "\\" in installer_name
        or any(ord(character) < 32 for character in installer_name)
    ):
        raise ValueError(f"{path.name}: installer name is invalid")

    phases = evidence.get("phases")
    if not isinstance(phases, list):
        raise ValueError(f"{path.name}: phases are invalid")
    phase_map: dict[str, dict[str, Any]] = {}
    for phase in phases:
        if not isinstance(phase, dict) or phase.get("phase") not in REQUIRED_PHASES:
            raise ValueError(f"{path.name}: phase entry is invalid")
        name = str(phase["phase"])
        if name in phase_map:
            raise ValueError(f"{path.name}: duplicate {name} phase")
        checks = phase.get("checks")
        if (
            phase.get("passed") is not True
            or not isinstance(checks, dict)
            or not checks
            or any(value is not True for value in checks.values())
        ):
            raise ValueError(f"{path.name}: {name} phase did not pass all checks")
        phase_map[name] = phase
    if tuple(name for name in REQUIRED_PHASES if name in phase_map) != REQUIRED_PHASES:
        raise ValueError(f"{path.name}: all required phases have not been recorded")
    summary = evidence.get("summary")
    readiness = evidence.get("readiness")
    if (
        not isinstance(summary, dict)
        or summary.get("requiredPhases") != list(REQUIRED_PHASES)
        or summary.get("passedPhases") != list(REQUIRED_PHASES)
        or summary.get("allRequiredPhasesPassed") is not True
    ):
        raise ValueError(f"{path.name}: evidence phase summary is not complete")
    if (
        not isinstance(readiness, dict)
        or readiness.get("readyForQualificationReview") is not True
        or readiness.get("cleanHostInstallQualified") is not False
        or readiness.get("physicalHardwareQualified") is not False
    ):
        raise ValueError(f"{path.name}: evidence qualification boundary is invalid")
    runner = evidence.get("runner")
    if (
        not isinstance(runner, dict)
        or not isinstance(runner.get("runnerIdHash"), str)
        or not isinstance(runner.get("os"), dict)
    ):
        raise ValueError(f"{path.name}: runner identity is invalid")
    runner_hash = runner["runnerIdHash"]
    if not runner_hash.startswith("sha256:"):
        raise ValueError(f"{path.name}: runner identity is invalid")
    _require_digest(runner_hash[7:], f"{path.name}: runner identity")

    return {
        "platform": platform,
        "distributionChannel": channel,
        "installer": {
            "name": installer["name"],
            "format": installer_format,
            "bytes": installer["bytes"],
            "sha256": installer["sha256"],
        },
        "runnerIdHash": runner_hash,
        "passedPhases": list(REQUIRED_PHASES),
        "evidenceFile": {
            "name": path.name,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        },
    }


def build_review(index_path: Path, evidence_paths: list[Path]) -> dict[str, Any]:
    index_path = Path(index_path)
    index = _load_object(index_path, "desktop release index")
    platforms = _index_platforms(index)
    if not evidence_paths:
        raise ValueError("at least one clean-host evidence file is required")

    required_tracks = tuple((platform, channel, installer_format)
                            for platform, installer_format in REQUIRED_TRACKS
                            for name, channel in platforms if name == platform)
    tracks: dict[tuple[str, str, str], dict[str, Any]] = {}
    for evidence_path in evidence_paths:
        path = Path(evidence_path)
        summary = _evidence_summary(
            path,
            _load_object(path, f"clean-host evidence {path.name}"),
            index,
            platforms,
        )
        key = (str(summary["platform"]), str(summary["distributionChannel"]), str(summary["installer"]["format"]))
        if key in tracks:
            raise ValueError(f"duplicate clean-host evidence track {key[0]}/{key[1]}/{key[2]}")
        tracks[key] = summary

    missing = [f"{platform}/{installer_format}" + (f"/{channel}" if channel != "legacy" else "")
               for platform, channel, installer_format in required_tracks
               if (platform, channel, installer_format) not in tracks]
    complete = not missing
    blockers = []
    if missing:
        blockers.append("Missing clean-host evidence tracks: " + ", ".join(missing) + ".")
    blockers.extend([
        "Owner review must verify the bound reports and exact downloaded release candidate.",
        "Signing, legal, accessibility, and physical audio/MIDI qualification remain separate gates.",
    ])
    return {
        "documentType": DOCUMENT_TYPE,
        "schemaVersion": 1,
        "product": "StageMesh",
        "candidate": {
            "candidateId": index["candidateId"],
            "version": index["version"],
            "sourceCommit": index["sourceCommit"],
            "releaseIndex": {
                "name": index_path.name,
                "bytes": index_path.stat().st_size,
                "sha256": _sha256(index_path),
            },
        },
        "requiredTracks": [
            {"platform": platform, "distributionChannel": channel, "installerFormat": installer_format}
            for platform, channel, installer_format in required_tracks
        ],
        "evidence": [tracks[key] for key in required_tracks if key in tracks],
        "summary": {
            "requiredTrackCount": len(required_tracks),
            "reviewReadyTrackCount": len(tracks),
            "allEvidenceBoundToCandidate": True,
            "allRequiredTracksReviewReady": complete,
        },
        "readiness": {
            "readyForOwnerReview": complete,
            "ownerReviewComplete": False,
            "cleanHostInstallQualified": False,
            "accessibilityQualified": False,
            "physicalHardwareQualified": False,
            "blockers": blockers,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inputs = {args.index.resolve(), *(path.resolve() for path in args.evidence)}
        output = args.output.resolve()
        if output in inputs:
            raise ValueError("output must not overwrite an input file")
        report = build_review(args.index, args.evidence)
        payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(output)
        print(payload, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Desktop clean-host review failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
