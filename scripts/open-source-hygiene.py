#!/usr/bin/env python3
"""Fail closed when StageMesh's public contribution and security files drift."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 1024 * 1024
RETIRED_NAMES = ("stage" + "forge",)
REQUIRED_TEXT = {
    "README.md": (
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "SUPPORT.md",
    ),
    "CONTRIBUTING.md": (
        "Apache License 2.0",
        "python scripts/release-check.py",
        "physical qualification",
        "SECURITY.md",
    ),
    "SECURITY.md": (
        "Supported versions",
        "security/advisories/new",
        "Do not disclose",
        "pre-1.0",
    ),
    "CODE_OF_CONDUCT.md": (
        "Expected behavior",
        "Enforcement",
        "privately",
    ),
    "SUPPORT.md": (
        "no guaranteed support",
        "SECURITY.md",
        "physical-hardware compatibility",
    ),
    ".github/ISSUE_TEMPLATE/bug_report.md": (
        "name: Bug report",
        "## Reproduction",
        "## Qualification boundary",
        "SECURITY.md",
    ),
    ".github/ISSUE_TEMPLATE/feature_request.md": (
        "name: Feature request",
        "## Problem",
        "## Boundaries and dependencies",
        "proprietary SDK",
    ),
    ".github/pull_request_template.md": (
        "## Test evidence",
        "## Boundary review",
        "No credentials",
        "fail closed",
    ),
}


def _read_text(root: Path, relative: str) -> tuple[str | None, str | None]:
    path = root / relative
    if not path.is_file() or path.is_symlink():
        return None, f"{relative} must be a regular file"
    if path.stat().st_size > MAX_TEXT_BYTES:
        return None, f"{relative} exceeds the 1 MiB policy limit"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{relative} is not readable UTF-8 text: {exc}"
    if not text.strip():
        return None, f"{relative} must not be empty"
    return text, None


def validate(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    documents: dict[str, str] = {}
    for relative, tokens in REQUIRED_TEXT.items():
        text, error = _read_text(root, relative)
        if error:
            errors.append(error)
            continue
        assert text is not None
        documents[relative] = text
        for token in tokens:
            if token not in text:
                errors.append(f"{relative} is missing required text: {token}")

    license_text, license_error = _read_text(root, "LICENSE")
    if license_error:
        errors.append(license_error)
    elif (
        "Apache License" not in license_text
        or "Version 2.0, January 2004" not in license_text
        or "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" not in license_text
    ):
        errors.append("LICENSE must contain the complete Apache License 2.0 identity")

    for relative, text in documents.items():
        lowered = text.lower()
        for retired in RETIRED_NAMES:
            if retired in lowered:
                errors.append(f"{relative} contains retired project name: {retired}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    errors = validate(args.root)
    if errors:
        for error in errors:
            print(f"Open-source hygiene failed: {error}", file=sys.stderr)
        return 2
    print(f"Open-source hygiene passed ({len(REQUIRED_TEXT) + 1} required files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
