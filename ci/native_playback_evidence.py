"""Hosted silent endpoint playback; missing endpoints are reported, never passed as live I/O."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
binary = Path(sys.argv[1]).resolve()
report = {
    "documentType": "org.upp.native-playback-smoke", "schemaVersion": 1,
    "host": {"os": platform.system(), "release": platform.release(), "architecture": platform.machine()},
    "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "githubRunId": os.environ.get("GITHUB_RUN_ID"),
    "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    "sourceSha256": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted((root / "native").glob("*")) if p.is_file()},
    "physicalHardwareQualified": False, "audibleOutputQualified": False,
    "captureQualified": False, "fullEngineIntegrated": False, "status": "failed",
}
try:
    result = subprocess.run([str(binary)], capture_output=True, text=True, check=True, timeout=30)
    checks = json.loads(result.stdout)
    report["nativeChecks"] = checks
    for key in ["contractPassed", "missingPinnedEndpointRejected", "ownerThreadEnforced", "silentTestOnly"]:
        if checks.get(key) is not True:
            raise RuntimeError(f"missing required check: {key}")
    if checks["endpointPresent"]:
        for key in ["nativeCallbacksObserved", "nativeStopDrained", "explicitRestartObserved", "nonExactConfigurationRejected"]:
            if checks.get(key) is not True:
                raise RuntimeError(f"missing live endpoint check: {key}")
        if checks["callbacks"] < 16 or checks["frames"] <= 0:
            raise RuntimeError("insufficient live callback evidence")
        if platform.system() == "Darwin" and checks.get("nativeTopologyStoppedStream") is not True:
            raise RuntimeError("native software topology did not stop active stream")
        if platform.system() == "Darwin" and checks.get("singleExplicitRearmAfterNativeEvent") is not True:
            raise RuntimeError("single explicit rearm did not restart native stream after topology invalidation")
    elif any(checks[k] for k in ["nativeCallbacksObserved", "nativeStopDrained", "explicitRestartObserved", "callbacks", "frames"]):
        raise RuntimeError("live I/O claim without endpoint")
    report["status"] = "passed"
except Exception as error:
    report["error"] = str(error)
    if "selected CoreAudio identity absent" in str(error) and platform.system() == "Darwin":
        report["status"] = "unavailable"
        report["unavailableReason"] = "hosted runner has no matching default CoreAudio output identity"
        print(json.dumps(report, indent=2))
        raise SystemExit(0)
    if isinstance(error, subprocess.CalledProcessError):
        report["stderr"] = error.stderr[-8000:]
    raise
finally:
    Path("native-playback-evidence.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
