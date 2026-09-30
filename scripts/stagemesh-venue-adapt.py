#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from adaptation import build_transaction
from compatibility import migrate_show_state, show_requirements_from_snapshot
from venue import venue_compatibility_plan


def load_json(path: Path):
    return json.loads(path.read_text("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an offline UPP venue adaptation transaction preview")
    parser.add_argument("show_state", type=Path)
    parser.add_argument("venue_profile", type=Path)
    parser.add_argument("--discovery", type=Path, help="optional discovered-device JSON array")
    parser.add_argument("--output", "-o", type=Path, help="write transaction JSON instead of stdout")
    parser.add_argument("--require-ready", action="store_true", help="exit nonzero unless the transaction has no blockers")
    args = parser.parse_args()

    show_raw = load_json(args.show_state)
    show, migration = migrate_show_state(show_raw)
    venue = load_json(args.venue_profile)
    discovered = load_json(args.discovery) if args.discovery else None
    requirements = show_requirements_from_snapshot(show)
    plan = venue_compatibility_plan(venue, requirements, discovered_devices=discovered)
    tx = build_transaction(plan, requirements, use_local_discovery=args.discovery is not None)
    tx["offlinePreview"] = True
    tx["showMigration"] = migration
    text = json.dumps(tx, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, "utf-8")
    else:
        sys.stdout.write(text)
    if args.require_ready and (tx.get("blockers") or plan.get("readiness") != "ready"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
