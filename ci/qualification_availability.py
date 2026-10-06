"""Read-only availability inventory. Never requests microphone access or captures audio."""
import json
import os
from pathlib import Path
import platform
import subprocess

report = {
    "documentType": "org.upp.qualification-availability", "schemaVersion": 1,
    "githubRunId": os.environ.get("GITHUB_RUN_ID"),
    "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "hostOs": platform.system(),
    "microphoneAccessRequested": False, "audioCaptured": False,
    "physicalHardwareQualified": False,
}
if platform.system() == "Darwin":
    code = r'''
import AVFoundation
switch AVCaptureDevice.authorizationStatus(for: .audio) {
case .authorized: print("authorized")
case .denied: print("denied")
case .restricted: print("restricted")
case .notDetermined: print("not-determined")
@unknown default: print("unknown")
}
'''
    result = subprocess.run(["swift", "-e", code], capture_output=True, text=True, timeout=90)
    report["microphoneAuthorization"] = result.stdout.strip() if result.returncode == 0 else "probe-failed"
    if result.returncode:
        report["probeError"] = result.stderr[-2000:]
else:
    report["microphoneAuthorization"] = "not-probed-on-this-platform"
if platform.system() == "Darwin" and os.environ.get("GITHUB_ENV"):
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env:
        env.write("STAGEMESH_HOSTED_CAPTURE_AUTHORIZED=" +
                  ("1" if report["microphoneAuthorization"] == "authorized" else "0") + "\n")
Path("qualification-availability.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
