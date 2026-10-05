#!/usr/bin/env python3
"""Record the locked desktop dependency inputs without making legal claims."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
REQUIREMENT_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)$")
INPUT_PATHS = (
    "desktop/package-lock.json",
    "desktop/src-tauri/Cargo.lock",
    "requirements-desktop.txt",
)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def purl(ecosystem: str, name: str, version: str) -> str:
    return f"pkg:{ecosystem}/{quote(name, safe='/')}@{quote(version, safe='.+-')}"


def npm_components(path: Path) -> list[dict[str, str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("lockfileVersion") != 3 or not isinstance(document.get("packages"), dict):
        raise ValueError("desktop/package-lock.json must use lockfileVersion 3")
    result: list[dict[str, str]] = []
    for package_path, package in document["packages"].items():
        if not package_path or not isinstance(package, dict):
            continue
        name = package_path.rsplit("node_modules/", 1)[-1]
        version = package.get("version")
        if not name or not isinstance(version, str) or not version:
            raise ValueError(f"npm lock entry is missing a name/version: {package_path}")
        component = {
            "ecosystem": "npm",
            "name": name,
            "version": version,
            "role": "desktop-build-tool",
            "purl": purl("npm", name, version),
        }
        integrity = package.get("integrity")
        if isinstance(integrity, str) and integrity:
            component["integrity"] = integrity
        result.append(component)
    return result


def cargo_components(path: Path) -> list[dict[str, str]]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    packages = document.get("package")
    if document.get("version") != 4 or not isinstance(packages, list):
        raise ValueError("desktop/src-tauri/Cargo.lock must use lockfile version 4")
    result: list[dict[str, str]] = []
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError("Cargo.lock package entries must be objects")
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise ValueError("Cargo.lock package entry is missing a name/version")
        if name == "stagemesh-desktop" and "source" not in package:
            continue
        component = {
            "ecosystem": "cargo",
            "name": name,
            "version": version,
            "role": "desktop-application-lock",
            "purl": purl("cargo", name, version),
        }
        checksum = package.get("checksum")
        if isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum):
            component["sha256"] = checksum
        result.append(component)
    return result


def python_components(path: Path) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = REQUIREMENT_PATTERN.fullmatch(line)
        if not match:
            raise ValueError(
                f"requirements-desktop.txt:{line_number} must use an exact name==version pin"
            )
        name, version = match.groups()
        result.append({
            "ecosystem": "pypi",
            "name": name,
            "version": version,
            "role": "runtime-freezer-build-tool",
            "purl": purl("pypi", name, version),
        })
    if not result:
        raise ValueError("requirements-desktop.txt contains no pinned dependencies")
    return result


def build_inventory(root: Path, version: str, commit: str) -> dict[str, object]:
    root = root.resolve()
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("version must use MAJOR.MINOR.PATCH with an optional prerelease suffix")
    if not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("commit must be a 40-character lowercase hexadecimal SHA")
    paths = {relative: root / relative for relative in INPUT_PATHS}
    missing = [relative for relative, path in paths.items() if not path.is_file()]
    if missing:
        raise ValueError("missing desktop dependency input(s): " + ", ".join(missing))

    components = (
        npm_components(paths["desktop/package-lock.json"])
        + cargo_components(paths["desktop/src-tauri/Cargo.lock"])
        + python_components(paths["requirements-desktop.txt"])
    )
    components.sort(key=lambda item: (item["ecosystem"], item["name"].lower(), item["version"]))
    identifiers = [item["purl"] for item in components]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("dependency inputs contain duplicate package identifiers")
    counts = {
        ecosystem: sum(item["ecosystem"] == ecosystem for item in components)
        for ecosystem in ("cargo", "npm", "pypi")
    }
    return {
        "schemaVersion": 1,
        "documentType": "org.stagemesh.desktop-dependency-inventory",
        "product": "StageMesh",
        "version": version,
        "sourceCommit": commit,
        "inputs": [
            {"path": relative, "sha256": digest(paths[relative])}
            for relative in INPUT_PATHS
        ],
        "counts": {"total": len(components), **counts},
        "components": components,
        "reviewBoundary": {
            "standardSbom": False,
            "payloadInclusionVerified": False,
            "dependencyLicensesVerified": False,
            "ownerLegalReviewComplete": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    try:
        report = build_inventory(args.root, args.version, args.commit)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Recorded {report['counts']['total']} locked desktop dependency components")
    return 0


if __name__ == "__main__":
    sys.exit(main())
