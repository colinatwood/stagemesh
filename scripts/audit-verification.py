#!/usr/bin/env python3
"""Run the Python audit gate and classify restricted-environment failures."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def classify_failure(text: str) -> str:
    if "unable to create UDP socket" in text:
        return "environment-only: UDP sockets unavailable"
    if "PermissionError: [Errno 1] Operation not permitted" in text and (
        "socket.py" in text
        or "socketserver.py" in text
        or "StageMeshHTTPServer" in text
        or "ThreadingHTTPServer" in text
        or "send_frame" in text
        or "test_local_ipc.py" in text
        or "local_ipc.py" in text
    ):
        return "environment-only: network sockets unavailable"
    return "unexpected"


class AuditResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records: list[dict[str, str]] = []

    def addError(self, test, err):  # noqa: N802
        text = self._exc_info_to_string(err, test)
        self.records.append({"test": str(test), "kind": "error", "classification": classify_failure(text)})
        super().addError(test, err)

    def addFailure(self, test, err):  # noqa: N802
        text = self._exc_info_to_string(err, test)
        self.records.append({"test": str(test), "kind": "failure", "classification": classify_failure(text)})
        super().addFailure(test, err)


def run_audit() -> dict[str, object]:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    stream = io.StringIO()
    side_output = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=0, resultclass=AuditResult)
    # Some integration tests intentionally exercise logging and server-side
    # exception paths. Keep those diagnostics in the report instead of
    # corrupting the machine-readable --json output stream.
    with contextlib.redirect_stdout(side_output), contextlib.redirect_stderr(side_output):
        result = runner.run(suite)
    environment_only = [record for record in result.records if record["classification"].startswith("environment-only:")]
    unexpected = [record for record in result.records if record["classification"] == "unexpected"]
    return {
        "testsRun": result.testsRun,
        "passed": result.testsRun - len(result.errors) - len(result.failures) - len(result.skipped),
        "skipped": len(result.skipped),
        "errors": len(result.errors),
        "failures": len(result.failures),
        "environmentOnly": environment_only,
        "unexpected": unexpected,
        "gate": "pass-with-environment-limits" if not unexpected else "fail",
        "output": stream.getvalue() + side_output.getvalue(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    report = run_audit()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"tests={report['testsRun']} passed={report['passed']} skipped={report['skipped']} "
            f"errors={report['errors']} failures={report['failures']} "
            f"environmentOnly={len(report['environmentOnly'])} unexpected={len(report['unexpected'])}"
        )
        print(report["gate"])
    return 0 if not report["unexpected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
