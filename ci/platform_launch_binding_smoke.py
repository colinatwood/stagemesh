#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def windows_smoke() -> dict:
    import platform_launch_binding as binding

    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidates = [system_root / "System32" / "whoami.exe", system_root / "System32" / "where.exe", system_root / "System32" / "cmd.exe"]
    chosen = None; signature = None
    for candidate in candidates:
        if not candidate.is_file(): continue
        try: evidence = binding._windows_authenticode_evidence(candidate)
        except Exception: continue
        if evidence.get("signatureStatus") == "Valid" and evidence.get("publisherCertificateSha256"):
            chosen = candidate; signature = evidence; break
    if chosen is None or signature is None: raise RuntimeError("no valid signed Windows system executable was available as a launch-binding fixture")
    digest = sha256_file(chosen)
    process, evidence = binding.windows_verify_and_launch(chosen, (), expected_adapter_sha256="sha256:" + digest, expected_publisher_certificate_sha256="sha256:" + signature["publisherCertificateSha256"])
    exit_code = process.wait(timeout=15)
    if exit_code != 0: raise RuntimeError(f"bound Windows fixture exited with {exit_code}")
    return {"qualified":True,"fixtureName":chosen.name,"binding":evidence["binding"],"adapterSha256":evidence["adapterSha256"],"publisherCertificateSha256":evidence["publisherCertificateSha256"],"fileIdentityPresent":bool(evidence.get("volumeSerial") and evidence.get("fileId")),"exitCode":exit_code,"physicalOutputsArmed":False}


def macos_smoke() -> dict:
    import platform_launch_binding as binding

    candidates = [
        (Path("/usr/bin/xcrun"), ("--find", "true")),
        (Path("/usr/bin/true"), ()),
        (Path("/usr/bin/whoami"), ()),
        (Path("/usr/bin/security"), ("help",)),
    ]
    chosen = None; chosen_args = (); signature = None; fallback = None
    for candidate, args in candidates:
        if not candidate.is_file(): continue
        try: evidence = binding._codesign_evidence(candidate)
        except Exception: continue
        if not evidence.get("codeDirectoryHash"): continue
        if fallback is None: fallback = (candidate, args, evidence)
        if evidence.get("teamId"):
            chosen, chosen_args, signature = candidate, args, evidence
            break
    if chosen is None and fallback is not None: chosen, chosen_args, signature = fallback
    if chosen is None or signature is None: raise RuntimeError("no signed macOS system executable was available as a launch-binding fixture")
    digest = sha256_file(chosen)
    process, evidence = binding.macos_verify_and_launch(chosen, chosen_args, expected_adapter_sha256="sha256:" + digest, expected_team_id=signature["teamId"] or None, expected_code_directory_hash="cdhash:" + signature["codeDirectoryHash"])
    exit_code = process.wait(timeout=15)
    if exit_code != 0: raise RuntimeError(f"bound macOS fixture exited with {exit_code}")
    return {"qualified":True,"fixtureName":chosen.name,"fixtureArgs":list(chosen_args),"binding":evidence["binding"],"adapterSha256":evidence["adapterSha256"],"teamId":evidence.get("teamId") or None,"teamIdChecked":bool(signature.get("teamId")),"codeDirectoryHash":evidence["codeDirectoryHash"],"fileIdentityPresent":bool(evidence.get("fileId")),"privateStagedCopyVerified":bool(evidence.get("privateStagedCopyVerified")),"exitCode":exit_code,"physicalOutputsArmed":False}


def main() -> int:
    host = platform.system()
    report = {"documentType":"org.upp.platform-launch-binding-smoke","schemaVersion":2,"host":{"os":host,"release":platform.release(),"architecture":platform.machine()},"gitHubSource":{"sha":os.environ.get("GITHUB_SHA"),"headRef":os.environ.get("GITHUB_HEAD_REF")},"physicalOutputsArmed":False,"physicalHardwareQualified":False,"pluginCompatibilityQualified":False,"checks":{}}
    if host == "Windows": report["checks"]["nativeLaunchBinding"] = windows_smoke()
    elif host == "Darwin": report["checks"]["nativeLaunchBinding"] = macos_smoke()
    else: report["checks"]["nativeLaunchBinding"] = {"qualified":False,"reason":"Linux uses the existing procfd binder"}
    out = Path(os.environ.get("STAGEMESH_LAUNCH_EVIDENCE", "platform-launch-binding-smoke.json"))
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8")); return 0


if __name__ == "__main__": raise SystemExit(main())
