#!/usr/bin/env python3
"""Validate and summarize the authoritative StageMesh backlog workbook."""

import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT / "docs/backlog/StageMesh-Master-Backlog-Checkpoint-84.xlsx"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
REQUIRED_COLUMNS = ("ID", "Work Item", "Priority", "Status", "Phase", "Type")
ALLOWED_STATUSES = ("Done", "In Progress", "Blocked", "Deferred")


class BacklogError(RuntimeError):
    """Raised when the workbook cannot be treated as authoritative."""


def _xml(archive, name):
    try:
        return ET.fromstring(archive.read(name))
    except KeyError as exc:
        raise BacklogError(f"Workbook is missing {name}") from exc
    except ET.ParseError as exc:
        raise BacklogError(f"Workbook XML is invalid: {name}") from exc


def _shared_strings(archive):
    try:
        root = _xml(archive, "xl/sharedStrings.xml")
    except BacklogError as exc:
        if "is missing" in str(exc):
            return []
        raise
    return ["".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
            for item in root.findall(f"{{{MAIN_NS}}}si")]


def _sheet_path(archive, sheet_name):
    workbook = _xml(archive, "xl/workbook.xml")
    relation_id = None
    for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        if sheet.get("name") == sheet_name:
            relation_id = sheet.get(f"{{{REL_NS}}}id")
            break
    if not relation_id:
        raise BacklogError(f"Workbook has no {sheet_name!r} worksheet")
    relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
    for relation in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship"):
        if relation.get("Id") == relation_id:
            target = relation.get("Target", "")
            return target.lstrip("/") if target.startswith("/") else str(PurePosixPath("xl") / target)
    raise BacklogError(f"Workbook has no relationship for {sheet_name!r}")


def _column_index(reference):
    match = re.match(r"([A-Z]+)", reference or "")
    if not match:
        raise BacklogError(f"Invalid cell reference: {reference!r}")
    result = 0
    for character in match.group(1):
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def _cell_text(cell, shared_strings):
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value = cell.find(f"{{{MAIN_NS}}}v")
    if value is None or value.text is None:
        return ""
    if kind == "s":
        try:
            return shared_strings[int(value.text)]
        except (IndexError, ValueError) as exc:
            raise BacklogError("Workbook contains an invalid shared-string reference") from exc
    return value.text


def load_backlog(path):
    path = Path(path)
    if not path.is_file():
        raise BacklogError(f"Backlog workbook not found: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            shared_strings = _shared_strings(archive)
            worksheet = _xml(archive, _sheet_path(archive, "Backlog"))
    except zipfile.BadZipFile as exc:
        raise BacklogError(f"Backlog workbook is not a valid XLSX file: {path}") from exc
    rows = []
    for row in worksheet.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
        values = {_column_index(cell.get("r")): _cell_text(cell, shared_strings).strip()
                  for cell in row.findall(f"{{{MAIN_NS}}}c")}
        if values:
            rows.append([values.get(index, "") for index in range(max(values) + 1)])
    if not rows:
        raise BacklogError("Backlog worksheet is empty")
    headers = rows[0]
    missing = [name for name in REQUIRED_COLUMNS if name not in headers]
    if missing:
        raise BacklogError("Backlog worksheet is missing columns: " + ", ".join(missing))
    records = []
    for values in rows[1:]:
        record = {header: values[index] if index < len(values) else ""
                  for index, header in enumerate(headers) if header}
        if any(record.values()):
            records.append(record)
    validate(records)
    return records


def validate(records):
    if not records:
        raise BacklogError("Backlog contains no work items")
    identifiers = [record.get("ID", "").strip() for record in records]
    missing_ids = [str(index + 2) for index, value in enumerate(identifiers) if not value]
    if missing_ids:
        raise BacklogError("Backlog rows have no ID: " + ", ".join(missing_ids))
    duplicates = sorted(item for item, count in Counter(identifiers).items() if count > 1)
    if duplicates:
        raise BacklogError("Backlog contains duplicate IDs: " + ", ".join(duplicates))
    unknown = sorted({record.get("Status", "") for record in records} - set(ALLOWED_STATUSES))
    if unknown:
        raise BacklogError("Backlog contains unsupported statuses: " + ", ".join(repr(item) for item in unknown))


def summarize(records, workbook):
    open_items = [record for record in records if record["Status"] != "Done"]
    status_counts = Counter(record["Status"] for record in records)
    return {
        "documentType": "org.stagemesh.backlog-status",
        "schemaVersion": 1,
        "sourceWorkbook": Path(workbook).name,
        "totalItems": len(records),
        "openItems": len(open_items),
        "statusCounts": {status: status_counts.get(status, 0) for status in ALLOWED_STATUSES},
        "openByPriority": dict(sorted(Counter(record["Priority"] for record in open_items).items())),
        "openByType": dict(sorted(Counter(record["Type"] for record in open_items).items())),
        "items": [{key: record.get(key, "") for key in REQUIRED_COLUMNS} for record in open_items],
        "qualificationBoundary": (
            "This inventory reports backlog state only. It does not qualify hardware, installed packages, "
            "assistive technology, signing, legal approval, deployed services, or audible quality."
        ),
    }


def as_markdown(report):
    lines = ["# StageMesh backlog status", "", f"Source: `{report['sourceWorkbook']}`", "",
             f"{report['totalItems']} total items; {report['openItems']} remain open.", "",
             "| Status | Count |", "|---|---:|"]
    lines.extend(f"| {status} | {count} |" for status, count in report["statusCounts"].items())
    lines.extend(["", "## Open items", "", "| ID | Priority | Status | Type | Work item |", "|---|---|---|---|---|"])
    for item in report["items"]:
        safe = {key: value.replace("|", "\\|").replace("\n", " ") for key, value in item.items()}
        lines.append(f"| {safe['ID']} | {safe['Priority']} | {safe['Status']} | {safe['Type']} | {safe['Work Item']} |")
    lines.extend(["", f"> {report['qualificationBoundary']}", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = summarize(load_backlog(args.workbook), args.workbook)
        content = json.dumps(report, indent=2, sort_keys=True) + "\n" if args.format == "json" else as_markdown(report)
        if args.output:
            args.output.write_text(content, encoding="utf-8")
        else:
            print(content, end="")
        return 0
    except (BacklogError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
