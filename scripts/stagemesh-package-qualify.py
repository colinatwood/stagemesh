#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOOLS = ("systemd-sysusers", "systemd-tmpfiles", "systemd-analyze", "sh")


def _run(argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(argv)}: {detail}")
    return result


def _account_ids(root: Path) -> tuple[int, int]:
    passwd = root / "etc/passwd"
    group = root / "etc/group"
    uid = gid = None
    for line in passwd.read_text().splitlines():
        parts = line.split(":")
        if len(parts) >= 4 and parts[0] == "stagemesh":
            uid, gid = int(parts[2]), int(parts[3])
            break
    if uid is None or gid is None:
        raise RuntimeError("staged sysusers did not create the stagemesh account")
    if not any(line.split(":", 1)[0] == "stagemesh" for line in group.read_text().splitlines()):
        raise RuntimeError("staged sysusers did not create the stagemesh group")
    return uid, gid


def qualify(*, build_dir: Path) -> dict[str, Any]:
    missing = [name for name in REQUIRED_TOOLS if shutil.which(name) is None]
    if missing:
        raise RuntimeError("missing packaging qualification tools: " + ", ".join(missing))
    engine = build_dir / "native/stagemesh_engine"
    if not engine.is_file() or not os.access(engine, os.X_OK):
        raise RuntimeError("package qualification requires a built native stagemesh_engine")

    with tempfile.TemporaryDirectory(prefix="stagemesh-package-qual-") as raw:
        stage = Path(raw) / "rootfs"
        env = {**os.environ, "DESTDIR": str(stage), "PREFIX": "/usr", "STAGEMESH_BUILD_DIR": str(build_dir)}

        first = _run(["sh", str(ROOT / "scripts/install-linux.sh")], env=env)
        (stage / "etc").mkdir(parents=True, exist_ok=True)
        _run(["systemd-sysusers", f"--root={stage}", str(stage / "usr/lib/sysusers.d/stagemesh.conf")])
        _run(["systemd-tmpfiles", f"--root={stage}", "--create", str(stage / "usr/lib/tmpfiles.d/stagemesh.conf")])
        uid, gid = _account_ids(stage)

        state_dir = stage / "var/lib/stagemesh"
        info = state_dir.stat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o750:
            raise RuntimeError("staged state directory mode must be 0750")
        if (info.st_uid, info.st_gid) != (uid, gid):
            raise RuntimeError("staged state directory ownership does not match the stagemesh account")

        required = [
            stage / "usr/libexec/stagemesh/stagemesh_engine",
            stage / "usr/libexec/stagemesh/stagemesh-qualify.py",
            stage / "usr/libexec/stagemesh/stagemesh-package-qualify.py",
            stage / "usr/libexec/stagemesh/stagemesh-qualification-plan.py",
            stage / "usr/libexec/stagemesh/stagemesh-qualification-review.py",
            stage / "usr/libexec/stagemesh/stagemesh-qualification-status.py",
            stage / "usr/libexec/stagemesh/stagemesh-device-permissions.py",
            stage / "usr/share/stagemesh/backend/dev_server.py",
            stage / "usr/share/stagemesh/backend/witness_server.py",
            stage / "usr/lib/systemd/system/stagemesh.service",
            stage / "usr/lib/systemd/system/stagemesh-witness.service",
        ]
        missing_installed = [str(path.relative_to(stage)) for path in required if not path.is_file()]
        if missing_installed:
            raise RuntimeError("staged install is missing files: " + ", ".join(missing_installed))
        for notice in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            installed = stage / "usr/share/stagemesh" / notice
            if not installed.is_file() or installed.read_bytes() != (ROOT / notice).read_bytes():
                raise RuntimeError(f"installed notice missing or different: {notice}")
        if (stage / "etc/systemd/system/multi-user.target.wants").exists():
            raise RuntimeError("installer must not enable StageMesh services automatically")

        _run(["systemd-analyze", "verify", str(ROOT / "packaging/systemd/stagemesh.service"), str(ROOT / "packaging/systemd/stagemesh-witness.service")])

        sentinel = state_dir / "qualification-sentinel.json"
        sentinel.write_text('{"preserve":true}\n')
        os.chown(sentinel, uid, gid)
        before = sentinel.read_bytes()
        second = _run(["sh", str(ROOT / "scripts/install-linux.sh")], env=env)
        if sentinel.read_bytes() != before:
            raise RuntimeError("reinstall modified persistent state")

        helper = _run([sys.executable, str(stage / "usr/libexec/stagemesh/stagemesh-qualify.py")])
        try:
            helper_result = json.loads(helper.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("installed qualification helper did not emit JSON") from exc
        if not isinstance(helper_result, dict):
            raise RuntimeError("installed qualification helper response must be an object")

        uninstall_env = {**os.environ, "DESTDIR": str(stage), "PREFIX": "/usr"}
        _run(["sh", str(ROOT / "scripts/uninstall-linux.sh")], env=uninstall_env)
        if not sentinel.is_file() or sentinel.read_bytes() != before:
            raise RuntimeError("ordinary uninstall did not preserve persistent state")
        if any((stage / path).exists() for path in ("usr/share/stagemesh", "usr/libexec/stagemesh", "usr/share/stagemesh", "usr/libexec/stagemesh")):
            raise RuntimeError("ordinary uninstall left StageMesh program files behind")

        _run(["sh", str(ROOT / "scripts/uninstall-linux.sh"), "--purge-data"], env=uninstall_env)
        if state_dir.exists():
            raise RuntimeError("explicit purge did not remove persistent state")

        return {
            "qualification": "isolated-rootfs-reference",
            "cleanHostQualified": False,
            "hardwarePermissionsQualified": False,
            "install": "passed",
            "reinstallPreservedState": True,
            "sysusersProvisioned": True,
            "tmpfilesProvisioned": True,
            "stateDirectory": {"mode": "0750", "uid": uid, "gid": gid},
            "systemdUnitsVerified": 2,
            "serviceAutoEnabled": False,
            "installedHelperRan": True,
            "licenseNoticesInstalled": True,
            "uninstallPreservedState": True,
            "purgeRemovedState": True,
            "installOutput": first.stdout.strip()[-256:],
            "reinstallOutput": second.stdout.strip()[-256:],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify StageMesh Linux packaging in an isolated staged rootfs")
    parser.add_argument("--build-dir", default=os.environ.get("STAGEMESH_BUILD_DIR", os.environ.get("STAGEMESH_BUILD_DIR", str(ROOT / "build"))))
    args = parser.parse_args()
    try:
        report = qualify(build_dir=Path(args.build_dir).resolve())
    except Exception as exc:
        print(json.dumps({"qualification": "isolated-rootfs-reference", "passed": False, "error": str(exc)}))
        return 1
    report["passed"] = True
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
