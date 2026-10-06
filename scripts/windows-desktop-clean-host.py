#!/usr/bin/env python3
"""Collect exact-candidate Windows desktop clean-host evidence.

The report is an evidence envelope for later review.  It deliberately never
sets clean-host or hardware qualification to true.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
from typing import Any


DOCUMENT_TYPE = "org.stagemesh.windows-desktop-clean-host-evidence"
MANIFEST_NAME = "desktop-artifacts.json"
REQUIRED_PHASES = ("baseline", "installed", "restarted", "upgraded", "uninstalled")
MAX_JSON_BYTES = 5 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


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


def _candidate(bundle: Path, installer: Path) -> dict[str, Any]:
    root = bundle.resolve()
    manifest_path = root / MANIFEST_NAME
    manifest = _load_object(manifest_path, "desktop artifact manifest")
    if manifest.get("product") != "StageMesh" or manifest.get("platform") != "Windows":
        raise ValueError("clean-host evidence requires a Windows StageMesh bundle")
    version = manifest.get("version")
    commit = manifest.get("sourceCommit")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("artifact manifest version is invalid")
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("artifact manifest source commit is invalid")
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
    if selected.suffix.lower() not in {".exe", ".msi"}:
        raise ValueError("Windows installer must be an NSIS .exe or MSI package")
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
        "version": version,
        "sourceCommit": commit,
        "manifest": {
            "bytes": manifest_path.stat().st_size,
            "sha256": _sha256_file(manifest_path),
        },
        "installer": {
            "name": selected.name,
            "format": selected.suffix.lower().lstrip("."),
            "bytes": actual_size,
            "sha256": actual_digest,
        },
    }


def _valid_runner(snapshot: dict[str, Any]) -> None:
    runner_hash = snapshot.get("runnerIdHash")
    os_info = snapshot.get("os")
    if not isinstance(runner_hash, str) or not runner_hash.startswith("sha256:") or not SHA256_PATTERN.fullmatch(runner_hash[7:]):
        raise ValueError("snapshot requires a SHA-256 runner identity")
    if not isinstance(os_info, dict):
        raise ValueError("snapshot requires Windows OS metadata")
    if not str(os_info.get("productName", "")).startswith("Windows 11"):
        raise ValueError("clean-host evidence requires Windows 11")
    if os_info.get("architecture") not in {"AMD64", "x86_64"}:
        raise ValueError("clean-host evidence requires Windows 11 x64")
    build = os_info.get("buildNumber")
    if type(build) is not int or build < 22000:
        raise ValueError("Windows build is not a supported Windows 11 build")


def _stagemesh_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    state = snapshot.get("stageMesh")
    if not isinstance(state, dict):
        raise ValueError("snapshot requires StageMesh installation state")
    for name in ("uninstallEntries", "installedExecutables"):
        if not isinstance(state.get(name), list):
            raise ValueError(f"snapshot StageMesh state requires {name}")
    if type(state.get("runningProcessCount")) is not int or state["runningProcessCount"] < 0:
        raise ValueError("snapshot StageMesh process count is invalid")
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
    _valid_runner(snapshot)
    state = _stagemesh_state(snapshot)
    candidate = _candidate(bundle, installer)
    clean = not state["uninstallEntries"] and not state["installedExecutables"] and state["runningProcessCount"] == 0
    phase = {
        "phase": "baseline",
        "observedAtUtc": observed_at_utc,
        "passed": bool(clean_host_attested and clean),
        "checks": {
            "cleanHostAttested": bool(clean_host_attested),
            "noStageMeshUninstallEntry": not state["uninstallEntries"],
            "noStageMeshExecutableDetected": not state["installedExecutables"],
            "noStageMeshProcessRunning": state["runningProcessCount"] == 0,
            "windows11X64": True,
        },
    }
    report = {
        "documentType": DOCUMENT_TYPE,
        "schemaVersion": 1,
        "product": "StageMesh",
        "candidate": candidate,
        "runner": {
            "runnerIdHash": snapshot["runnerIdHash"],
            "os": snapshot["os"],
        },
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
        raise ValueError("invalid Windows clean-host evidence document")
    if phase == "baseline" or phase not in REQUIRED_PHASES:
        raise ValueError("invalid append phase")
    _valid_runner(snapshot)
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
    target = report.get("candidate", {}).get("version")
    installed_versions = sorted({
        str(item.get("displayVersion", ""))
        for item in state["uninstallEntries"]
        if isinstance(item, dict) and str(item.get("displayVersion", ""))
    })
    installed = bool(state["uninstallEntries"]) and bool(state["installedExecutables"])
    version_matches = target in installed_versions
    webview = snapshot.get("webView2")
    webview_detected = isinstance(webview, dict) and webview.get("detected") is True
    marker = _marker_hash(persistence_marker)
    checks: dict[str, Any]

    if phase == "installed":
        checks = {
            "installerRegistrationDetected": bool(state["uninstallEntries"]),
            "installedExecutableDetected": bool(state["installedExecutables"]),
            "installedVersionMatchesCandidate": version_matches,
            "webView2Detected": webview_detected,
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
            "installerRegistrationRemoved": not state["uninstallEntries"],
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
        entry["installedVersions"] = installed_versions
    report["phases"].append(entry)
    _summarize(report)
    return report


def _registry_values(winreg: Any, hive: Any, path: str, view: int) -> dict[str, Any] | None:
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view) as key:
            values: dict[str, Any] = {}
            for index in range(winreg.QueryInfoKey(key)[1]):
                name, value, _ = winreg.EnumValue(key, index)
                values[name] = value
            return values
    except OSError:
        return None


def _registry_children(winreg: Any, hive: Any, path: str, view: int) -> list[str]:
    try:
        with winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view) as key:
            return [winreg.EnumKey(key, index) for index in range(winreg.QueryInfoKey(key)[0])]
    except OSError:
        return []


def collect_windows_snapshot() -> dict[str, Any]:
    if sys.platform != "win32":
        raise RuntimeError("live clean-host collection must run on Windows")
    import winreg

    current = _registry_values(winreg, winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", winreg.KEY_WOW64_64KEY) or {}
    machine = _registry_values(winreg, winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", winreg.KEY_WOW64_64KEY) or {}
    whoami = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True)
    sid_rows = list(csv.reader(whoami.stdout.splitlines()))
    if not sid_rows or len(sid_rows[0]) < 2:
        raise RuntimeError("could not read the current Windows user SID")
    identity = f"{machine.get('MachineGuid', '')}\0{sid_rows[0][1]}".encode("utf-8")

    uninstall_entries: list[dict[str, str]] = []
    views = (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY)
    uninstall_root = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    raw_locations: list[str] = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in views:
            for child in _registry_children(winreg, hive, uninstall_root, view):
                values = _registry_values(winreg, hive, uninstall_root + "\\" + child, view) or {}
                display_name = str(values.get("DisplayName", ""))
                if not display_name.lower().startswith("stagemesh"):
                    continue
                uninstall_entries.append({
                    "displayName": display_name,
                    "displayVersion": str(values.get("DisplayVersion", "")),
                    "publisher": str(values.get("Publisher", "")),
                })
                raw_locations.extend([str(values.get("InstallLocation", "")), str(values.get("DisplayIcon", ""))])

    candidates = [
        Path(location.strip().split(",", 1)[0].strip().strip('"'))
        for location in raw_locations if location.strip()
    ]
    candidates.extend([
        Path(os.environ.get("LOCALAPPDATA", "")) / "StageMesh" / "StageMesh.exe",
        Path(os.environ.get("ProgramFiles", "")) / "StageMesh" / "StageMesh.exe",
    ])
    executables: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate.is_dir():
            candidate = candidate / "StageMesh.exe"
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        executables.append({
            "pathHash": "sha256:" + _sha256_bytes(str(resolved).lower().encode("utf-8")),
            "bytes": resolved.stat().st_size,
            "sha256": _sha256_file(resolved),
        })

    webview_versions: set[str] = set()
    clients_root = r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in views:
            for child in _registry_children(winreg, hive, clients_root, view):
                values = _registry_values(winreg, hive, clients_root + "\\" + child, view) or {}
                if "webview" in str(values.get("name", "")).lower():
                    version = str(values.get("pv", "")).strip()
                    if version:
                        webview_versions.add(version)

    tasklist = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True)
    process_count = sum(
        1 for row in csv.reader(tasklist.stdout.splitlines())
        if row and row[0].lower() in {"stagemesh.exe", "stagemesh-runtime.exe", "stagemesh_engine.exe"}
    )
    app_data = Path(os.environ.get("APPDATA", "")) / "org.stagemesh.desktop"
    build_text = str(current.get("CurrentBuildNumber", "0"))
    return {
        "runnerIdHash": "sha256:" + _sha256_bytes(identity),
        "os": {
            "productName": str(current.get("ProductName", platform.platform())).replace("Windows 10", "Windows 11")
            if int(build_text or "0") >= 22000 else str(current.get("ProductName", platform.platform())),
            "displayVersion": str(current.get("DisplayVersion", "")),
            "buildNumber": int(build_text or "0"),
            "architecture": os.environ.get("PROCESSOR_ARCHITECTURE", platform.machine()),
        },
        "stageMesh": {
            "uninstallEntries": uninstall_entries,
            "installedExecutables": executables,
            "runningProcessCount": process_count,
        },
        "webView2": {
            "detected": bool(webview_versions),
            "versions": sorted(webview_versions),
        },
        "appData": {
            "pathHash": "sha256:" + _sha256_bytes(str(app_data).lower().encode("utf-8")),
            "exists": app_data.exists(),
        },
    }


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=REQUIRED_PHASES, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--bundle-directory", type=Path)
    parser.add_argument("--installer", type=Path)
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
        snapshot = collect_windows_snapshot()
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
            report = _load_object(output, "Windows clean-host evidence")
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
        print(f"Windows clean-host evidence failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
