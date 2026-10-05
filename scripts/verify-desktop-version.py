#!/usr/bin/env python3
"""Verify one StageMesh desktop version across manifests and an optional tag."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(
    r"^(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$"
)


def normalize_tag(tag: str) -> str:
    value = tag.strip()
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError("release tag must be vMAJOR.MINOR.PATCH with an optional prerelease suffix")
    return value[1:] if value.startswith("v") else value


def versions(root: Path) -> dict[str, str]:
    package = json.loads((root / "desktop/package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((root / "desktop/package-lock.json").read_text(encoding="utf-8"))
    tauri = json.loads((root / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    cargo = tomllib.loads((root / "desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8"))
    cargo_lock = tomllib.loads((root / "desktop/src-tauri/Cargo.lock").read_text(encoding="utf-8"))
    locked_package = next(
        (item for item in cargo_lock.get("package", []) if item.get("name") == "stagemesh-desktop"),
        None,
    )
    if locked_package is None:
        raise ValueError("Cargo.lock does not contain stagemesh-desktop")
    return {
        "package.json": str(package.get("version", "")),
        "package-lock.json": str(package_lock.get("version", "")),
        "package-lock.json root package": str(package_lock.get("packages", {}).get("", {}).get("version", "")),
        "tauri.conf.json": str(tauri.get("version", "")),
        "Cargo.toml": str(cargo.get("package", {}).get("version", "")),
        "Cargo.lock": str(locked_package.get("version", "")),
    }


def verify(root: Path, tag: str | None) -> dict[str, object]:
    found = versions(root)
    unique = set(found.values())
    if "" in unique:
        missing = sorted(name for name, value in found.items() if not value)
        raise ValueError("missing desktop version in: " + ", ".join(missing))
    if len(unique) != 1:
        detail = ", ".join(f"{name}={value}" for name, value in sorted(found.items()))
        raise ValueError("desktop versions do not match: " + detail)
    version = next(iter(unique))
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"desktop version is not valid semantic version syntax: {version}")
    if tag and normalize_tag(tag) != version:
        raise ValueError(f"release tag {tag} does not match desktop version {version}")
    return {"passed": True, "version": version, "tag": tag or None, "manifests": found}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""))
    args = parser.parse_args()
    try:
        result = verify(args.root.resolve(), args.tag or None)
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
