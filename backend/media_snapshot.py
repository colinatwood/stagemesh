"""Private disk copies owned by one render or playback operation."""
from copy import deepcopy
import hashlib
import json
import os
import shutil
import stat
import time
from threading import Lock
from pathlib import Path
import tempfile
from file_lock import exclusive_file_lock
from daw_media import resolve_media_path
from temporary_ownership import classify_owner,create_owner_manifest,fsync_directory,owner_live,process_identity,recheck_reclaimable


class MediaSnapshot:
    MAX_TOTAL_BYTES = 2 * 1024 ** 3
    FREE_RESERVE_BYTES = 64 * 1024 ** 2
    _budget_lock = Lock()
    _reserved_bytes = 0

    @classmethod
    def _store_path(cls, root):
        configured = os.environ.get("STAGEFORGE_SNAPSHOT_DIR", "").strip()
        source_root = Path(root).resolve()
        return Path(configured).expanduser().resolve() if configured else source_root.parent / ".stageforge-media-snapshots"

    @classmethod
    def _configured_bytes(cls, name, default, minimum):
        raw = os.environ.get(name, "").strip()
        if not raw: return default
        try: value = int(raw)
        except ValueError: raise RuntimeError(f"{name} must be an integer number of bytes") from None
        if value < minimum: raise RuntimeError(f"{name} must be at least {minimum} bytes")
        return value

    @staticmethod
    def _process_identity(pid=None):
        return process_identity(pid)

    @classmethod
    def _owner_live(cls, owner):
        return owner_live(owner)

    @staticmethod
    def _tree_size(path):
        total = 0
        for item in path.rglob("*"):
            try:
                if item.is_file() and not item.is_symlink(): total += item.stat().st_size
            except OSError:
                pass
        return total

    @classmethod
    def cleanup_stale(cls, store):
        """Caller holds the store lock. Unknown/replaced resources remain and consume quota."""
        reclaimed = []
        for directory in sorted(store.glob("snapshot-*")):
            if not directory.is_dir() or directory.is_symlink(): continue
            owner_path=directory/"owner.json"
            if recheck_reclaimable(owner_path,directory,resource_class="media-snapshot") is None:continue
            # The exact directory inode/device binding was rechecked immediately
            # before recursive removal.  Any replacement becomes unknown.
            try:shutil.rmtree(directory)
            except FileNotFoundError:continue
            reclaimed.append(directory.name)
        return reclaimed

    @classmethod
    def _store_bytes(cls, store):
        total = 0
        for path in store.glob("snapshot-*"):
            if not path.is_dir() or path.is_symlink(): continue
            reserved = 0
            try:
                manifest = json.loads((path / "owner.json").read_text())
                if type(manifest.get("reservedBytes")) is int and manifest["reservedBytes"] >= 0:
                    reserved = manifest["reservedBytes"]
            except (OSError, ValueError, TypeError):
                pass
            total += max(reserved, cls._tree_size(path))
        return total

    @classmethod
    def status(cls, root):
        """Return a bounded, path-free projection of the shared snapshot store."""
        store=cls._store_path(root);max_total=cls._configured_bytes("STAGEFORGE_SNAPSHOT_MAX_BYTES",cls.MAX_TOTAL_BYTES,1024*1024);free_reserve=cls._configured_bytes("STAGEFORGE_SNAPSHOT_FREE_RESERVE_BYTES",cls.FREE_RESERVE_BYTES,0)
        result={"documentType":"org.upp.daw-temporary-resource-status","schemaVersion":1,"resourceClass":"media-snapshot","configuredMaximumBytes":max_total,"freeReserveBytes":free_reserve,"reservedBytes":0,"observedBytes":0,"resources":[],"resourceCount":0,"liveCount":0,"reclaimableCount":0,"unknownOwnerCount":0,"scanTruncated":False,"automaticCleanup":"proven-dead-owner-on-create","physicalOutputsArmed":False}
        if not store.exists():return result
        directories=[item for item in sorted(store.glob("snapshot-*")) if item.is_dir() and not item.is_symlink()]
        result["resourceCount"]=len(directories);result["scanTruncated"]=len(directories)>128
        now_ms=int(time.time()*1000)
        for index,directory in enumerate(directories):
            state,owner=classify_owner(directory/"owner.json",directory,resource_class="media-snapshot")
            reserved=owner.get("reservedBytes",0) if isinstance(owner,dict) and type(owner.get("reservedBytes")) is int and owner.get("reservedBytes",0)>=0 else 0
            observed=cls._tree_size(directory)
            created=owner.get("createdAtUnixMs") if isinstance(owner,dict) and type(owner.get("createdAtUnixMs")) is int else None
            entry={"resourceId":directory.name,"state":state,"reservedBytes":reserved,"observedBytes":observed,"ageMs":max(0,now_ms-created) if created is not None else None,"purpose":str(owner.get("purpose","unknown"))[:32] if isinstance(owner,dict) else "unknown"}
            if index<128:result["resources"].append(entry)
            result["reservedBytes"]+=reserved;result["observedBytes"]+=observed
            if state=="live":result["liveCount"]+=1
            elif state=="reclaimable":result["reclaimableCount"]+=1
            else:result["unknownOwnerCount"]+=1
        return result

    @classmethod
    def reclaim(cls, root):
        store=cls._store_path(root)
        if not store.exists():return {**cls.status(root),"reclaimedCount":0,"reclaimedResourceIds":[]}
        lock_path=store/"quota.lock";lock_path.touch(mode=0o600,exist_ok=True)
        with lock_path.open("r+") as lock:
            with exclusive_file_lock(lock):reclaimed=cls.cleanup_stale(store)
        return {**cls.status(root),"reclaimedCount":len(reclaimed),"reclaimedResourceIds":reclaimed[:128]}

    def __init__(self, root, plan, *, purpose="unspecified"):
        self.reserved_bytes = 0
        source_root = Path(root).resolve()
        max_total = self._configured_bytes("STAGEFORGE_SNAPSHOT_MAX_BYTES", self.MAX_TOTAL_BYTES, 1024 * 1024)
        free_reserve = self._configured_bytes("STAGEFORGE_SNAPSHOT_FREE_RESERVE_BYTES", self.FREE_RESERVE_BYTES, 0)
        self.store = self._store_path(source_root)
        self.store.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = self.store / "quota.lock"
        lock_path.touch(mode=0o600, exist_ok=True)
        self.root = None
        self.plan = deepcopy(plan)
        self.plan["regions"] = [deepcopy(region) for region in plan["regions"]]
        copies = {}
        try:
            sources = {}
            for region in self.plan["regions"]:
                source = region["source"]
                if source.get("type") != "audio-file":continue
                uri = str(source.get("uri", ""));key = (uri, source.get("contentHash"))
                if key in sources:continue
                path = resolve_media_path(root, uri[6:] if uri.startswith("media/") else uri)
                info = path.stat()
                if not stat.S_ISREG(info.st_mode):raise ValueError("snapshot source must be a regular file")
                sources[key] = (path, info.st_size)
            required = sum(size for _, size in sources.values())
            with lock_path.open("r+") as lock:
                with exclusive_file_lock(lock):
                    self.cleanup_stale(self.store)
                    used = self._store_bytes(self.store)
                    if used + required > max_total:
                        raise RuntimeError("audio snapshots exceed the shared configured budget")
                    if shutil.disk_usage(self.store).free < required + free_reserve:
                        raise RuntimeError("insufficient temporary disk space for audio snapshot")
                    self.root = Path(tempfile.mkdtemp(prefix="snapshot-", dir=self.store))
                    create_owner_manifest(self.root/"owner.json",self.root,resource_class="media-snapshot",purpose=str(purpose)[:32],extra={"reservedBytes":required})
                    fsync_directory(self.store)
                    with MediaSnapshot._budget_lock:
                        MediaSnapshot._reserved_bytes += required
                        self.reserved_bytes = required
            for region in self.plan["regions"]:
                source = region["source"]
                if source.get("type") != "audio-file":
                    continue
                source = dict(source)
                region["source"] = source
                uri = str(source.get("uri", ""))
                expected = source.get("contentHash")
                key = (uri, expected)
                if key not in copies:
                    path, planned_size = sources[key]
                    name = f"source-{len(copies)}.wav"
                    digest = hashlib.sha256()
                    with path.open("rb") as original, (self.root / name).open("xb") as target:
                        before = os.fstat(original.fileno())
                        if not stat.S_ISREG(before.st_mode) or before.st_size != planned_size:
                            raise ValueError("session media changed before snapshot: " + uri)
                        copied = 0
                        while chunk := original.read(65536):
                            copied += len(chunk)
                            if copied > planned_size:raise ValueError("session media grew during snapshot: " + uri)
                            digest.update(chunk); target.write(chunk)
                        after = os.fstat(original.fileno())
                    actual = "sha256:" + digest.hexdigest()
                    if expected and actual != expected:
                        raise ValueError("session media hash mismatch: " + uri)
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError("session media changed during snapshot: " + uri)
                    copies[key] = (name, actual)
                source["uri"], source["contentHash"] = copies[key]
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.root is not None:
            shutil.rmtree(self.root, ignore_errors=True)
            self.root = None
        with MediaSnapshot._budget_lock:
            MediaSnapshot._reserved_bytes -= self.reserved_bytes
            self.reserved_bytes = 0
