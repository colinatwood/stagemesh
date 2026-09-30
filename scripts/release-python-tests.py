#!/usr/bin/env python3
"""Require a selected engine and make skipped tests visible to release review."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

def main():
    engine = os.environ.get("STAGEMESH_NATIVE_ENGINE", "")
    if not engine or not Path(engine).is_file():
        print("Release tests require STAGEMESH_NATIVE_ENGINE pointing to a built engine", file=sys.stderr)
        return 1
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    for test, reason in result.skipped:
        print(f"RELEASE SKIP: {test.id()}: {reason}", file=sys.stderr)
    # A passing suite with skipped coverage is not a release pass.
    return 0 if result.wasSuccessful() and not result.skipped else 1

if __name__ == "__main__":
    sys.exit(main())
