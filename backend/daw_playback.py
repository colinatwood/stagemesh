from __future__ import annotations
import math,time
from threading import Event,Lock,RLock,Thread
from typing import Any
from copy import deepcopy
from daw_production import OfflineRenderer,PreparedAutomation
from daw_session import render_plan
from media_snapshot import MediaSnapshot
from clip_fades import fade_envelope

class ArrangementProducer:
    """Control-thread media producer; all disk reads finish before native queue submission."""
    STOP_TIMEOUT_SECONDS = 1.0
    def __init__(self,native,media_root)->None:self.native=native;self.reader=OfflineRenderer(media_root);self.stop_event=Event();self.thread:Thread|None=None;self.lock=Lock();self.lifecycle_lock=RLock();self.state={"running":False,"producedBlocks":0,"producedFrames":0,"errors":0,"lastError":None,"physicalOutputsArmed":False}
    def _block(self,plan:dict[str,Any],start:int,frames:int)->tuple[list[float],list[float]]:
        left=[0.0]*frames;right=[0.0]*frames
        curves=getattr(self,"_automation_curves",None) if getattr(self,"_automation_plan_identity",None)==id(plan) else None
        curves=curves or {id(region):PreparedAutomation([p for p in region.get("automation",[]) if p.get("parameter")=="volume"]) for region in plan["regions"]}
        for region in plan["regions"]:
            begin=max(start,region["renderStartFrame"]);finish=min(start+frames,region["renderStartFrame"]+region["renderFrames"])
            if finish<=begin or region["source"].get("type")!="audio-file":continue
            amount=finish-begin;relative=begin-region["renderStartFrame"];sl,sr=self.reader._source_slice(str(region["source"].get("uri","")),region["sourceStartFrame"]+relative,amount);pan=max(-1,min(1,region["pan"]));gl=region["gain"]*math.sqrt((1-pan)/2);gr=region["gain"]*math.sqrt((1+pan)/2);fades=region.get("fades") or {};fi=int(fades.get("inFrames",0));fo=int(fades.get("outFrames",0))
            for i,gain in enumerate(curves[id(region)].block(begin,amount)):
                envelope=fade_envelope(region,relative+i)
                destination=begin-start+i;left[destination]+=sl[i]*gl*envelope*gain;right[destination]+=sr[i]*gr*envelope*gain
        return left,right
    def start(self,session:dict[str,Any],start_frame:int,end_frame:int,*,loop:bool=False)->dict[str,Any]:
        with self.lifecycle_lock:
            return self._start(session,start_frame,end_frame,loop=loop)
    def _start(self,session:dict[str,Any],start_frame:int,end_frame:int,*,loop:bool=False)->dict[str,Any]:
        if start_frame<0:raise ValueError("playback start must be non-negative")
        plan=render_plan(session,start_frame,end_frame)
        root=getattr(self,"source_root",self.reader.media_root)
        self.source_root=root
        snapshot=MediaSnapshot(root,plan,purpose="arrangement-playback")
        try:return self._start_snapshot(snapshot,start_frame,end_frame,loop)
        except BaseException:snapshot.close();raise
    def _start_snapshot(self,snapshot,start_frame,end_frame,loop):
        self.stop();self.native.daw_playback_loop_clear();self.native.daw_playback_seek(start_frame)
        if loop:self.native.daw_playback_loop(start_frame,end_frame)
        generation=int(self.native.daw_playback_status()["generation"]);self.stop_event.clear()
        with self.lock:self.state={"running":True,"generation":generation,"startFrame":start_frame,"endFrame":end_frame,"looping":loop,"producedBlocks":0,"producedFrames":0,"errors":0,"lastError":None,"physicalOutputsArmed":False}
        self.reader=OfflineRenderer(snapshot.root)
        self.thread=Thread(target=self._run,args=(snapshot.plan,generation,start_frame,end_frame,loop,snapshot),name="stagemesh-daw-producer",daemon=True);self.thread.start();return self.status()
    def start_clip(self,session:dict[str,Any],clip_id:str,*,loop:bool=False)->dict[str,Any]:
        isolated=deepcopy(session);selected=None
        for track in isolated.get("tracks",[]):
            clips=[clip for clip in track.get("clips",[]) if str(clip.get("clipId"))==clip_id]
            if clips:selected=(track,clips[0]);track["clips"]=clips
            else:track["clips"]=[]
        if not selected:raise ValueError("mapped DAW clip no longer exists")
        clip=selected[1];clip["startFrame"]=0;end=int(clip["lengthFrames"])
        return self.start(isolated,0,end,loop=loop)
    def _loop_block(self,plan:dict[str,Any],position:int,frames:int,start:int,end:int)->tuple[list[float],list[float]]:
        if end<=start or position<start or position>=end:raise ValueError("invalid loop cursor")
        left=[0.0]*frames;right=[0.0]*frames;written=0;cursor=position
        while written<frames:
            amount=min(frames-written,end-cursor);sl,sr=self._block(plan,cursor,amount)
            left[written:written+amount]=sl;right[written:written+amount]=sr;written+=amount;cursor+=amount
            if cursor>=end:cursor=start
        return left,right
    @staticmethod
    def _advance_loop(position:int,frames:int,start:int,end:int)->int:
        span=end-start
        if span<=0:raise ValueError("invalid loop range")
        return start+((position-start+frames)%span)
    def _run(self,plan,generation,start,end,repeat=False,snapshot=None)->None:
        position=start;started=False;self._automation_plan_identity=id(plan);self._automation_curves={id(region):PreparedAutomation([p for p in region.get("automation",[]) if p.get("parameter")=="volume"]) for region in plan["regions"]}
        try:
            while not self.stop_event.is_set():
                if position>=end:
                    if repeat:position=start
                    else:break
                status=self.native.daw_playback_status()
                if self.stop_event.is_set():break
                queued=int(status.get("queuedBlocks",0))
                if queued>=8 and not started:self.native.daw_playback_start();started=True
                if queued>=24:time.sleep(.003);continue
                if repeat:
                    frames=256;left,right=self._loop_block(plan,position,frames,start,end)
                else:
                    frames=min(256,end-position);left,right=self._block(plan,position,frames)
                    if frames<256:left.extend([0.0]*(256-frames));right.extend([0.0]*(256-frames));frames=256
                if self.stop_event.is_set():break
                self.native.daw_playback_pcm(generation,position,left,right)
                position=self._advance_loop(position,frames,start,end) if repeat else position+frames
                with self.lock:self.state["producedBlocks"]+=1;self.state["producedFrames"]+=frames
            if not self.stop_event.is_set() and not started:self.native.daw_playback_start()
        except Exception as exc:
            with self.lock:self.state["errors"]+=1;self.state["lastError"]=str(exc)
        finally:
            self._automation_curves=None;self._automation_plan_identity=None
            if snapshot is not None:snapshot.close()
            if self.stop_event.is_set() and self.native.available:
                try:self.native.daw_playback_stop()
                except RuntimeError:pass
            with self.lock:self.state["running"]=False
    def stop(self)->None:
        with self.lifecycle_lock:
            self._stop()
    def _stop(self)->None:
        self.stop_event.set()
        if self.native.available:
            try:self.native.daw_playback_stop()
            except RuntimeError:pass
        if self.thread and self.thread.is_alive():self.thread.join(timeout=self.STOP_TIMEOUT_SECONDS)
        if self.thread and self.thread.is_alive():
            with self.lock:self.state["stopTimedOut"]=True;self.state["lastError"]="playback producer has not stopped"
            raise RuntimeError("playback producer has not stopped; restart blocked")
        self.thread=None
        # A start already in flight when cancellation was requested must also stop.
        if self.native.available:
            try:self.native.daw_playback_stop()
            except RuntimeError:pass
        with self.lock:self.state["running"]=False;self.state["stopTimedOut"]=False
    def status(self)->dict[str,Any]:
        with self.lock:return dict(self.state)
