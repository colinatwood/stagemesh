from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import weakref
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from staged_resources import _process_identity
from temporary_ownership import classify_owner,create_owner_manifest,fsync_directory,recheck_reclaimable

FORMATS={"vst3","clap","lv2","audio-unit","builtin"}
_HOSTS:weakref.WeakSet=weakref.WeakSet();_HOSTS_LOCK=threading.Lock()

def plugin_host_audit_status()->list[dict[str,Any]]:
    with _HOSTS_LOCK:hosts=list(_HOSTS)
    return [host.status() for host in hosts]

def _scratch_root(*,create=True)->Path|None:
    root=Path(os.environ.get("STAGEFORGE_PLUGIN_SCRATCH_DIR","").strip() or (Path(tempfile.gettempdir())/"stageforge-plugin-host-scratch"))
    if not root.exists():
        if not create:return None
        root.mkdir(mode=0o700,parents=True,exist_ok=True)
    info=root.lstat()
    if root.is_symlink() or info.st_uid!=os.getuid() or info.st_mode&0o077:raise RuntimeError("plugin scratch root must be private and owned by the service user")
    return root.resolve()

def _tree_size(root:Path)->int:
    total=0
    for item in root.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():total+=item.stat().st_size
        except OSError:pass
    return total

def _scratch_limit()->int:
    raw=os.environ.get("STAGEFORGE_PLUGIN_SCRATCH_MAX_BYTES",str(512*1024**2))
    try:maximum=int(raw)
    except ValueError:raise RuntimeError("STAGEFORGE_PLUGIN_SCRATCH_MAX_BYTES must be an integer number of bytes") from None
    if maximum<1024*1024:raise RuntimeError("STAGEFORGE_PLUGIN_SCRATCH_MAX_BYTES must be at least 1048576 bytes")
    return maximum

def plugin_host_scratch_status()->dict[str,Any]:
    root=_scratch_root(create=False);entries=[];counts={"live":0,"reclaimable":0,"unknown-owner":0};observed=0;directories=[] if root is None else [item for item in sorted(root.glob("host-*")) if item.is_dir() and not item.is_symlink()]
    for directory in directories:
        state,owner=classify_owner(directory/"owner.json",directory,resource_class="plugin-host-scratch");counts[state]+=1;size=_tree_size(directory);observed+=size
        created=owner.get("createdAtUnixMs") if isinstance(owner,dict) and type(owner.get("createdAtUnixMs")) is int else None
        if len(entries)<128:entries.append({"resourceId":"plugin-"+hashlib.sha256(directory.name.encode()).hexdigest()[:20],"resourceClass":"plugin-host-scratch","state":state,"observedBytes":size,"ageMs":max(0,int(time.time()*1000)-created) if created is not None else None,"purpose":"isolated-effect-host"})
    maximum=_scratch_limit()
    return {"resourceCount":len(directories),"liveCount":counts["live"],"reclaimableCount":counts["reclaimable"],"unknownOwnerCount":counts["unknown-owner"],"observedBytes":observed,"configuredMaximumBytes":maximum,"overBudget":observed>maximum,"resources":entries,"scanTruncated":len(directories)>128}

def plugin_host_scratch_cleanup()->dict[str,Any]:
    root=_scratch_root(create=False);reclaimed=[]
    if root is None:return {**plugin_host_scratch_status(),"reclaimedCount":0,"reclaimedResourceIds":[]}
    for directory in sorted(root.glob("host-*")):
        if not directory.is_dir() or directory.is_symlink():continue
        if recheck_reclaimable(directory/"owner.json",directory,resource_class="plugin-host-scratch") is None:continue
        resource_id="plugin-"+hashlib.sha256(directory.name.encode()).hexdigest()[:20]
        try:shutil.rmtree(directory)
        except FileNotFoundError:continue
        reclaimed.append(resource_id)
    return {**plugin_host_scratch_status(),"reclaimedCount":len(reclaimed),"reclaimedResourceIds":reclaimed[:128]}


def _hash_fd(fd:int)->str:
    digest=hashlib.sha256();os.lseek(fd,0,os.SEEK_SET)
    while True:
        chunk=os.read(fd,65536)
        if not chunk:break
        digest.update(chunk)
    os.lseek(fd,0,os.SEEK_SET)
    return "sha256:"+digest.hexdigest()

def _open_linux_verified_adapter(path:Path,expected_digest:str)->tuple[int,dict[str,int]]:
    flags=os.O_RDONLY|getattr(os,"O_CLOEXEC",0)|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)
    try:fd=os.open(path,flags)
    except OSError as exc:raise ValueError("external adapter executable must be an absolute regular executable file") from exc
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):raise ValueError("external adapter executable must be an absolute regular executable file")
        if not os.access(f"/proc/self/fd/{fd}",os.X_OK):raise ValueError("external adapter executable must be an absolute regular executable file")
        if _hash_fd(fd)!=expected_digest:raise ValueError("external adapter executable hash mismatch")
        return fd,{"device":int(info.st_dev),"inode":int(info.st_ino),"size":int(info.st_size),"mtimeNs":int(info.st_mtime_ns),"ctimeNs":int(info.st_ctime_ns)}
    except BaseException:
        os.close(fd);raise



def _normalize_platform_launch_attestation(value: Any, host_system: str) -> dict[str, Any] | None:
    if host_system == "Linux":
        return None
    attestations=value if isinstance(value,dict) else {}
    raw=attestations.get(host_system)
    if not isinstance(raw,dict):
        raise ValueError(f"external plugin manifest requires {host_system} platformLaunchAttestation")
    if host_system == "Windows":
        if set(raw)!={"mode","publisherCertificateSha256","fileIdentityRequired"}:
            raise ValueError("Windows platformLaunchAttestation has unsupported fields")
        if raw.get("mode")!="windows-authenticode-fileid-v1" or raw.get("fileIdentityRequired") is not True:
            raise ValueError("Windows platformLaunchAttestation requires Authenticode plus file identity binding")
        publisher=str(raw.get("publisherCertificateSha256","")).lower()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}",publisher):
            raise ValueError("Windows platformLaunchAttestation requires publisherCertificateSha256")
        return {"mode":"windows-authenticode-fileid-v1","publisherCertificateSha256":publisher,"fileIdentityRequired":True}
    if host_system == "Darwin":
        if set(raw)!={"mode","teamId","codeDirectoryHash"}:
            raise ValueError("Darwin platformLaunchAttestation has unsupported fields")
        team_id=str(raw.get("teamId","")).strip().upper();cdhash=str(raw.get("codeDirectoryHash","")).lower()
        if raw.get("mode")!="macos-codesign-cdhash-v1" or not re.fullmatch(r"[A-Z0-9]{6,64}",team_id):
            raise ValueError("Darwin platformLaunchAttestation requires a signed Team ID")
        if not re.fullmatch(r"cdhash:[0-9a-f]{40,64}",cdhash):
            raise ValueError("Darwin platformLaunchAttestation requires codeDirectoryHash")
        return {"mode":"macos-codesign-cdhash-v1","teamId":team_id,"codeDirectoryHash":cdhash}
    raise ValueError(f"unsupported host system {host_system}")

def validate_platform_launch_evidence(manifest: dict[str, Any], evidence: dict[str, Any], *, host_system: str) -> dict[str, Any]:
    """Validate OS-native verification evidence before a future platform binder launches an adapter.

    This deliberately does not launch anything. Windows/macOS runtime binding remains unavailable until
    a native implementation can prove that the process image is the same verified object.
    """
    normalized=validate_plugin_manifest(manifest,host_system=host_system,host_machine=str(manifest.get("hostArchitectures",[""])[0]))
    attestation=normalized.get("platformLaunchAttestation")
    if not isinstance(evidence,dict):raise ValueError("platform launch evidence must be an object")
    digest=str(evidence.get("adapterSha256","")).lower()
    if digest!=normalized["adapterSha256"]:raise ValueError("platform launch evidence adapter hash mismatch")
    if host_system=="Windows":
        if evidence.get("signatureStatus")!="Valid":raise ValueError("Windows adapter Authenticode signature is not valid")
        publisher=str(evidence.get("publisherCertificateSha256","")).lower()
        if publisher!=attestation["publisherCertificateSha256"]:raise ValueError("Windows adapter publisher certificate mismatch")
        volume=str(evidence.get("volumeSerial","")).strip();file_id=str(evidence.get("fileId","")).strip()
        if not volume or not file_id:raise ValueError("Windows adapter file identity is required")
        return {"binding":"windows-authenticode-fileid-v1","adapterSha256":digest,"publisherCertificateSha256":publisher,"volumeSerial":volume[:128],"fileId":file_id[:256]}
    if host_system=="Darwin":
        if evidence.get("signatureValid") is not True:raise ValueError("macOS adapter code signature is not valid")
        team_id=str(evidence.get("teamId","")).strip().upper();cdhash=str(evidence.get("codeDirectoryHash","")).lower()
        if team_id!=attestation["teamId"]:raise ValueError("macOS adapter Team ID mismatch")
        if cdhash!=attestation["codeDirectoryHash"]:raise ValueError("macOS adapter code directory hash mismatch")
        file_id=str(evidence.get("fileId","")).strip()
        if not file_id:raise ValueError("macOS adapter file identity is required")
        return {"binding":"macos-codesign-cdhash-v1","adapterSha256":digest,"teamId":team_id,"codeDirectoryHash":cdhash,"fileId":file_id[:256]}
    raise ValueError("platform launch evidence is only defined for Windows and macOS")

def validate_plugin_manifest(value: dict[str, Any], *, host_system: str | None = None, host_machine: str | None = None) -> dict[str, Any]:
    result=dict(value);fmt=str(result.get("format","")).lower();plugin_id=str(result.get("pluginId","")).strip()
    if fmt not in FORMATS or not plugin_id:raise ValueError("plugin manifest requires a supported format and pluginId")
    if fmt!="builtin":
        if not str(result.get("adapterExecutable","")).strip():raise ValueError("external plugin formats require an explicit adapter executable")
        systems=result.get("hostSystems");architectures=result.get("hostArchitectures");protocols=result.get("adapterProtocolVersions")
        if not isinstance(systems,list) or not systems or any(system not in {"Linux","Windows","Darwin"} for system in systems):raise ValueError("external plugin manifest requires supported hostSystems")
        if not isinstance(architectures,list) or not architectures or any(not isinstance(machine,str) or not machine.strip() for machine in architectures):raise ValueError("external plugin manifest requires hostArchitectures")
        if not isinstance(protocols,list) or not protocols or any(type(version) is not int or version<1 or version>16 for version in protocols):raise ValueError("external plugin manifest requires adapterProtocolVersions")
        if 1 not in protocols:raise ValueError("plugin adapter protocol 1 is not supported by this host")
        actual_system=host_system or platform.system();actual_machine=host_machine or platform.machine()
        if actual_system not in systems:raise ValueError(f"plugin adapter is incompatible with host system {actual_system}")
        if actual_machine not in architectures:raise ValueError(f"plugin adapter is incompatible with host architecture {actual_machine}")
        digest=str(result.get("adapterSha256","")).lower()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}",digest):raise ValueError("external plugin manifest requires adapterSha256")
        attestation=_normalize_platform_launch_attestation(result.get("platformLaunchAttestations"),actual_system)
        result.update({"hostSystems":list(dict.fromkeys(systems)),"hostArchitectures":list(dict.fromkeys(architectures)),"adapterProtocolVersions":list(dict.fromkeys(protocols)),"adapterSha256":digest})
        if attestation is not None:result["platformLaunchAttestation"]=attestation
    result.update({"format":fmt,"pluginId":plugin_id[:256],"realtimeProcessInCore":False,"physicalOutputsArmed":False})
    return result


class IsolatedPluginHost:
    """Watchdog client for a bounded effect process. Failure always becomes bypass."""
    def __init__(self, executable: Path, manifest: dict[str, Any], *, timeout: float=.25) -> None:
        self.manifest=validate_plugin_manifest(manifest);requested=Path(self.manifest["adapterExecutable"]) if self.manifest["format"]!="builtin" else Path(executable)
        if self.manifest["format"]!="builtin" and (not requested.is_absolute() or not requested.is_file() or not os.access(requested,os.X_OK)):raise ValueError("external adapter executable must be an absolute executable file")
        if self.manifest["format"]!="builtin":
            if sys.platform.startswith("linux"):
                fd,_=_open_linux_verified_adapter(requested,self.manifest["adapterSha256"]);os.close(fd)
            else:
                raise RuntimeError("external plugin launch binding is not implemented for this platform")
        self.executable=requested;self.command=[sys.executable,str(requested)] if requested.suffix.lower()==".py" else [str(requested)];self.timeout=max(.01,min(float(timeout),5.0))
        self.launch_binding="builtin" if self.manifest["format"]=="builtin" else "path-digest";self.launch_identity:dict[str,int]|None=None
        self.process:subprocess.Popen[str]|None=None;self.bypassed=True;self.failures=0;self._lock=threading.RLock()
        self.scratch_path:Path|None=None;self.scratch_resource_id=None
        self.starts=0;self.closes=0;self.forced_kills=0;self.last_exit_code=None;self.requests=0;self.process_blocks=0;self.processed_samples=0;self.timeouts=0;self.disconnects=0;self.host_errors=0;self.invalid_responses=0;self.max_request_duration_ns=0;self.last_error=None
        self.qualification_enabled=os.environ.get("STAGEMESH_RT_QUALIFICATION","").strip().lower() in {"1","true","yes","on"}
        self.serialization_lock_attempts=0;self.serialization_lock_contentions=0;self.max_serialization_lock_wait_ns=0;self.request_payload_bytes=0;self.response_payload_bytes=0
        self._next_request_id=1;self.protocol_version=None;self.latency_frames=None;self.process_supported=False
        with _HOSTS_LOCK:_HOSTS.add(self)

    @contextmanager
    def _locked(self):
        if not self.qualification_enabled:
            with self._lock:
                yield
            return
        started=time.monotonic_ns()
        contended=not self._lock.acquire(blocking=False)
        if contended:self._lock.acquire()
        waited=time.monotonic_ns()-started
        self.serialization_lock_attempts+=1
        self.max_serialization_lock_wait_ns=max(self.max_serialization_lock_wait_ns,waited)
        if contended:self.serialization_lock_contentions+=1
        try:yield
        finally:self._lock.release()

    def start(self)->dict[str,Any]:
        with self._locked():
            self.close();scratch_root=_scratch_root()
            scratch_status=plugin_host_scratch_status()
            if scratch_status["observedBytes"]>=scratch_status["configuredMaximumBytes"]:raise RuntimeError("plugin scratch store reached configured budget")
            self.scratch_path=Path(tempfile.mkdtemp(prefix="host-",dir=scratch_root));self.scratch_path.chmod(0o700);self.scratch_resource_id="plugin-"+hashlib.sha256(self.scratch_path.name.encode()).hexdigest()[:20]
            try:
                create_owner_manifest(self.scratch_path/"owner.json",self.scratch_path,resource_class="plugin-host-scratch",purpose="isolated-effect-host",extra={"pluginIdHash":hashlib.sha256(self.manifest["pluginId"].encode()).hexdigest()})
                fsync_directory(scratch_root)
                environment=os.environ.copy();environment["STAGEFORGE_PLUGIN_INSTANCE_SCRATCH_DIR"]=str(self.scratch_path)
                launch_command=self.command;launch_kwargs:dict[str,Any]={}
                adapter_fd=None
                if self.manifest["format"]!="builtin" and sys.platform.startswith("linux"):
                    adapter_fd,self.launch_identity=_open_linux_verified_adapter(self.executable,self.manifest["adapterSha256"])
                    fd_path=f"/proc/self/fd/{adapter_fd}"
                    launch_command=[sys.executable,fd_path] if self.executable.suffix.lower()==".py" else [fd_path]
                    launch_kwargs["pass_fds"]=(adapter_fd,)
                    self.launch_binding="linux-procfd-sha256"
                try:
                    self.process=subprocess.Popen(launch_command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,shell=False,env=environment,**launch_kwargs);self.starts+=1
                finally:
                    if adapter_fd is not None:os.close(adapter_fd)
                result=self._request({"op":"activate","manifest":self.manifest})
                valid=(result.get("active") is True and type(result.get("protocolVersion")) is int and result["protocolVersion"]==1 and result.get("pluginId")==self.manifest["pluginId"] and result.get("format")==self.manifest["format"] and result.get("supportsProcess") is True and type(result.get("latencyFrames")) is int and 0<=result["latencyFrames"]<=65536)
                if not valid:self._failure("invalid","plugin adapter handshake mismatch");raise ValueError("plugin adapter handshake mismatch")
            except BaseException:
                self.close();raise
            self.protocol_version=1;self.latency_frames=result["latencyFrames"];self.process_supported=True;self.bypassed=False;return self.status()

    def _failure(self,kind:str,message:str)->None:
        self.failures+=1;self.bypassed=True;self.last_error=str(message)[:512]
        if kind=="timeout":self.timeouts+=1
        elif kind=="disconnect":self.disconnects+=1
        elif kind=="host":self.host_errors+=1
        else:self.invalid_responses+=1

    def _request(self,value:dict[str,Any])->dict[str,Any]:
        with self._locked():
            started=time.monotonic_ns();self.requests+=1;request_id=self._next_request_id;self._next_request_id+=1;request=dict(value);request["requestId"]=request_id;process=self.process
            try:
                if not process or process.poll() is not None or not process.stdin or not process.stdout:self._failure("disconnect","plugin host unavailable");raise RuntimeError("plugin host unavailable")
                encoded=json.dumps(request,separators=(",",":"),allow_nan=False)+"\n";self.request_payload_bytes+=len(encoded.encode("utf-8"));process.stdin.write(encoded);process.stdin.flush();result:list[str]=[]
                thread=threading.Thread(target=lambda:result.append(process.stdout.readline()),daemon=True);thread.start();thread.join(self.timeout)
                if thread.is_alive():
                    self._failure("timeout","plugin host watchdog timeout");process.kill();self.forced_kills+=1;process.wait(timeout=1);raise TimeoutError("plugin host watchdog timeout")
                if not result or not result[0]:self._failure("disconnect","plugin host disconnected");raise RuntimeError("plugin host disconnected")
                self.response_payload_bytes+=len(result[0].encode("utf-8"))
                try:decoded=json.loads(result[0])
                except (json.JSONDecodeError,TypeError) as exc:self._failure("invalid",str(exc));raise
                if not isinstance(decoded,dict):self._failure("invalid","plugin host response must be an object");raise ValueError("plugin host response must be an object")
                if decoded.get("requestId")!=request_id:self._failure("invalid","plugin host response correlation mismatch");raise ValueError("plugin host response correlation mismatch")
                if not decoded.get("ok"):message=str(decoded.get("error","plugin host error"));self._failure("host",message);raise RuntimeError(message)
                return decoded
            finally:self.max_request_duration_ns=max(self.max_request_duration_ns,time.monotonic_ns()-started)

    def process_block(self,samples:list[float])->list[float]:
        with self._locked():
            if self.bypassed:return list(samples)
            if len(samples)>4096:raise ValueError("plugin block exceeds 4096 samples")
            if any(not math.isfinite(float(value)) for value in samples):raise ValueError("plugin input samples must be finite")
            try:
                result=[float(v) for v in self._request({"op":"process","samples":samples})["samples"]]
                if len(result)!=len(samples) or any(not math.isfinite(value) for value in result):self._failure("invalid","plugin output block is invalid");raise ValueError("plugin output block is invalid")
                self.process_blocks+=1;self.processed_samples+=len(result);return result
            except (RuntimeError,TimeoutError,ValueError,KeyError,json.JSONDecodeError):self.bypassed=True;return list(samples)

    def status(self)->dict[str,Any]:
        with self._locked():return {"pluginId":self.manifest["pluginId"],"format":self.manifest["format"],"isolated":True,"running":bool(self.process and self.process.poll() is None),"bypassed":self.bypassed,"failures":self.failures,"scratchResourceId":self.scratch_resource_id,"launch":{"binding":self.launch_binding,"identity":dict(self.launch_identity) if self.launch_identity else None},"handshake":{"protocolVersion":self.protocol_version,"latencyFrames":self.latency_frames,"supportsProcess":self.process_supported},"audit":{"starts":self.starts,"closes":self.closes,"forcedKills":self.forced_kills,"lastExitCode":self.last_exit_code,"requests":self.requests,"processBlocks":self.process_blocks,"processedSamples":self.processed_samples,"timeouts":self.timeouts,"disconnects":self.disconnects,"hostErrors":self.host_errors,"invalidResponses":self.invalid_responses,"maxRequestDurationNs":self.max_request_duration_ns,"lastError":self.last_error,"qualificationEnabled":self.qualification_enabled,"serializationLockAttempts":self.serialization_lock_attempts,"serializationLockContentions":self.serialization_lock_contentions,"maxSerializationLockWaitNs":self.max_serialization_lock_wait_ns,"requestPayloadBytes":self.request_payload_bytes,"responsePayloadBytes":self.response_payload_bytes},"physicalOutputsArmed":False}

    def close(self)->None:
        with self._locked():
            process=self.process
            try:
                if process:
                    if process.poll() is None:
                        try:process.terminate()
                        except ProcessLookupError:pass
                        try:process.wait(timeout=1)
                        except subprocess.TimeoutExpired:process.kill();self.forced_kills+=1;process.wait(timeout=1)
                    self.last_exit_code=process.poll();self.closes+=1
            finally:
                if process:
                    for stream in (process.stdin,process.stdout,process.stderr):
                        try:
                            if stream:stream.close()
                        except OSError:pass
                self.process=None
                if self.scratch_path is not None:shutil.rmtree(self.scratch_path,ignore_errors=True)
                self.scratch_path=None;self.scratch_resource_id=None;self.bypassed=True;self.protocol_version=None;self.latency_frames=None;self.process_supported=False
