from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DOCUMENT_TYPE_PLAN="org.upp.external-qualification-plan"
DOCUMENT_TYPE_RESULT="org.upp.external-qualification-result"
SCHEMA_VERSION=1

_TASKS=(
    {"taskId":"independent-witness","backlogIds":["REC-033","REC-034","SEC-039"],"environment":"three independently hosted witnesses plus primary/standby nodes","command":"stageforge-witness-qualify.py","requiredClaims":["physicalIndependenceQualified","twoOfThreeSurvivesOneWitnessLoss","oneOfThreeDenied","clockSkewWithinBound","recoveredNodeRemainsStandbyDisarmed"],"requiredArtifacts":["qualification-report","topology-inventory","clock-evidence"]},
    {"taskId":"lan-security","backlogIds":["SEC-040"],"environment":"deployed TLS reverse proxy, IdP/auth proxy and venue/control LAN firewall","command":"stageforge-http-qualify.py","requiredClaims":["trustedCertificateQualified","hostOriginBoundaryQualified","idpIdentityQualified","firewallIngressQualified","controllerLoadQualified"],"requiredArtifacts":["qualification-report","tls-certificate-chain","firewall-policy"]},
    {"taskId":"linux-packaging-host","backlogIds":["PKG-033","PKG-034"],"environment":"fresh Linux host or VM with representative audio/MIDI/device access","command":"stageforge-package-qualify.py","requiredClaims":["cleanHostQualified","serviceBootQualified","upgradeStatePreserved","hardwarePermissionsQualified","uninstallPreservesState","purgeRemovesState"],"requiredArtifacts":["qualification-report","package-manifest","service-evidence"]},
    {"taskId":"windows-platform","backlogIds":["AUD-035","DEV-033","IPC-033","PLUG-034","PLUG-035"],"environment":"supported Windows host with audio/MIDI hardware and plugin fixtures","command":None,"requiredClaims":["audioNegotiationQualified","playbackLifecycleQualified","hotplugLifecycleQualified","namedPipeDaclQualified","pluginLaunchBindingQualified"],"requiredArtifacts":["qualification-report","platform-observation","playback-evidence","security-evidence"]},
    {"taskId":"macos-platform","backlogIds":["AUD-036","DEV-034","PLUG-034","PLUG-036"],"environment":"supported macOS host with audio/MIDI hardware and plugin fixtures","command":None,"requiredClaims":["audioNegotiationQualified","playbackLifecycleQualified","hotplugLifecycleQualified","pluginLaunchBindingQualified"],"requiredArtifacts":["qualification-report","platform-observation","playback-evidence","security-evidence"]},
    {"taskId":"assistive-technology","backlogIds":["UX-035"],"environment":"real operator browser plus selected screen reader/keyboard AT stack","command":None,"requiredClaims":["keyboardWorkflowQualified","screenReaderWorkflowQualified","statusAnnouncementsQualified"],"requiredArtifacts":["qualification-report","at-transcript"]},
    {"taskId":"licensed-plugin-matrix","backlogIds":["PLUG-033","PLUG-037","PLUG-038"],"environment":"licensed real plugin fixtures on every claimed OS/architecture","command":None,"requiredClaims":["fixtureLicensesReviewed","loadControlAudioRestartMatrixQualified","delayCompensationQualified","failureBypassQualified"],"requiredArtifacts":["qualification-report","fixture-inventory","compatibility-matrix"]},
    {"taskId":"stage-hardware","backlogIds":["AUD-034","DEV-035","LIVE-033","HW-033","HW-034","HW-035","HW-036","HW-037"],"environment":"named production hardware and rehearsal topology","command":"stageforge-qualify.py","requiredClaims":["latencySoakQualified","audibleRecordingLoopQualified","controllerTimingQualified","rfClockQualified","failoverTimingQualified"],"requiredArtifacts":["qualification-report","hardware-inventory","measurement-summary"]},
)

_FINGERPRINT_ROOTS=("backend","frontend","native","schemas","scripts","packaging")
_FINGERPRINT_FILES=("CMakeLists.txt","requirements-release.txt")


def _sha256_file(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(65536),b""):digest.update(chunk)
    return "sha256:"+digest.hexdigest()


def source_fingerprint(root:Path)->str:
    root=root.resolve();digest=hashlib.sha256()
    files:list[Path]=[]
    for name in _FINGERPRINT_ROOTS:
        base=root/name
        if base.is_dir():files.extend(path for path in base.rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix!=".pyc")
    for name in _FINGERPRINT_FILES:
        path=root/name
        if path.is_file():files.append(path)
    for path in sorted(set(files),key=lambda item:item.relative_to(root).as_posix()):
        rel=path.relative_to(root).as_posix().encode();payload=path.read_bytes()
        digest.update(len(rel).to_bytes(4,"big"));digest.update(rel);digest.update(len(payload).to_bytes(8,"big"));digest.update(payload)
    return "sha256:"+digest.hexdigest()


def create_plan(*,root:Path,engine_path:Path)->dict[str,Any]:
    if not engine_path.is_file():raise ValueError("qualification plan requires a built native engine")
    build={"sourceFingerprint":source_fingerprint(root),"nativeEngineSha256":_sha256_file(engine_path)}
    plan={"documentType":DOCUMENT_TYPE_PLAN,"schemaVersion":SCHEMA_VERSION,"build":build,"tasks":[dict(task) for task in _TASKS],"physicalOutputsArmed":False}
    canonical=json.dumps(plan,separators=(",",":"),sort_keys=True).encode()
    return {**plan,"planId":"sha256:"+hashlib.sha256(canonical).hexdigest()}


def result_template(plan:dict[str,Any],task_id:str)->dict[str,Any]:
    task=next((item for item in plan.get("tasks",[]) if item.get("taskId")==task_id),None)
    if task is None:raise ValueError("unknown qualification task")
    artifacts=[{"kind":kind,"name":kind,"relativePath":f"replace-me-{kind}.json","sha256":"sha256:"+"0"*64,"sizeBytes":0} for kind in task["requiredArtifacts"]]
    return {"documentType":DOCUMENT_TYPE_RESULT,"schemaVersion":SCHEMA_VERSION,"planId":plan["planId"],"taskId":task_id,"build":dict(plan["build"]),"runner":{"runnerIdHash":"sha256:"+"0"*64,"platform":"replace-me"},"passed":False,"claims":{name:False for name in task["requiredClaims"]},"artifacts":artifacts,"notes":[],"physicalOutputsArmed":False}


def validate_result(plan:dict[str,Any],result:dict[str,Any])->dict[str,Any]:
    if result.get("documentType")!=DOCUMENT_TYPE_RESULT or result.get("schemaVersion")!=SCHEMA_VERSION:raise ValueError("invalid qualification result document")
    if result.get("planId")!=plan.get("planId") or result.get("build")!=plan.get("build"):raise ValueError("qualification result does not match this exact build plan")
    task_id=str(result.get("taskId", ""));task=next((item for item in plan.get("tasks",[]) if item.get("taskId")==task_id),None)
    if task is None:raise ValueError("unknown qualification result task")
    runner=result.get("runner")
    if not isinstance(runner,dict) or not str(runner.get("platform","")).strip():raise ValueError("qualification result requires runner platform")
    runner_hash=str(runner.get("runnerIdHash","")).lower()
    if len(runner_hash)!=71 or not runner_hash.startswith("sha256:") or any(ch not in "0123456789abcdef" for ch in runner_hash[7:]):raise ValueError("qualification result requires hashed runner identity")
    if result.get("physicalOutputsArmed") is not False:raise ValueError("qualification result envelope must not arm physical outputs")
    claims=result.get("claims")
    if not isinstance(claims,dict):raise ValueError("qualification result requires claims")
    required=list(task["requiredClaims"]);missing=[name for name in required if type(claims.get(name)) is not bool]
    if missing:raise ValueError("qualification result is missing boolean claims: "+", ".join(missing))
    passed=result.get("passed") is True
    if passed and any(claims[name] is not True for name in required):raise ValueError("passing qualification result requires every task claim to be true")
    artifacts=result.get("artifacts",[])
    if not isinstance(artifacts,list) or len(artifacts)>64:raise ValueError("qualification result artifacts must be a bounded list")
    artifact_kinds=[];artifact_paths=[]
    for item in artifacts:
        if not isinstance(item,dict) or not str(item.get("name","")).strip():raise ValueError("qualification artifact requires a name")
        kind=str(item.get("kind","")).strip();relative=str(item.get("relativePath","")).strip()
        if not kind or len(kind)>128 or any(ord(ch)<33 or ord(ch)>126 for ch in kind):raise ValueError("qualification artifact requires a bounded kind")
        path=Path(relative)
        if not relative or len(relative)>512 or path.is_absolute() or ".." in path.parts or relative in {".",".."}:raise ValueError("qualification artifact requires a safe relative path")
        digest=str(item.get("sha256","")).lower()
        if len(digest)!=71 or not digest.startswith("sha256:") or any(ch not in "0123456789abcdef" for ch in digest[7:]):raise ValueError("qualification artifact requires sha256")
        size=item.get("sizeBytes")
        if type(size) is not int or size<0 or size>2**63-1:raise ValueError("qualification artifact requires sizeBytes")
        artifact_kinds.append(kind);artifact_paths.append(relative)
    if len(artifact_paths)!=len(set(artifact_paths)):raise ValueError("qualification artifact paths must be unique")
    required_artifacts=list(task["requiredArtifacts"])
    if passed:
        missing_artifacts=[kind for kind in required_artifacts if kind not in artifact_kinds]
        if missing_artifacts:raise ValueError("passing qualification result is missing required artifacts: "+", ".join(missing_artifacts))
    return {"accepted":True,"passed":passed,"taskId":task_id,"backlogIds":list(task["backlogIds"]),"build":dict(plan["build"]),"requiredClaims":required,"requiredArtifacts":required_artifacts,"claims":{name:claims[name] for name in required},"physicalOutputsArmed":False}
