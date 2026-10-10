#!/usr/bin/env python3
"""Check software-only desktop release readiness without making release claims.

This gate validates the inputs that can be checked in source/CI. It deliberately
does not sign, notarize, approve a license, or convert clean-host or hardware
evidence into a qualification claim.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION_SCRIPT = Path(__file__).with_name("verify-desktop-version.py")
SBOM_SCRIPT = Path(__file__).with_name("desktop-sbom.py")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_DISTRIBUTION_FILES = ("LICENSE", "THIRD_PARTY_NOTICES.md")

WINDOWS_WEBVIEW_INSTALL_MODES = {
    "offline": "offlineInstaller",
    "online": "downloadBootstrapper",
}
REQUIRED_DESKTOP_CSP = {
    "default-src": "'self' customprotocol: asset:",
    "connect-src": "ipc: http://ipc.localhost",
    "font-src": "'self'",
    "img-src": "'self' asset: http://asset.localhost blob: data:",
    "object-src": "'none'",
    "script-src": "'self'",
    "style-src": "'self' 'unsafe-inline'",
}


def _windows_webview_install_mode(
    root: Path, expected: str = "offlineInstaller"
) -> tuple[str | None, str | None]:
    config_path = root / "desktop" / "src-tauri" / "tauri.conf.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"Windows WebView2 installer configuration is invalid: {exc}"
    bundle = config.get("bundle") if isinstance(config, dict) else None
    windows = bundle.get("windows") if isinstance(bundle, dict) else None
    mode = windows.get("webviewInstallMode") if isinstance(windows, dict) else None
    mode = mode.get("type") if isinstance(mode, dict) else None
    if mode != expected:
        return mode, (
            f"Windows WebView2 installation must use {expected} "
            f"(found {mode!r})"
        )
    return mode, None


def _desktop_webview_security(root: Path) -> tuple[dict[str, bool], str | None]:
    config_path = root / "desktop" / "src-tauri" / "tauri.conf.json"
    report = {
        "globalTauriApiDisabled": False,
        "bundledContentSecurityPolicyConfigured": False,
        "remoteDomainIpcAccessDisabled": False,
    }
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return report, f"desktop WebView security configuration is invalid: {exc}"
    app = config.get("app") if isinstance(config, dict) else None
    if not isinstance(app, dict):
        return report, "desktop WebView app configuration must be an object"
    if app.get("withGlobalTauri") is not False:
        return report, "desktop WebView must keep the global Tauri API disabled"
    report["globalTauriApiDisabled"] = True
    security = app.get("security")
    if not isinstance(security, dict):
        return report, "desktop WebView security configuration must be an object"
    remote_ipc = security.get("dangerousRemoteDomainIpcAccess")
    if remote_ipc not in (None, []):
        return report, "desktop WebView must not grant remote-domain IPC access"
    report["remoteDomainIpcAccessDisabled"] = True
    csp = security.get("csp")
    if csp != REQUIRED_DESKTOP_CSP:
        return report, "desktop bundled-content CSP does not match the least-authority policy"
    report["bundledContentSecurityPolicyConfigured"] = True
    return report, None


DEPENDENCY_INVENTORY_NAME = "desktop-dependencies.json"
SBOM_NAME = "desktop-sbom.cdx.json"
REQUIRED_DEPENDENCY_INPUTS = {
    "desktop/package-lock.json",
    "desktop/src-tauri/Cargo.lock",
    "requirements-desktop.txt",
}


def _sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def version_module():
    spec = importlib.util.spec_from_file_location("verify_desktop_version", VERSION_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load version verifier: {VERSION_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sbom_module():
    spec = importlib.util.spec_from_file_location("desktop_sbom", SBOM_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load desktop SBOM generator: {SBOM_SCRIPT}")
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
    channel = manifest.get("distributionChannel")
    expected_channels = {"online", "offline"} if platform == "Windows" else {"standard"}
    if channel not in expected_channels:
        expected = "online or offline" if platform == "Windows" else "standard"
        return f"artifact manifest distributionChannel must be {expected} for {platform}"
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


def _dependency_inventory_error(inventory: dict[str, Any], version: str) -> str | None:
    if inventory.get("schemaVersion") != 1:
        return "dependency inventory schemaVersion must be 1"
    if inventory.get("documentType") != "org.stagemesh.desktop-dependency-inventory":
        return "dependency inventory documentType is invalid"
    if inventory.get("product") != "StageMesh":
        return "dependency inventory product must be StageMesh"
    if inventory.get("version") != version:
        return f"dependency inventory version {inventory.get('version')!r} does not match {version}"
    commit = inventory.get("sourceCommit")
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        return "dependency inventory sourceCommit must be a 40-character lowercase commit"
    inputs = inventory.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return "dependency inventory inputs must be a non-empty list"
    input_paths: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict):
            return "dependency inventory input entries must be objects"
        path = item.get("path")
        path_parts = Path(path).parts if isinstance(path, str) else ()
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in path_parts:
            return "dependency inventory input paths must be safe relative paths"
        if not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            return f"dependency inventory input SHA-256 is invalid for {path}"
        input_paths.add(path)
    if input_paths != REQUIRED_DEPENDENCY_INPUTS or len(inputs) != len(input_paths):
        return "dependency inventory must contain each required lock input exactly once"
    components = inventory.get("components")
    if not isinstance(components, list) or not components:
        return "dependency inventory components must be a non-empty list"
    purls: list[str] = []
    ecosystems: list[str] = []
    for item in components:
        if not isinstance(item, dict):
            return "dependency inventory component entries must be objects"
        for field in ("ecosystem", "name", "version", "role", "purl"):
            if not isinstance(item.get(field), str) or not item[field]:
                return f"dependency inventory component {field} is missing"
        purls.append(item["purl"])
        ecosystems.append(item["ecosystem"])
    if any(name not in {"cargo", "npm", "pypi"} for name in ecosystems):
        return "dependency inventory component ecosystem is invalid"
    if len(purls) != len(set(purls)):
        return "dependency inventory package identifiers must be unique"
    counts = inventory.get("counts")
    expected_counts = {
        "total": len(components),
        **{name: ecosystems.count(name) for name in ("cargo", "npm", "pypi")},
    }
    if not isinstance(counts, dict) or any(counts.get(name) != value for name, value in expected_counts.items()):
        return "dependency inventory counts do not match components"
    boundary = inventory.get("reviewBoundary")
    required_false = (
        "standardSbom",
        "payloadInclusionVerified",
        "dependencyLicensesVerified",
        "ownerLegalReviewComplete",
    )
    if not isinstance(boundary, dict) or any(boundary.get(name) is not False for name in required_false):
        return "dependency inventory cannot claim SBOM, payload, license, or legal review completion"
    return None


def _dependency_manifest_binding_error(
    inventory_path: Path,
    inventory: dict[str, Any],
    manifest_path: Path,
    manifest: dict[str, Any],
) -> str | None:
    try:
        relative = inventory_path.resolve().relative_to(manifest_path.resolve().parent).as_posix()
    except ValueError:
        return "dependency inventory must be inside the artifact manifest directory"
    if relative != DEPENDENCY_INVENTORY_NAME:
        return f"dependency inventory must be named {DEPENDENCY_INVENTORY_NAME}"
    entries = [
        item for item in manifest.get("files", [])
        if isinstance(item, dict) and item.get("path") == relative
    ]
    if len(entries) != 1:
        return "artifact manifest must contain exactly one dependency inventory entry"
    entry = entries[0]
    if entry.get("bytes") != inventory_path.stat().st_size or entry.get("sha256") != _sha256(inventory_path):
        return "artifact manifest dependency inventory digest does not match"
    if inventory.get("sourceCommit") != manifest.get("sourceCommit"):
        return "dependency inventory sourceCommit does not match artifact manifest"
    return None


def _sbom_error(
    sbom: dict[str, Any],
    inventory_path: Path,
    version: str,
    source_commit: str,
) -> str | None:
    if sbom.get("$schema") != "https://cyclonedx.org/schema/bom-1.7.schema.json":
        return "desktop SBOM schema must be CycloneDX 1.7 JSON"
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.7":
        return "desktop SBOM format/specVersion must be CycloneDX 1.7"
    if sbom.get("version") != 1:
        return "desktop SBOM document version must be 1"
    metadata = sbom.get("metadata")
    component = metadata.get("component") if isinstance(metadata, dict) else None
    if not isinstance(component, dict):
        return "desktop SBOM metadata component is missing"
    if (
        component.get("type") != "application"
        or component.get("name") != "StageMesh"
        or component.get("version") != version
        or component.get("purl") != f"pkg:generic/stagemesh@{version}"
    ):
        return "desktop SBOM product identity does not match the release"
    properties = component.get("properties")
    if not isinstance(properties, list):
        return "desktop SBOM review-boundary properties are missing"
    property_map: dict[str, str] = {}
    for item in properties:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("value"), str)
            or item["name"] in property_map
        ):
            return "desktop SBOM review-boundary properties are invalid"
        property_map[item["name"]] = item["value"]
    required = {
        "org.stagemesh:sourceCommit": source_commit,
        "org.stagemesh:dependencyInventorySha256": _sha256(inventory_path),
        "org.stagemesh:dependencyInventoryBytes": str(inventory_path.stat().st_size),
        "org.stagemesh:payloadInclusionVerified": "false",
        "org.stagemesh:dependencyLicensesVerified": "false",
        "org.stagemesh:ownerLegalReviewComplete": "false",
    }
    if property_map != required:
        return "desktop SBOM inventory binding or review boundary is invalid"
    expected = sbom_module().build_sbom(inventory_path)
    if sbom != expected:
        return "desktop SBOM does not match the deterministic locked-inventory projection"
    return None


def _sbom_manifest_binding_error(
    sbom_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> str | None:
    try:
        relative = sbom_path.resolve().relative_to(manifest_path.resolve().parent).as_posix()
    except ValueError:
        return "desktop SBOM must be inside the artifact manifest directory"
    if relative != SBOM_NAME:
        return f"desktop SBOM must be named {SBOM_NAME}"
    entries = [
        item for item in manifest.get("files", [])
        if isinstance(item, dict) and item.get("path") == relative
    ]
    if len(entries) != 1:
        return "artifact manifest must contain exactly one desktop SBOM entry"
    entry = entries[0]
    if entry.get("bytes") != sbom_path.stat().st_size or entry.get("sha256") != _sha256(sbom_path):
        return "artifact manifest desktop SBOM digest does not match"
    return None


def evaluate(
    root: Path,
    tag: str | None = None,
    manifest_path: Path | None = None,
    dependency_inventory_path: Path | None = None,
    sbom_path: Path | None = None,
) -> dict[str, Any]:
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
    manifest_document: dict[str, Any] | None = None
    if manifest_path is not None:
        path = manifest_path.resolve()
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("artifact manifest must be a JSON object")
            manifest_document = manifest
            manifest_report = {
                "path": str(path),
                "signed": manifest.get("signed"),
                "platform": manifest.get("platform"),
                "distributionChannel": manifest.get("distributionChannel"),
                "sourceCommit": manifest.get("sourceCommit"),
            }
            if version_report is not None:
                error = _manifest_error(manifest, str(version_report["version"]))
                if error:
                    blockers.append(error)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            blockers.append(f"artifact manifest check failed: {exc}")

    expected_webview_mode = "offlineInstaller"
    if (
        manifest_document is not None
        and manifest_document.get("platform") == "Windows"
        and manifest_document.get("distributionChannel") in WINDOWS_WEBVIEW_INSTALL_MODES
    ):
        expected_webview_mode = WINDOWS_WEBVIEW_INSTALL_MODES[
            str(manifest_document["distributionChannel"])
        ]
    windows_webview_mode, windows_webview_error = _windows_webview_install_mode(
        root, expected_webview_mode
    )
    if windows_webview_error:
        blockers.append(windows_webview_error)

    desktop_webview_security, desktop_webview_error = _desktop_webview_security(root)
    if desktop_webview_error:
        blockers.append(desktop_webview_error)

    dependency_report: dict[str, Any] | None = None
    inventory_document: dict[str, Any] | None = None
    if manifest_path is not None and dependency_inventory_path is None:
        blockers.append("artifact readiness requires a dependency inventory")
    if dependency_inventory_path is not None:
        inventory_path = dependency_inventory_path.resolve()
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            if not isinstance(inventory, dict):
                raise ValueError("dependency inventory must be a JSON object")
            inventory_document = inventory
            dependency_report = {
                "path": str(inventory_path),
                "sourceCommit": inventory.get("sourceCommit"),
                "componentCount": inventory.get("counts", {}).get("total")
                if isinstance(inventory.get("counts"), dict) else None,
                "manifestBound": False,
            }
            if version_report is not None:
                error = _dependency_inventory_error(inventory, str(version_report["version"]))
                if error:
                    blockers.append(error)
            if manifest_path is not None and manifest_document is not None:
                binding_error = _dependency_manifest_binding_error(
                    inventory_path, inventory, manifest_path, manifest_document
                )
                if binding_error:
                    blockers.append(binding_error)
                else:
                    dependency_report["manifestBound"] = True
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            blockers.append(f"dependency inventory check failed: {exc}")

    sbom_report: dict[str, Any] | None = None
    if manifest_path is not None and sbom_path is None:
        blockers.append("artifact readiness requires a CycloneDX desktop SBOM")
    if sbom_path is not None and dependency_inventory_path is None:
        blockers.append("desktop SBOM validation requires the dependency inventory")
    if sbom_path is not None:
        resolved_sbom = sbom_path.resolve()
        try:
            sbom = json.loads(resolved_sbom.read_text(encoding="utf-8"))
            if not isinstance(sbom, dict):
                raise ValueError("desktop SBOM must be a JSON object")
            sbom_report = {
                "path": str(resolved_sbom),
                "format": sbom.get("bomFormat"),
                "specVersion": sbom.get("specVersion"),
                "componentCount": len(sbom.get("components", []))
                if isinstance(sbom.get("components"), list) else None,
                "inventoryBound": False,
                "manifestBound": False,
            }
            if (
                version_report is not None
                and manifest_document is not None
                and dependency_inventory_path is not None
                and inventory_document is not None
            ):
                error = _sbom_error(
                    sbom,
                    dependency_inventory_path.resolve(),
                    str(version_report["version"]),
                    str(manifest_document.get("sourceCommit", "")),
                )
                if error:
                    blockers.append(error)
                else:
                    sbom_report["inventoryBound"] = True
                binding_error = _sbom_manifest_binding_error(
                    resolved_sbom, manifest_path, manifest_document
                )
                if binding_error:
                    blockers.append(binding_error)
                else:
                    sbom_report["manifestBound"] = True
        except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
            blockers.append(f"desktop SBOM check failed: {exc}")

    passed = not blockers
    return {
        "schemaVersion": 1,
        "passed": passed,
        "version": version_report.get("version") if version_report else None,
        "tag": tag,
        "manifests": version_report.get("manifests") if version_report else None,
        "distributionFilesPresent": not missing,
        "windowsWebViewInstallMode": windows_webview_mode,
        "desktopWebviewSecurity": desktop_webview_security,
        "artifactManifest": manifest_report,
        "dependencyInventory": dependency_report,
        "sbom": sbom_report,
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
    parser.add_argument("--dependency-inventory", type=Path)
    parser.add_argument("--sbom", type=Path)
    args = parser.parse_args()
    report = evaluate(
        args.root,
        args.tag or None,
        args.manifest,
        args.dependency_inventory,
        args.sbom,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
