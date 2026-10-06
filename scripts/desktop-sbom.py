#!/usr/bin/env python3
"""Convert the locked desktop dependency inventory to CycloneDX 1.7 JSON.

The SBOM describes declared lockfile components.  It does not claim that every
component is shipped in every installer or that licenses/legal approval have
been reviewed.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
import uuid


BOM_FORMAT = "CycloneDX"
SPEC_VERSION = "1.7"
SCHEMA_URL = "https://cyclonedx.org/schema/bom-1.7.schema.json"
INVENTORY_DOCUMENT_TYPE = "org.stagemesh.desktop-dependency-inventory"
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_JSON_BYTES = 10 * 1024 * 1024
BOUNDARY_PROPERTIES = {
    "org.stagemesh:payloadInclusionVerified": "false",
    "org.stagemesh:dependencyLicensesVerified": "false",
    "org.stagemesh:ownerLegalReviewComplete": "false",
}
INTEGRITY_ALGORITHMS = {
    "sha256": ("SHA-256", 32),
    "sha384": ("SHA-384", 48),
    "sha512": ("SHA-512", 64),
}


def _sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _load_inventory(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("desktop dependency inventory is missing")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("desktop dependency inventory exceeds the 10 MiB input limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("desktop dependency inventory is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("desktop dependency inventory must be a JSON object")
    return value


def _properties(values: dict[str, str]) -> list[dict[str, str]]:
    return [{"name": name, "value": value} for name, value in sorted(values.items())]


def _integrity_hash(value: str) -> dict[str, str]:
    algorithm, separator, encoded = value.partition("-")
    if not separator or algorithm not in INTEGRITY_ALGORITHMS or not encoded:
        raise ValueError("npm integrity must use SHA-256, SHA-384, or SHA-512 SRI")
    label, expected_bytes = INTEGRITY_ALGORITHMS[algorithm]
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("npm integrity is not valid base64") from exc
    if len(decoded) != expected_bytes:
        raise ValueError("npm integrity digest length does not match its algorithm")
    return {"alg": label, "content": decoded.hex()}


def _validate_inventory(inventory: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    if (
        inventory.get("schemaVersion") != 1
        or inventory.get("documentType") != INVENTORY_DOCUMENT_TYPE
        or inventory.get("product") != "StageMesh"
    ):
        raise ValueError("desktop dependency inventory identity is invalid")
    version = inventory.get("version")
    commit = inventory.get("sourceCommit")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("desktop dependency inventory version is invalid")
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("desktop dependency inventory source commit is invalid")
    boundary = inventory.get("reviewBoundary")
    if (
        not isinstance(boundary, dict)
        or boundary.get("standardSbom") is not False
        or boundary.get("payloadInclusionVerified") is not False
        or boundary.get("dependencyLicensesVerified") is not False
        or boundary.get("ownerLegalReviewComplete") is not False
    ):
        raise ValueError("desktop dependency inventory review boundary is invalid")
    components = inventory.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("desktop dependency inventory components are missing")
    counts = inventory.get("counts")
    if not isinstance(counts, dict) or counts.get("total") != len(components):
        raise ValueError("desktop dependency inventory component count is invalid")
    purls: set[str] = set()
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("desktop dependency inventory component is invalid")
        for field in ("ecosystem", "name", "version", "role", "purl"):
            if not isinstance(component.get(field), str) or not component[field]:
                raise ValueError(f"desktop dependency inventory component {field} is invalid")
        if component["ecosystem"] not in {"cargo", "npm", "pypi"}:
            raise ValueError("desktop dependency inventory component ecosystem is invalid")
        if component["purl"] in purls:
            raise ValueError("desktop dependency inventory contains duplicate package identifiers")
        purls.add(component["purl"])
    return version, commit, components


def build_sbom(inventory_path: Path) -> dict[str, Any]:
    inventory_path = Path(inventory_path)
    inventory = _load_inventory(inventory_path)
    version, commit, inventory_components = _validate_inventory(inventory)
    inventory_digest = _sha256(inventory_path)
    product_ref = f"pkg:generic/stagemesh@{version}"

    components: list[dict[str, Any]] = []
    for source in inventory_components:
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": source["purl"],
            "name": source["name"],
            "version": source["version"],
            "purl": source["purl"],
            "properties": _properties({
                "org.stagemesh:ecosystem": source["ecosystem"],
                "org.stagemesh:role": source["role"],
            }),
        }
        hashes: list[dict[str, str]] = []
        checksum = source.get("sha256")
        if checksum is not None:
            if not isinstance(checksum, str) or not SHA256_PATTERN.fullmatch(checksum):
                raise ValueError(f"invalid SHA-256 for {source['purl']}")
            hashes.append({"alg": "SHA-256", "content": checksum})
        integrity = source.get("integrity")
        if integrity is not None:
            if not isinstance(integrity, str):
                raise ValueError(f"invalid npm integrity for {source['purl']}")
            hashes.append(_integrity_hash(integrity))
        if hashes:
            component["hashes"] = hashes
        components.append(component)

    root_properties = {
        "org.stagemesh:sourceCommit": commit,
        "org.stagemesh:dependencyInventorySha256": inventory_digest,
        "org.stagemesh:dependencyInventoryBytes": str(inventory_path.stat().st_size),
        **BOUNDARY_PROPERTIES,
    }
    serial = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"https://stagemesh.org/sbom/{version}/{commit}/{inventory_digest}",
    )
    component_refs = [component["bom-ref"] for component in components]
    return {
        "$schema": SCHEMA_URL,
        "bomFormat": BOM_FORMAT,
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": product_ref,
                "name": "StageMesh",
                "version": version,
                "purl": product_ref,
                "properties": _properties(root_properties),
            },
        },
        "components": components,
        "dependencies": [
            {"ref": product_ref, "dependsOn": component_refs},
            *({"ref": reference, "dependsOn": []} for reference in component_refs),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        source = args.inventory.resolve()
        output = args.output.resolve()
        if source == output:
            raise ValueError("SBOM output must not overwrite the dependency inventory")
        report = build_sbom(source)
        payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(output)
        print(f"Recorded {len(report['components'])} CycloneDX desktop components")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Desktop SBOM generation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
