#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from compatibility import migrate_show_state, show_requirements_from_snapshot
from venue import venue_compatibility_plan


def read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read {path}: {exc}")
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan UPP show compatibility against a StageMesh venue profile")
    parser.add_argument("show", type=Path, help="show-state JSON")
    parser.add_argument("venue", type=Path, help="venue-profile JSON (.stagevenue content)")
    parser.add_argument("--discovery", type=Path, help="optional discovered-device JSON object/array")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args()

    show, _ = migrate_show_state(read_object(args.show))
    venue = read_object(args.venue)
    discovered = None
    if args.discovery:
        raw = json.loads(args.discovery.read_text("utf-8"))
        discovered = raw.get("devices") if isinstance(raw, dict) else raw
        if not isinstance(discovered, list):
            raise SystemExit("discovery JSON must be an array or an object containing a devices array")

    plan = venue_compatibility_plan(venue, show_requirements_from_snapshot(show), discovered_devices=discovered)
    print(json.dumps(plan, indent=None if args.compact else 2, sort_keys=True, ensure_ascii=False))
    return 0 if plan.get("compatible") else 2


if __name__ == "__main__":
    raise SystemExit(main())
