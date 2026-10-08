#!/usr/bin/env python3
"""Collect exact-candidate macOS or Linux desktop clean-host evidence.

The report is an evidence envelope for later owner review. It never marks a
host, installer, accessibility path, or physical device as qualified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
import subprocess
import sys
from typing import Any


DOCUMENT_TYPE = "org.stagemesh.posix-desktop-clean-host-evidence"
MANIFEST_NAME = "desktop-artifacts.json"
REQUIRED_PHASES = ("baseline", "installed", "restarted", "upgraded", "uninstalled")
MAX_JSON_BYTES = 5 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
PLATFORM_FORMATS = {"macOS": {"dmg"}, "Linux": {"deb", "appimage"}}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} is missing")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"{label} exceeds the JSON size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and value not in {".", ".."}


def _installer_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return "appimage" if suffix == "appimage" else suffix


def _candidate(bundle: Path, installer: Path) -> dict[str, Any]:
    root = bundle.resolve()
    manifest_path = root / MANIFEST_NAME
    manifest = _load_object(manifest_path, "desktop artifact manifest")
    target_platform = manifest.get("platform")
    if manifest.get("product") != "StageMesh" or target_platform not in PLATFORM_FORMATS:
        raise ValueError("clean-host evidence requires a macOS or Linux StageMesh bundle")
    version = manifest.get("version")
    commit = manifest.get("sourceCommit")
    distribution_channel = manifest.get("distributionChannel")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("artifact manifest version is invalid")
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("artifact manifest source commit is invalid")
    if distribution_channel != "standard":
        raise ValueError("macOS and Linux artifact manifest distribution channel must be standard")
    expected_qualification = {
        "softwarePackageBuilt": True,
        "cleanHostInstallQualified": False,
        "physicalHardwareQualified": False,
    }
    if manifest.get("qualification") != expected_qualification:
        raise ValueError("artifact manifest qualification boundary is invalid")

    selected = installer.resolve()
    try:
        relative = selected.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("installer must be inside the verified bundle") from exc
    installer_format = _installer_format(selected)
    if installer_format not in PLATFORM_FORMATS[target_platform]:
        expected = ", ".join(sorted(PLATFORM_FORMATS[target_platform]))
        raise ValueError(f"{target_platform} installer must use one of: {expected}")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("artifact manifest files are invalid")
    entries: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("artifact manifest file entry is invalid")
        path = item["path"]
        if not _safe_relative(path) or path in entries:
            raise ValueError("artifact manifest contains unsafe or duplicate paths")
        entries[path] = item
    entry = entries.get(relative)
    if entry is None:
        raise ValueError("selected installer is not present in the artifact manifest")
    actual_size = selected.stat().st_size
    actual_digest = _sha256_file(selected)
    if entry.get("bytes") != actual_size or entry.get("sha256") != actual_digest:
        raise ValueError("selected installer does not match the artifact manifest")
    return {
        "platform": target_platform,
        "version": version,
        "sourceCommit": commit,
        "distributionChannel": distribution_channel,
        "manifest": {
            "bytes": manifest_path.stat().st_size,
            "sha256": _sha256_file(manifest_path),
        },
        "installer": {
            "name": selected.name,
            "format": installer_format,
            "bytes": actual_size,
            "sha256": actual_digest,
        },
    }


def _valid_runner(snapshot: dict[str, Any], target_platform: str) -> None:
    runner_hash = snapshot.get("runnerIdHash")
    os_info = snapshot.get("os")
    if not isinstance(runner_hash, str) or not runner_hash.startswith("sha256:") or not SHA256_PATTERN.fullmatch(runner_hash[7:]):
        raise ValueError("snapshot requires a SHA-256 runner identity")
    if not isinstance(os_info, dict) or os_info.get("family") != target_platform:
        raise ValueError(f"snapshot requires {target_platform} OS metadata")
    architecture = str(os_info.get("architecture", "")).lower()
    if target_platform == "macOS":
        version = str(os_info.get("version", ""))
        try:
            major = int(version.split(".", 1)[0])
        except ValueError as exc:
            raise ValueError("macOS version is invalid") from exc
        if major < 14 or architecture not in {"arm64", "aarch64"}:
            raise ValueError("clean-host evidence requires macOS 14+ on Apple Silicon")
    else:
        if os_info.get("productName") != "Ubuntu" or os_info.get("version") not in {"22.04", "24.04"}:
            raise ValueError("clean-host evidence requires Ubuntu 22.04 or 24.04")
        if architecture not in {"x86_64", "amd64"}:
            raise ValueError("clean-host evidence requires Ubuntu x64")


def _stagemesh_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    state = snapshot.get("stageMesh")
    if not isinstance(state, dict):
        raise ValueError("snapshot requires StageMesh installation state")
    for name in ("packageEntries", "installedExecutables"):
        if not isinstance(state.get(name), list):
            raise ValueError(f"snapshot StageMesh state requires {name}")
    if type(state.get("runningProcessCount")) is not int or state["runningProcessCount"] < 0:
        raise ValueError("snapshot StageMesh process count is invalid")
    observed = state.get("observedVersion")
    if observed is not None and (not isinstance(observed, str) or not VERSION_PATTERN.fullmatch(observed)):
        raise ValueError("snapshot StageMesh observed version is invalid")
    return state


def _phase_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    phases = report.get("phases")
    if not isinstance(phases, list):
        raise ValueError("evidence phases are invalid")
    result: dict[str, dict[str, Any]] = {}
    for item in phases:
        if not isinstance(item, dict) or item.get("phase") not in REQUIRED_PHASES:
            raise ValueError("evidence phase entry is invalid")
        name = str(item["phase"])
        if name in result:
            raise ValueError("evidence contains a duplicate phase")
        result[name] = item
    return result


def _marker_hash(marker: str | None) -> str | None:
    if marker is None:
        return None
    normalized = marker.strip()
    if not normalized or len(normalized) > 256 or any(ord(ch) < 32 for ch in normalized):
        raise ValueError("persistence marker must be 1-256 printable characters")
    return "sha256:" + _sha256_bytes(normalized.encode("utf-8"))


def _summarize(report: dict[str, Any]) -> None:
    phases = _phase_map(report)
    passed = [name for name in REQUIRED_PHASES if phases.get(name, {}).get("passed") is True]
    all_passed = len(passed) == len(REQUIRED_PHASES)
    blockers = []
    for name in REQUIRED_PHASES:
        phase = phases.get(name)
        if phase is None:
            blockers.append(f"{name} phase has not been recorded")
        elif phase.get("passed") is not True:
            blockers.append(f"{name} phase did not pass")
    blockers.extend([
        "Owner review must verify the evidence and exact downloaded candidate.",
        "Signing, accessibility, and physical audio/MIDI qualification remain separate gates.",
    ])
    report["summary"] = {
        "requiredPhases": list(REQUIRED_PHASES),
        "passedPhases": passed,
        "allRequiredPhasesPassed": all_passed,
    }
    report["readiness"] = {
        "readyForQualificationReview": all_passed,
        "cleanHostInstallQualified": False,
        "physicalHardwareQualified": False,
        "blockers": blockers,
    }


def start_evidence(
    bundle: Path,
    installer: Path,
    snapshot: dict[str, Any],
    *,
    clean_host_attested: bool,
    observed_at_utc: str,
) -> dict[str, Any]:
    candidate = _candidate(bundle, installer)
    _valid_runner(snapshot, candidate["platform"])
    state = _stagemesh_state(snapshot)
    clean = not state["packageEntries"] and not state["installedExecutables"] and state["runningProcessCount"] == 0
    phase = {
        "phase": "baseline",
        "observedAtUtc": observed_at_utc,
        "passed": bool(clean_host_attested and clean),
        "checks": {
            "cleanHostAttested": bool(clean_host_attested),
            "noStageMeshPackageEntry": not state["packageEntries"],
            "noStageMeshExecutableDetected": not state["installedExecutables"],
            "noStageMeshProcessRunning": state["runningProcessCount"] == 0,
            "supportedHost": True,
        },
    }
    report = {
        "documentType": DOCUMENT_TYPE,
        "schemaVersion": 1,
        "product": "StageMesh",
        "candidate": candidate,
        "runner": {"runnerIdHash": snapshot["runnerIdHash"], "os": snapshot["os"]},
        "phases": [phase],
    }
    _summarize(report)
    return report


def append_phase(
    report: dict[str, Any],
    phase: str,
    snapshot: dict[str, Any],
    *,
    observed_at_utc: str,
    runtime_ready_observed: bool = False,
    persistence_marker: str | None = None,
    save_restart_recovered: bool = False,
    previous_version: str | None = None,
    upgrade_observed: bool = False,
    uninstall_observed: bool = False,
) -> dict[str, Any]:
    if report.get("documentType") != DOCUMENT_TYPE or report.get("schemaVersion") != 1:
        raise ValueError("invalid POSIX clean-host evidence document")
    if phase == "baseline" or phase not in REQUIRED_PHASES:
        raise ValueError("invalid append phase")
    candidate = report.get("candidate")
    if not isinstance(candidate, dict) or candidate.get("platform") not in PLATFORM_FORMATS:
        raise ValueError("evidence candidate is invalid")
    _valid_runner(snapshot, candidate["platform"])
    if snapshot["runnerIdHash"] != report.get("runner", {}).get("runnerIdHash"):
        raise ValueError("phase snapshot does not match the baseline runner")
    phases = _phase_map(report)
    if phase in phases:
        raise ValueError(f"{phase} phase is already recorded")
    if "uninstalled" in phases:
        raise ValueError("no phase can be recorded after uninstall")
    prerequisites = {
        "installed": ("baseline",),
        "restarted": ("installed",),
        "upgraded": ("restarted",),
        "uninstalled": ("restarted",),
    }[phase]
    if any(phases.get(name, {}).get("passed") is not True for name in prerequisites):
        raise ValueError(f"{phase} phase prerequisites have not passed")

    state = _stagemesh_state(snapshot)
    target = candidate.get("version")
    installed = bool(state["installedExecutables"])
    package_expected = candidate.get("installer", {}).get("format") == "deb"
    package_detected = bool(state["packageEntries"])
    observed_version = state.get("observedVersion")
    version_matches = observed_version == target
    marker = _marker_hash(persistence_marker)
    checks: dict[str, Any]

    if phase == "installed":
        checks = {
            "installerRegistrationDetectedWhenRequired": package_detected if package_expected else True,
            "installedExecutableDetected": installed,
            "installedVersionMatchesCandidate": version_matches,
            "runtimeReadyObserved": bool(runtime_ready_observed),
            "persistenceMarkerRecorded": marker is not None,
        }
    elif phase == "restarted":
        installed_marker = phases["installed"].get("persistenceMarkerHash")
        checks = {
            "installedStateStillDetected": installed,
            "installedVersionMatchesCandidate": version_matches,
            "runtimeReadyObserved": bool(runtime_ready_observed),
            "saveRestartRecovered": bool(save_restart_recovered),
            "persistenceMarkerMatches": marker is not None and marker == installed_marker,
        }
    elif phase == "upgraded":
        previous_valid = isinstance(previous_version, str) and bool(VERSION_PATTERN.fullmatch(previous_version)) and previous_version != target
        restarted_marker = phases["restarted"].get("persistenceMarkerHash")
        checks = {
            "upgradeObserved": bool(upgrade_observed),
            "previousVersionIsDifferent": previous_valid,
            "installedStateDetected": installed,
            "installedVersionMatchesCandidate": version_matches,
            "runtimeReadyObserved": bool(runtime_ready_observed),
            "upgradeStatePreserved": bool(save_restart_recovered) and marker is not None and marker == restarted_marker,
        }
    else:
        checks = {
            "uninstallObserved": bool(uninstall_observed),
            "packageRegistrationRemoved": not state["packageEntries"],
            "installedExecutableRemoved": not state["installedExecutables"],
            "noStageMeshProcessRunning": state["runningProcessCount"] == 0,
        }

    entry: dict[str, Any] = {
        "phase": phase,
        "observedAtUtc": observed_at_utc,
        "passed": all(value is True for value in checks.values()),
        "checks": checks,
    }
    if marker is not None and phase != "uninstalled":
        entry["persistenceMarkerHash"] = marker
    if phase == "upgraded" and previous_version is not None:
        entry["previousVersion"] = previous_version
    if phase != "uninstalled":
        entry["observedInstalledVersion"] = observed_version
    report["phases"].append(entry)
    _summarize(report)
    return report


def _os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def _mac_application_version(application: Path) -> str | None:
    app = application
    if app.is_file():
        for parent in app.parents:
            if parent.suffix == ".app":
                app = parent
                break
    plist = app / "Contents" / "Info.plist"
    if not plist.is_file():
        return None
    with plist.open("rb") as source:
        value = plistlib.load(source).get("CFBundleShortVersionString")
    return str(value) if isinstance(value, str) and VERSION_PATTERN.fullmatch(value) else None


def _installed_record(path: Path) -> dict[str, Any] | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if not resolved.exists():
        return None
    identity = resolved / "Contents" / "Info.plist" if resolved.is_dir() else resolved
    if not identity.is_file():
        return None
    return {
        "pathHash": "sha256:" + _sha256_bytes(str(resolved).encode("utf-8")),
        "identityBytes": identity.stat().st_size,
        "identitySha256": _sha256_file(identity),
    }


def collect_posix_snapshot(
    installed_executable: Path | None = None,
    observed_version: str | None = None,
) -> dict[str, Any]:
    if sys.platform not in {"darwin", "linux"}:
        raise RuntimeError("live POSIX clean-host collection must run on macOS or Linux")
    if observed_version is not None and not VERSION_PATTERN.fullmatch(observed_version):
        raise ValueError("observed installed version is invalid")

    if sys.platform == "darwin":
        target_platform = "macOS"
        uuid = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, check=True,
        ).stdout
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', uuid)
        if match is None:
            raise RuntimeError("could not read the macOS platform UUID")
        product_name = "macOS"
        version = platform.mac_ver()[0]
        identity = f"{match.group(1)}\0{os.getuid()}".encode("utf-8")
        applications = [installed_executable] if installed_executable else [
            Path("/Applications/StageMesh.app"),
            Path.home() / "Applications" / "StageMesh.app",
        ]
        detected_version = observed_version
        if detected_version is None:
            detected_version = next((_mac_application_version(item) for item in applications if item and item.exists()), None)
        package_entries: list[dict[str, str]] = []
        app_data = Path.home() / "Library" / "Application Support" / "org.stagemesh.desktop"
        webview = {"detected": True, "provider": "WKWebView system framework"}
    else:
        target_platform = "Linux"
        release = _os_release()
        product_name = release.get("NAME", "")
        version = release.get("VERSION_ID", "")
        machine_id = Path("/etc/machine-id").read_text(encoding="utf-8").strip()
        if not machine_id:
            raise RuntimeError("could not read the Linux machine identity")
        identity = f"{machine_id}\0{os.getuid()}".encode("utf-8")
        applications = [installed_executable] if installed_executable else [
            Path.home() / ".local" / "bin" / "StageMesh.AppImage",
            Path("/usr/bin/stagemesh"),
        ]
        package_entries = []
        package_query = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}\t${Version}\n", "stagemesh"],
            capture_output=True, text=True,
        )
        if package_query.returncode == 0 and package_query.stdout.startswith("install ok installed\t"):
            package_version = package_query.stdout.split("\t", 1)[1].strip().split("-", 1)[0]
            package_entries.append({"package": "stagemesh", "version": package_version})
            if observed_version is None and VERSION_PATTERN.fullmatch(package_version):
                observed_version = package_version
        detected_version = observed_version
        app_data = Path.home() / ".local" / "share" / "org.stagemesh.desktop"
        webkit = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}\t${Version}\n", "libwebkit2gtk-4.1-0"],
            capture_output=True, text=True,
        )
        webview = {
            "detected": webkit.returncode == 0 and webkit.stdout.startswith("install ok installed\t"),
            "provider": "libwebkit2gtk-4.1-0",
        }

    installed = [record for item in applications if item is not None for record in [_installed_record(item)] if record is not None]
    processes = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, text=True, check=True)
    process_count = sum(
        1 for name in processes.stdout.splitlines()
        if Path(name.strip()).name.lower() in {"stagemesh", "stagemesh-runtime", "stagemesh_engine"}
    )
    return {
        "runnerIdHash": "sha256:" + _sha256_bytes(identity),
        "os": {
            "family": target_platform,
            "productName": product_name,
            "version": version,
            "architecture": platform.machine(),
        },
        "stageMesh": {
            "packageEntries": package_entries,
            "installedExecutables": installed,
            "runningProcessCount": process_count,
            "observedVersion": detected_version,
        },
        "webview": webview,
        "appData": {
            "pathHash": "sha256:" + _sha256_bytes(str(app_data).encode("utf-8")),
            "exists": app_data.exists(),
        },
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=REQUIRED_PHASES, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--bundle-directory", type=Path)
    parser.add_argument("--installer", type=Path)
    parser.add_argument("--installed-executable", type=Path)
    parser.add_argument("--observed-installed-version")
    parser.add_argument("--clean-host-attested", action="store_true")
    parser.add_argument("--runtime-ready-observed", action="store_true")
    parser.add_argument("--persistence-marker")
    parser.add_argument("--save-restart-recovered", action="store_true")
    parser.add_argument("--previous-version")
    parser.add_argument("--upgrade-observed", action="store_true")
    parser.add_argument("--uninstall-observed", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = args.evidence.resolve()
        snapshot = collect_posix_snapshot(args.installed_executable, args.observed_installed_version)
        if args.phase == "baseline":
            if args.bundle_directory is None or args.installer is None:
                raise ValueError("baseline phase requires --bundle-directory and --installer")
            bundle = args.bundle_directory.resolve()
            try:
                output.relative_to(bundle)
            except ValueError:
                pass
            else:
                raise ValueError("evidence output must be outside the downloaded bundle")
            if output.exists():
                raise ValueError("baseline phase will not overwrite existing evidence")
            report = start_evidence(
                bundle,
                args.installer,
                snapshot,
                clean_host_attested=args.clean_host_attested,
                observed_at_utc=_utc_now(),
            )
        else:
            report = _load_object(output, "POSIX clean-host evidence")
            report = append_phase(
                report,
                args.phase,
                snapshot,
                observed_at_utc=_utc_now(),
                runtime_ready_observed=args.runtime_ready_observed,
                persistence_marker=args.persistence_marker,
                save_restart_recovered=args.save_restart_recovered,
                previous_version=args.previous_version,
                upgrade_observed=args.upgrade_observed,
                uninstall_observed=args.uninstall_observed,
            )
        payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(output)
        print(payload, end="")
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"POSIX clean-host evidence failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
