from __future__ import annotations
import math,struct,time
from threading import Event,Lock,RLock,Thread
from pathlib import Path
from typing import Any
from daw_runtime import RecordingSpool
from punch_capture import PunchCaptureGate
from recording_recovery import recover_partial

class CaptureDrainer:
    STOP_TIMEOUT_SECONDS = 2.0
    def __init__(self,native,root:Path)->None:self.native=native;self.root=Path(root);self.stop_event=Event();self.thread:Thread|None=None;self.spool:RecordingSpool|None=None;self.gate:PunchCaptureGate|None=None;self.lock=Lock();self.lifecycle_lock=RLock();self.track:int|None=None;self.state={"state":"idle","blocks":0,"frames":0,"dropoutBlocks":0,"physicalInputArmed":False,"physicalOutputsArmed":False}
    def start(self,track:int,take_id:str,file_name:str,**plan:Any)->dict[str,Any]:
        with self.lifecycle_lock:return self._start(track,take_id,file_name,**plan)
    def _start(self,track:int,take_id:str,file_name:str,**plan:Any)->dict[str,Any]:
        if self.spool is not None:raise RuntimeError("finish or abort the pending capture before starting another")
        if track<0 or track>=8:raise ValueError("capture track must be between 0 and 7")
        self.spool=RecordingSpool(self.root);self.spool.begin(take_id,acknowledge_physical_input=True)
        try:
            armed=self.native.daw_record_arm(track,True);generation=int((armed or {}).get("generation",1))
            self.gate=PunchCaptureGate(generation,punch_in_frame=int(plan.get("punchInFrame",0)),punch_out_frame=plan.get("punchOutFrame"),pre_roll_frames=int(plan.get("preRollFrames",0)),latency_compensation_frames=int(plan.get("latencyCompensationFrames",0)),loop_start_frame=plan.get("loopStartFrame"),loop_end_frame=plan.get("loopEndFrame"),maximum_passes=int(plan.get("maximumPasses",1)))
        except Exception:
            try:self.native.daw_record_disarm(track)
            except Exception:pass
            self.spool.abort();self.spool=None;raise
        self.track=track;self.stop_event.clear();self.finish_event=Event()
        with self.lock:self.state={"state":"recording","track":track,"takeId":take_id,"fileName":Path(file_name).name,"blocks":0,"frames":0,"dropoutBlocks":0,"generation":generation,"physicalInputArmed":True,"physicalOutputsArmed":False}
        self.thread=Thread(target=self._run,args=(track,),name="stagemesh-capture-drain",daemon=True);self.thread.start();return self.status()
    def _run(self,track:int)->None:
        last=0;drained=0
        while not self.stop_event.is_set():
            try:
                try:
                    block=self.native.daw_record_pop(track)
                except RuntimeError as exc:
                    if str(exc).startswith("empty:"):
                        if self.finish_event.is_set():
                            with self.lock:self.state["queueDrained"]=True
                            break
                        self.stop_event.wait(.003);continue
                    raise
                if self.stop_event.is_set():break
                if self.finish_event.is_set():
                    drained+=1
                    if drained>65:raise RuntimeError("capture queue did not drain within bounded tail")
                frames=block["frames"]
                if type(frames) is not int or frames<=0 or len(block["left"])!=frames or len(block["right"])!=frames:
                    raise ValueError("capture channel lengths must match positive frame count")
                if any(not math.isfinite(value) for channel in (block["left"],block["right"]) for value in channel):
                    raise ValueError("capture samples must be finite")
                if last and block["sequence"]!=last+1:
                    gap=max(1,block["sequence"]-last-1);self.spool.dropout(block["showFrame"],gap*block["frames"])
                    with self.lock:self.state["dropoutBlocks"]+=gap
                last=block["sequence"]
                for selected in self.gate.select(block):
                    values=[];finish=selected.offset+selected.frames
                    for left,right in zip(block["left"][selected.offset:finish],block["right"][selected.offset:finish]):values.extend((round(max(-1,min(1,left))*2147483647),round(max(-1,min(1,right))*2147483647)))
                    self.spool.append_s32(struct.pack("<"+"i"*len(values),*values),selected.frames)
                    with self.lock:self.state["blocks"]+=1;self.state["frames"]+=selected.frames
                if self.gate.complete:
                    self.native.daw_record_disarm(track);self.stop_event.set()
                    with self.lock:self.state["state"]="punch-complete";self.state["physicalInputArmed"]=False
            except Exception as exc:
                self.stop_event.set()
                with self.lock:self.state["state"]="failed";self.state["captureError"]=str(exc);self.state["lastError"]=str(exc)
                try:
                    self.native.daw_record_disarm(track)
                    with self.lock:self.state["physicalInputArmed"]=False
                except Exception as disarm_error:
                    with self.lock:self.state["disarmError"]=str(disarm_error)
                break
    def finish(self,file_name:str|None=None)->dict[str,Any]:
        with self.lifecycle_lock:return self._finish(file_name)
    def recover(self,name:str)->dict[str,Any]:
        with self.lifecycle_lock:
            if self.spool is not None:raise RuntimeError("recovery requires no pending capture")
            try:return recover_partial(self.root,name)
            except FileNotFoundError as exc:raise ValueError("partial recording no longer exists; refresh the list") from exc
    def recovery_candidates(self)->dict[str,Any]:
        with self.lifecycle_lock:
            if self.spool is not None:return {"available":False,"reason":"Finish or abort the pending capture first.","files":[],"truncated":False}
            files=[];truncated=False
            for index,path in enumerate(self.root.iterdir()):
                if index>=1000:truncated=True;break
                if not path.name.endswith(".partial.wav") or path.is_symlink():continue
                try:
                    if path.is_file():files.append({"fileName":path.name,"bytes":path.stat().st_size})
                except FileNotFoundError:continue
            return {"available":True,"files":sorted(files,key=lambda item:item["fileName"]),"truncated":truncated}
    def _quiesce(self,*,drain:bool=False)->None:
        if not drain:self.stop_event.set()
        if self.track is not None and getattr(self.native,"available",False):
            self.native.daw_record_disarm(self.track)
            with self.lock:self.state["physicalInputArmed"]=False
        if drain and self.thread:self.finish_event.set()
        if self.thread:self.thread.join(timeout=self.STOP_TIMEOUT_SECONDS)
        if self.thread and self.thread.is_alive():
            with self.lock:self.state["stopTimedOut"]=True;self.state["lastError"]="capture worker has not stopped"
            raise RuntimeError("capture worker has not stopped; take remains pending")
        with self.lock:self.state["stopTimedOut"]=False
    def _finish(self,file_name:str|None=None)->dict[str,Any]:
        if not self.spool:raise RuntimeError("capture drain inactive")
        if file_name is not None:
            if not file_name or Path(file_name).name!=file_name or not file_name.lower().endswith(".wav"):
                raise ValueError("recording output must be a WAV basename")
            with self.lock:self.state["fileName"]=file_name
        self._quiesce(drain=True)
        if self.state.get("captureError"):
            raise RuntimeError("capture failed; abort the pending take: "+self.state["captureError"])
        try:receipt=self.spool.finish(str(self.state["fileName"]))
        except FileExistsError as exc:
            with self.lock:self.state["state"]="finalization-pending";self.state["finalizationError"]="output already exists"
            raise RuntimeError("recording output already exists; retry finish with a different fileName") from exc
        except OSError as exc:
            with self.lock:self.state["state"]="finalization-pending";self.state["finalizationError"]=str(exc)
            raise RuntimeError("recording finalization failed; take retained for retry") from exc
        gate_status=self.gate.status() if self.gate else {};self.spool=None;self.thread=None;self.track=None;self.gate=None
        with self.lock:self.state.pop("finalizationError",None)
        with self.lock:self.state={**self.state,**gate_status,**receipt,"state":"complete","physicalInputArmed":False,"receipt":receipt}
        return self.status()
    def abort(self)->None:
        with self.lifecycle_lock:self._abort()
    def _abort(self)->None:
        self._quiesce()
        if self.spool:self.spool.abort()
        self.spool=None;self.thread=None;self.track=None;self.gate=None
        with self.lock:self.state={"state":"aborted","blocks":0,"frames":0,"dropoutBlocks":0,"physicalInputArmed":False,"physicalOutputsArmed":False}
    def status(self)->dict[str,Any]:
        with self.lock:return {**self.state,**(self.gate.status() if self.gate else {})}
