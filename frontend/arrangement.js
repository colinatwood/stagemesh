(function(root) {
  const RATE=192000;
  const selected=new Set();
  function snapFrames(session, mode) {
    if (mode==='off') return 1;
    const tempo=Number(session.tempoMap?.[0]?.bpm || 120);
    const beat=Math.max(1,Math.round(RATE*60/tempo));
    if (mode==='sixteenth') return Math.max(1,Math.round(beat/4));
    if (mode==='bar') return beat*Math.max(1,Number(session.tempoMap?.[0]?.numerator || 4));
    return beat;
  }
  function bindClips({doc,session,zoomSeconds,snap,onSelect,onEdit}) {
    const grid=snapFrames(session,snap);
    const buttons=[...doc.querySelectorAll('[data-daw-clip]')];const valid=new Set(buttons.map(button=>button.dataset.dawClip));
    for(const id of [...selected])if(!valid.has(id))selected.delete(id);
    for (const button of buttons) {
      const clip=(session.tracks||[]).flatMap(track=>track.clips||[]).find(item=>item.clipId===button.dataset.dawClip);
      if (!clip) continue;
      button.classList?.toggle('selected',selected.has(clip.clipId));button.setAttribute('aria-pressed',String(selected.has(clip.clipId)));
      button.setAttribute('aria-label',`${clip.clipId}, starts at ${(clip.startFrame/RATE).toFixed(3)} seconds. Drag or use arrow keys to move. Use left and right bracket to trim edges.`);
      let gesture=null,suppressClick=false;
      const notify=()=>onSelect([...selected],clip.clipId);
      button.addEventListener('click',(event)=>{if(suppressClick){suppressClick=false;return;}if(event.shiftKey||event.ctrlKey||event.metaKey){selected.has(clip.clipId)?selected.delete(clip.clipId):selected.add(clip.clipId);}else{selected.clear();selected.add(clip.clipId);}notify();});
      button.addEventListener('pointerdown',(event)=>{
        if(event.button!==undefined&&event.button!==0)return;
        suppressClick=false;
        // Modifier selection is committed by click. Never rerender while capturing.
        if(event.shiftKey||event.ctrlKey||event.metaKey)return;
        const edge=event.target?.dataset?.dawResize||'';
        if(!edge&&!selected.has(clip.clipId)){
          selected.clear();selected.add(clip.clipId);
          for(const item of buttons){const active=selected.has(item.dataset.dawClip);item.classList?.toggle('selected',active);item.setAttribute('aria-pressed',String(active));}
        }
        gesture={x:event.clientX,start:clip.startFrame,width:button.parentElement.clientWidth,edge};button.setPointerCapture?.(event.pointerId);
      });
      button.addEventListener('pointermove',(event)=>{if(!gesture)return;const pixels=event.clientX-gesture.x;const previews=gesture.edge?[button]:buttons.filter(item=>selected.has(item.dataset.dawClip));if(gesture.edge==='start'){const trim=Math.max(0,pixels);button.style.transform=`translateX(${trim}px)`;button.style.width=`calc(var(--clip-width) - ${trim}px)`;}else if(gesture.edge==='end'){button.style.width=`calc(var(--clip-width) - ${Math.max(0,-pixels)}px)`;}else for(const item of previews)item.style.transform=`translateX(${pixels}px)`;});
      button.addEventListener('pointerup',(event)=>{
        if(!gesture)return;const active=gesture;const delta=Math.round((event.clientX-active.x)/Math.max(1,active.width)*Number(zoomSeconds)*RATE);gesture=null;for(const item of buttons){item.style.transform='';item.style.width='';}
        if(Math.abs(delta)<1)return;
        suppressClick=true;
        if(active.edge){const oldEnd=clip.startFrame+clip.lengthFrames;const startFrame=active.edge==='start'?Math.min(oldEnd-1,Math.max(clip.startFrame,clip.startFrame+delta)):clip.startFrame;const endFrame=active.edge==='end'?Math.max(clip.startFrame+1,Math.min(oldEnd,oldEnd+delta)):oldEnd;if(startFrame===clip.startFrame&&endFrame===oldEnd)return;onEdit({op:'resize',clipId:clip.clipId,startFrame,endFrame,snapFrames:grid});return;}
        if(selected.size>1){onEdit({op:'moveMany',clipIds:[...selected].sort(),deltaFrames:delta,snapFrames:grid});return;}
        const lane=doc.elementFromPoint?.(event.clientX,event.clientY)?.closest?.('[data-daw-lane]');
        onEdit({op:'move',clipId:clip.clipId,startFrame:Math.max(0,clip.startFrame+delta),targetTrackId:lane?.dataset.dawLane||button.dataset.dawTrack,snapFrames:grid});
      });
      button.addEventListener('pointercancel',()=>{gesture=null;for(const item of buttons){item.style.transform='';item.style.width='';}});
      button.addEventListener('keydown',(event)=>{
        if(['[',']'].includes(event.key)){event.preventDefault();const oldEnd=clip.startFrame+clip.lengthFrames;const startFrame=event.key==='['?Math.min(oldEnd-1,clip.startFrame+grid):clip.startFrame;const endFrame=event.key===']'?Math.max(clip.startFrame+1,oldEnd-grid):oldEnd;if(startFrame!==clip.startFrame||endFrame!==oldEnd)onEdit({op:'resize',clipId:clip.clipId,startFrame,endFrame,snapFrames:grid});return;}
        if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const step=event.altKey?256:grid;const direction=event.key==='ArrowLeft'?-1:1;
        if(selected.size>1&&selected.has(clip.clipId))onEdit({op:'moveMany',clipIds:[...selected].sort(),deltaFrames:direction*step,snapFrames:event.altKey?1:grid});
        else onEdit({op:'move',clipId:clip.clipId,startFrame:Math.max(0,clip.startFrame+direction*step),targetTrackId:button.dataset.dawTrack,snapFrames:event.altKey?1:grid});
      });
    }
  }
  const api={snapFrames,bindClips};if(typeof module!=='undefined')module.exports=api;root.StageMeshArrangement=api;
})(typeof globalThis!=='undefined'?globalThis:this);
