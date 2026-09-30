"""Run the native lifecycle check and bind evidence to source and executable."""
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
    "documentType": "org.upp.device-lifecycle-smoke",
    "schemaVersion": 2,
    "host": {"os": platform.system(), "release": platform.release(), "architecture": platform.machine()},
    "sourceCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "githubRunId": os.environ.get("GITHUB_RUN_ID"),
    "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    "sourceSha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted((root / "native").glob("*")) if p.is_file()},
    "physicalOutputsArmed": False,
    "physicalHardwareQualified": False,
    "audioStreamingQualified": False,
    "physicalHotplugQualified": False,
    "status": "failed",
}
try:
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30, check=True)
    checks = json.loads(run.stdout)
    report["nativeChecks"] = checks
    if not all(checks.get(key) is True for key in ["identityAssuranceDowngradeRejected", "weakDuplicatesRemainAmbiguous"]):
        raise RuntimeError("Identity assurance regression evidence missing")
    if not checks.get("nativeMidiEnumerationAvailable") or not checks.get("midiNotificationsRegistered"):
        if os.environ.get("STAGEFORGE_ALLOW_UNAVAILABLE_NATIVE_MIDI") != "1":
            raise RuntimeError("Native MIDI enumeration and notification registration are required")
        report["status"] = "unavailable"
        report["qualificationNote"] = "Hosted runner did not expose a native MIDI notification source"
    else:
        report["persistentIdentityReconciliationQualified"] = checks.get("identityReconciliationQualified") is True
        if platform.system() == "Darwin":
            report["nativeSoftwareEventDeliveryQualified"] = (
                checks.get("coreAudioNotificationObserved") is True
                and checks.get("coreMidiNotificationObserved") is True
            )
            report["macosIdentityRecoveryQualified"] = (
                checks.get("coreAudioIdentityRecoveryQualified") is True
                and checks.get("coreMidiIdentityRecoveryQualified") is True
            )
        else:
            report["nativeSoftwareEventDeliveryQualified"] = False
            report["macosIdentityRecoveryQualified"] = False
        report["status"] = "passed"
finally:
    Path("device-lifecycle-evidence.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
