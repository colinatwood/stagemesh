"""Durable, conservative ownership evidence for crash-visible temporary resources.

Version 2 manifests bind one process identity to one exact filesystem object.  Any
legacy, malformed, missing, replaced or otherwise unverifiable resource is
classified as unknown and is never automatically reclaimed.
"""
from __future__ import annotations

import json
import os
import platform
import stat
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = 2
MANIFEST_DOCUMENT_TYPE = "org.stageforge.temporary-resource-owner"


def process_identity(pid: int | None = None) -> dict[str, Any]:
    pid = os.getpid() if pid is None else int(pid)
    result: dict[str, Any] = {"pid": pid}
    if platform.system() == "Darwin":
        try:
            def ps(field: str) -> str:
                completed = subprocess.run(
                    ["ps", "-p", str(pid), "-o", f"{field}="],
                    check=True, capture_output=True, text=True,
                )
                value = completed.stdout.strip()
                if not value:
                    raise ValueError(f"missing ps field: {field}")
                return value
            boot = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            started = datetime.strptime(ps("lstart"), "%a %b %d %H:%M:%S %Y")
            result.update({
                "bootId": boot,
                "processStartTicks": int(started.timestamp()),
            })
            return result
        except (OSError, ValueError, subprocess.SubprocessError):
            # Without an exact process-generation identity cleanup remains
            # conservative. Creation still succeeds; liveness is unknown.
            return result
    try:
        result["bootId"] = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        result["processStartTicks"] = int(Path(f"/proc/{pid}/stat").read_text().split()[21])
    except (OSError, ValueError, IndexError):
        # Without an exact process-generation identity cleanup must remain
        # conservative. Creation still succeeds; later liveness is unknown.
        pass
    return result

