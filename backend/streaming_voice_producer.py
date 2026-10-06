from __future__ import annotations
import time
from copy import deepcopy
from threading import Event,RLock,Thread
from typing import Any
from daw_production import OfflineRenderer

VOICE_CAPACITY=16;BLOCK_FRAMES=256;PREBUFFER_BLOCKS=4;STOP_TIMEOUT_SECONDS=1.0;FEED_RETRY_TIMEOUT_SECONDS=.25

class PolyphonicStreamingProducer:
    """Service-thread media reader feeding independent bounded native voices."""
    def __init__(self,native,media_root)->None:
        self.native=native;self.reader=OfflineRenderer(media_root);self.lock=RLock();self.jobs={};self.next_generation=1;self.failures=0
    def _clip(self,session:dict[str,Any],clip_id:str)->dict[str,Any]:
        for track in session.get("tracks",[]):
            for clip in track.get("clips",[]):
                if str(clip.get("clipId"))==str(clip_id):return deepcopy(clip)
        raise ValueError("mapped DAW clip no longer exists")
    def _reclaim_locked(self)->None:
        for slot,job in list(self.jobs.items()):
            thread=job.get("thread")
            try:status=self.native.streaming_voice_slot_status(slot)
            except RuntimeError:continue
            if (not thread or not thread.is_alive()) and int(status.get("generation",0))==job["generation"] and status.get("active")=="0":self.jobs.pop(slot,None)
    def _allocate_locked(self)->int:
        self._reclaim_locked()
        for slot in range(VOICE_CAPACITY):
            if slot not in self.jobs:return slot
        raise RuntimeError("polyphonic streaming voice capacity reached")
    def _next_block(self,job:dict[str,Any])->tuple[list[float],list[float],bool]|None:
        if job["position"]>=job["frames"]:
            if job["loop"]:job["position"]=0
            else:return None
        count=min(BLOCK_FRAMES,job["frames"]-job["position"]);left,right=self.reader._source_slice(job["uri"],job["position"],count);job["position"]+=count
        return left,right,(not job["loop"] and job["position"]>=job["frames"])
    def _push_one(self,job:dict[str,Any])->bool:
        block=self._next_block(job)
        if block is None:return False
        left,right,terminal=block
        deadline=time.monotonic()+FEED_RETRY_TIMEOUT_SECONDS
        while not job["stop"].is_set():
            try:self.native.streaming_voice_block(job["slot"],job["generation"],job["sequence"],left,right,terminal);break
            except RuntimeError:
                job["backpressureRetries"]+=1
                if time.monotonic()>=deadline:raise RuntimeError("streaming voice feed remained unavailable")
                time.sleep(.002)
        if job["stop"].is_set():return False
        job["sequence"]+=1;job["producedBlocks"]+=1;job["producedFrames"]+=len(left);return not terminal or job["loop"]
    def start_clip(self,session:dict[str,Any],clip_id:str,*,loop:bool=False)->dict[str,Any]:
        if not self.native.available:raise RuntimeError("native streaming voice engine unavailable")
        clip=self._clip(session,clip_id);source=clip.get("source") or {};uri=str(source.get("uri",""));frames=int(clip.get("lengthFrames",0))
        if source.get("type")!="audio-file" or not uri or frames<=0:raise ValueError("streaming voice requires a non-empty audio-file clip")
        with self.lock:
            slot=self._allocate_locked();generation=self.next_generation;self.next_generation+=1
            job={"slot":slot,"generation":generation,"clipId":str(clip_id),"uri":uri,"frames":frames,"position":0,"sequence":1,"loop":bool(loop),"stop":Event(),"thread":None,"producedBlocks":0,"producedFrames":0,"backpressureRetries":0,"state":"prebuffering","error":None};self.jobs[slot]=job
        try:
            more=True
            for _ in range(PREBUFFER_BLOCKS):
                if more:more=self._push_one(job)
            self.native.streaming_voice_start(slot,generation,1.0,loop);job["state"]="feeding" if more else "feed-complete"
            if more:job["thread"]=Thread(target=self._run,args=(job,),name=f"stagemesh-stream-{slot}-{generation}",daemon=True);job["thread"].start()
            return {"voiceSlot":slot,"generation":generation,"clipId":str(clip_id),"looping":bool(loop),"prebufferedBlocks":job["producedBlocks"],"independentVoice":True,"activationQueued":True,"physicalOutputsArmed":False}
        except BaseException:
            with self.lock:self.jobs.pop(slot,None);self.failures+=1
            raise
    def _run(self,job:dict[str,Any])->None:
        try:
            while not job["stop"].is_set() and self._push_one(job):pass
            job["state"]="cancelled" if job["stop"].is_set() else "feed-complete"
        except Exception as exc:job["state"]="failed";job["error"]=str(exc);self.failures+=1
    def stop(self,slot:int,generation:int)->dict[str,Any]:
        with self.lock:
            job=self.jobs.get(slot)
            if not job or job["generation"]!=generation:raise ValueError("streaming voice generation unavailable")
            job["stop"].set();thread=job.get("thread")
        if thread and thread.is_alive():thread.join(STOP_TIMEOUT_SECONDS)
        if thread and thread.is_alive():raise RuntimeError("streaming voice feeder did not stop")
        self.native.streaming_voice_stop(slot,generation);job["state"]="stop-queued"
        return {"voiceSlot":slot,"generation":generation,"stopQueued":True,"physicalOutputsArmed":False}
    def status(self)->dict[str,Any]:
        with self.lock:
            self._reclaim_locked();voices=[{k:v for k,v in job.items() if k not in {"stop","thread","uri"}} for _,job in sorted(self.jobs.items())]
            return {"capacity":VOICE_CAPACITY,"voices":voices,"failures":self.failures,"backpressureRetries":sum(job["backpressureRetries"] for job in self.jobs.values()),"prebufferBlocks":PREBUFFER_BLOCKS,"blockFrames":BLOCK_FRAMES,"feedRetryTimeoutMs":round(FEED_RETRY_TIMEOUT_SECONDS*1000),"diskIoInAudioCallback":False,"physicalOutputsArmed":False}
    def close(self)->None:
        with self.lock:jobs=list(self.jobs.values());[job["stop"].set() for job in jobs]
        timed_out=False
        for job in jobs:
            thread=job.get("thread")
            if thread and thread.is_alive():thread.join(STOP_TIMEOUT_SECONDS)
            timed_out=timed_out or bool(thread and thread.is_alive())
        if self.native.available:self.native.streaming_voice_stop_all()
        if timed_out:raise RuntimeError("one or more streaming voice feeders did not stop")
