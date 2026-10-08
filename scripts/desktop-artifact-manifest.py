#!/usr/bin/env python3
"""Write deterministic checksums and metadata for desktop installer artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


MANIFEST_NAME = "desktop-artifacts.json"
CHECKSUM_NAME = "SHA256SUMS"
SIGNING_VERIFICATION_NAME = "signing-verification.json"
# The verification report binds to this manifest, so including that report in
# the manifest would create a self-referential checksum cycle. Keep all three
# release-metadata sidecars outside the packaged-file inventory.
EXCLUDED_NAMES = frozenset({MANIFEST_NAME, CHECKSUM_NAME, SIGNING_VERIFICATION_NAME})
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def inventory(root: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.name in EXCLUDED_NAMES:
            continue
        relative = path.relative_to(root).as_posix()
        files.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        })
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--platform", required=True)
    parser.add_argument(
        "--distribution-channel",
        choices=("standard", "online", "offline"),
        default="standard",
    )
    parser.add_argument("--commit", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    root = args.directory.resolve()
    if not root.is_dir():
        parser.error(f"artifact directory does not exist: {root}")
    files = inventory(root)
    if not files:
        parser.error(f"artifact directory contains no files: {root}")
    if not VERSION_PATTERN.fullmatch(args.version):
        parser.error("version must use MAJOR.MINOR.PATCH with an optional prerelease suffix")
    if args.platform == "Windows" and args.distribution_channel not in {"online", "offline"}:
        parser.error("Windows artifacts require the online or offline distribution channel")
    if args.platform != "Windows" and args.distribution_channel != "standard":
        parser.error("only Windows artifacts may use online or offline distribution channels")

    manifest = {
        "schemaVersion": 1,
        "product": "StageMesh",
        "version": args.version,
        "platform": args.platform,
        "distributionChannel": args.distribution_channel,
        "sourceCommit": args.commit,
        "signed": False,
        "qualification": {
            "softwarePackageBuilt": True,
            "cleanHostInstallQualified": False,
            "physicalHardwareQualified": False,
        },
        "files": files,
    }
    (root / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / CHECKSUM_NAME).write_text(
        "".join(f"{item['sha256']}  {item['path']}\n" for item in files),
        encoding="utf-8",
    )
    print(f"Recorded {len(files)} desktop artifact files in {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
