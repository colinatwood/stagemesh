(function(root){
  const RATE=192000;let current=null;let busy=false;
  async function submit(command){
    if(busy)return;
    const context=current,doc=context.doc;
    const save=doc.querySelector('#dawAutomationSave'),remove=doc.querySelector('#dawAutomationDelete'),status=doc.querySelector('#dawAutomationStatus');
    busy=true;save.disabled=true;remove.disabled=true;status.setAttribute('aria-busy','true');
    try{await context.onEdit(command);}
    catch(error){status.textContent=error.message||'Automation edit failed.';}
    finally{busy=false;save.disabled=false;remove.disabled=!doc.querySelector('#dawAutomationPoint').value;status.setAttribute('aria-busy','false');}
  }
  const id=()=>`automation-${root.crypto?.randomUUID?.()||Date.now()}`;
  function render(context){
    current=context;const {doc,session,zoomSeconds}=context;const onEdit=submit;const trackSelect=doc.querySelector('#dawAutomationTrack'),pointInput=doc.querySelector('#dawAutomationPoint'),seconds=doc.querySelector('#dawAutomationSeconds'),value=doc.querySelector('#dawAutomationValue'),save=doc.querySelector('#dawAutomationSave'),remove=doc.querySelector('#dawAutomationDelete'),lane=doc.querySelector('#dawAutomationLane'),status=doc.querySelector('#dawAutomationStatus');
    const previous=trackSelect.value;trackSelect.replaceChildren();for(const track of session.tracks||[]){const option=doc.createElement('option');option.value=track.trackId;option.textContent=track.name;trackSelect.appendChild(option);}if((session.tracks||[]).some(track=>track.trackId===previous))trackSelect.value=previous;
    if(!save.dataset.mounted){
      save.dataset.mounted='true';
      save.addEventListener('click',()=>{
        const unchanged=pointInput.value&&seconds.value===seconds.dataset.selectedText;
        const frame=unchanged?Number(seconds.dataset.selectedFrame):Math.round(Number(seconds.value)*RATE);
        const gain=Number(value.value),trackId=trackSelect.value;
        if(!trackId||!seconds.value.trim()||!value.value.trim()||!Number.isSafeInteger(frame)||frame<0||!Number.isFinite(gain)||gain<0||gain>2){status.textContent='Choose a track, non-negative time, and gain from 0 through 2.';return;}
        onEdit({action:'upsert',trackId,pointId:pointInput.value||id(),parameter:'volume',frame,value:gain});
      });
      remove.addEventListener('click',()=>{if(pointInput.value)onEdit({action:'delete',trackId:trackSelect.value,pointId:pointInput.value});});
      trackSelect.addEventListener('change',()=>{pointInput.value='';render(current);});
      doc.querySelector('#dawAutomationNew').addEventListener('click',()=>{
        if(busy)return;
        pointInput.value='';remove.disabled=true;
        status.textContent='New point: enter its time and gain, then save.';
      });
    }
    lane.replaceChildren();const track=(session.tracks||[]).find(item=>item.trackId===trackSelect.value);const points=(track?.automation||[]).filter(point=>point.parameter==='volume');
    for(const point of points){const node=doc.createElement('button');node.type='button';node.className='automationPoint';node.style.left=`${Math.min(100,point.frame/(RATE*zoomSeconds)*100)}%`;node.style.bottom=`${Math.min(100,point.value/2*100)}%`;node.textContent='';node.title=`${point.value.toFixed(2)} at ${(point.frame/RATE).toFixed(3)} seconds`;node.setAttribute('aria-label',`Volume ${node.title}`);let gesture=null;
      node.addEventListener('click',()=>{if(busy)return;pointInput.value=point.pointId;seconds.value=String(point.frame/RATE);seconds.dataset.selectedText=seconds.value;seconds.dataset.selectedFrame=String(point.frame);value.value=String(point.value);remove.disabled=false;status.textContent=`Selected ${point.pointId}. Drag it or edit its values.`;});
      node.addEventListener('pointerdown',event=>{gesture={x:event.clientX,y:event.clientY};node.setPointerCapture?.(event.pointerId);});node.addEventListener('pointerup',event=>{if(!gesture)return;const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y;gesture=null;if(!dx&&!dy)return;const frame=Math.max(0,Math.round(point.frame+dx/Math.max(1,lane.clientWidth)*zoomSeconds*RATE));const gain=Math.max(0,Math.min(2,point.value-dy/Math.max(1,lane.clientHeight)*2));onEdit({action:'upsert',trackId:track.trackId,pointId:point.pointId,parameter:'volume',frame,value:gain});});lane.appendChild(node);}
    if(!points.some(point=>point.pointId===pointInput.value)){pointInput.value='';remove.disabled=true;}status.textContent=`${points.length} linear volume point(s) on ${track?.name||'no track'}.`;
  }
  const api={render};if(typeof module!=='undefined')module.exports=api;root.StageMeshAutomation=api;
})(typeof globalThis!=='undefined'?globalThis:this);
