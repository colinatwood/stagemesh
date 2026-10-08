#!/usr/bin/env python3
"""Configure the Windows WebView2 installer mode for a distribution channel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("desktop/src-tauri/tauri.conf.json")
CHANNEL_MODES = {
    "offline": "offlineInstaller",
    "online": "downloadBootstrapper",
}


def configure(root: Path, channel: str) -> str:
    """Set and return the exact Tauri WebView2 mode for ``channel``."""
    if channel not in CHANNEL_MODES:
        raise ValueError("Windows distribution channel must be online or offline")
    path = root.resolve() / CONFIG
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        mode = document["bundle"]["windows"]["webviewInstallMode"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Windows Tauri configuration is invalid: {exc}") from exc
    if not isinstance(mode, dict) or set(mode) != {"type"}:
        raise ValueError("Windows webviewInstallMode must contain exactly the type field")
    expected = CHANNEL_MODES[channel]
    mode["type"] = expected
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--channel", choices=sorted(CHANNEL_MODES), required=True)
    args = parser.parse_args()
    try:
        mode = configure(args.root, args.channel)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Configured Windows {args.channel} channel with {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
