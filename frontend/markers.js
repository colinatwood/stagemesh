(function(root){
  const RATE=192000;
  function render({doc,session,zoomSeconds,snap,onEdit}){
    const rail=doc.querySelector('#dawMarkers'),add=doc.querySelector('#dawMarkerAdd'),name=doc.querySelector('#dawMarkerName'),seconds=doc.querySelector('#dawMarkerSeconds'),kind=doc.querySelector('#dawMarkerKind');
    const grid=root.StageMeshArrangement?.snapFrames(session,snap)||1;
    if(!add.dataset.mounted){add.dataset.mounted='true';add.addEventListener('click',()=>{const label=name.value.trim();const frame=Math.round(Number(seconds.value)*RATE);if(!label||!Number.isSafeInteger(frame)||frame<0){doc.querySelector('#dawStatus').textContent='Marker name and non-negative time are required.';return;}onEdit({action:'add',markerId:`marker-${root.crypto?.randomUUID?.()||Date.now()}`,name:label,kind:kind.value,frame});});}
    rail.replaceChildren();
    for(const marker of session.markers||[]){
      const item=doc.createElement('div');item.className=`dawMarker ${marker.kind}`;item.style.left=`${Math.min(100,marker.frame/(RATE*zoomSeconds)*100)}%`;
      const locate=doc.createElement('button');locate.type='button';locate.textContent=marker.name;locate.title=`${marker.kind} at ${(marker.frame/RATE).toFixed(3)} seconds`;locate.setAttribute('aria-label',locate.title);let startX=null;
      locate.addEventListener('click',()=>{seconds.value=(marker.frame/RATE).toFixed(3);doc.querySelector('#dawPlaybackBegin').value=(marker.frame/RATE).toFixed(3);doc.querySelector('#dawStatus').textContent=`Located ${marker.name} at ${(marker.frame/RATE).toFixed(3)} seconds.`;});
      locate.addEventListener('pointerdown',event=>{startX=event.clientX;locate.setPointerCapture?.(event.pointerId);});
      locate.addEventListener('pointerup',event=>{if(startX===null)return;const delta=Math.round((event.clientX-startX)/Math.max(1,rail.clientWidth)*zoomSeconds*RATE);startX=null;if(delta)onEdit({action:'move',markerId:marker.markerId,frame:Math.max(0,marker.frame+delta),snapFrames:grid});});
      const remove=doc.createElement('button');remove.type='button';remove.textContent='×';remove.setAttribute('aria-label',`Delete marker ${marker.name}`);remove.addEventListener('click',()=>{if(root.confirm(`Delete marker ${marker.name}?`))onEdit({action:'delete',markerId:marker.markerId});});
      item.appendChild(locate);item.appendChild(remove);rail.appendChild(item);
    }
  }
  const api={render};if(typeof module!=='undefined')module.exports=api;root.StageMeshMarkers=api;
})(typeof globalThis!=='undefined'?globalThis:this);
