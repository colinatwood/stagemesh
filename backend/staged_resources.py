"""Crash-visible staging files for DAW import and render publication."""
from __future__ import annotations
import fcntl,hashlib,os,tempfile
from pathlib import Path
from temporary_ownership import (
    classify_owner,create_owner_manifest,process_identity,recheck_reclaimable,owner_live,
)

# Compatibility aliases used by older internal callers/tests.  New cleanup is
# strict-v2 and therefore does not treat legacy dictionaries as reclaimable.
def _process_identity(pid=None):return process_identity(pid)
def _owner_live(owner):return owner_live(owner)

class StagedFile:
    def __init__(self,parent:Path,*,prefix:str,suffix:str,resource_class:str,purpose:str):
        parent=Path(parent);parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix=prefix,suffix=suffix,dir=parent);os.close(fd)
        self.path=Path(name);self.owner_path=Path(name+".owner.json");self.closed=False
        self.resource_class=str(resource_class)[:32];self.purpose=str(purpose)[:32]
        try:create_owner_manifest(self.owner_path,self.path,resource_class=self.resource_class,purpose=self.purpose)
        except BaseException:
            self.path.unlink(missing_ok=True);raise
    def publish(self,target:Path):
        os.replace(self.path,target);self.owner_path.unlink(missing_ok=True);self.closed=True
    def close(self):
        if self.closed:return
        self.path.unlink(missing_ok=True);self.owner_path.unlink(missing_ok=True);self.closed=True

class StagedResourceRegistry:
    def __init__(self,specs:list[tuple[str,Path,str]]):self.specs=[(kind,Path(root),pattern) for kind,root,pattern in specs]
    @staticmethod
    def _owner_path(path):return Path(str(path)+".owner.json")
    def _items(self):
        for resource_class,root,pattern in self.specs:
            if not root.exists():continue
            for path in sorted(root.rglob(pattern)):
                if path.is_file() and not path.is_symlink() and not path.name.endswith(".owner.json"):yield resource_class,root,path
    def status(self):
        import time
        now=int(time.time()*1000);entries=[];counts={"live":0,"reclaimable":0,"unknown-owner":0};observed=0;total=0
        for resource_class,root,path in self._items():
            total+=1
            try:size=path.stat().st_size
            except OSError:size=0
            observed+=size;state,owner=classify_owner(self._owner_path(path),path,resource_class=resource_class);counts[state]+=1
            created=owner.get("createdAtUnixMs") if isinstance(owner,dict) and type(owner.get("createdAtUnixMs")) is int else None
            relative=str(path.relative_to(root));resource_id="stage-"+hashlib.sha256(f"{resource_class}:{relative}".encode()).hexdigest()[:20]
            if len(entries)<128:entries.append({"resourceId":resource_id,"resourceClass":resource_class,"state":state,"observedBytes":size,"ageMs":max(0,now-created) if created is not None else None,"purpose":str(owner.get("purpose","unknown"))[:32] if isinstance(owner,dict) else "unknown"})
        return {"resourceCount":total,"liveCount":counts["live"],"reclaimableCount":counts["reclaimable"],"unknownOwnerCount":counts["unknown-owner"],"observedBytes":observed,"resources":entries,"scanTruncated":total>128}
    def reclaim(self):
        reclaimed=[]
        for resource_class,root,path in list(self._items()):
            lock_path=root/".stagemesh-staging.lock";lock_path.touch(mode=0o600,exist_ok=True)
            with lock_path.open("r+") as lock:
                fcntl.flock(lock,fcntl.LOCK_EX);owner_path=self._owner_path(path)
                if recheck_reclaimable(owner_path,path,resource_class=resource_class) is None:continue
                relative=str(path.relative_to(root));resource_id="stage-"+hashlib.sha256(f"{resource_class}:{relative}".encode()).hexdigest()[:20]
                # Final lstat identity is inside recheck_reclaimable immediately
                # before unlink.  Missing/replaced paths fail closed.
                try:path.unlink()
                except FileNotFoundError:continue
                owner_path.unlink(missing_ok=True);reclaimed.append(resource_id)
        return {**self.status(),"reclaimedCount":len(reclaimed),"reclaimedResourceIds":reclaimed[:128]}
