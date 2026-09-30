#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from compatibility import inspect_show_state, migrate_show_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or migrate StageMesh/UPP show-state JSON without launching StageMesh.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--inspect", action="store_true", help="print compatibility status only")
    args = parser.parse_args()

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    report = inspect_show_state(data)
    if args.inspect:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report.get("readable") else 3

    if not report.get("readable"):
        print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)
        return 3
    normalized, migration = migrate_show_state(data)
    payload = json.dumps(normalized, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    print(json.dumps({"ok": True, "report": migration}, sort_keys=True), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
