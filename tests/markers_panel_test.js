const assert=require('node:assert/strict');
global.StageMeshArrangement={snapFrames:()=>96000};global.confirm=()=>true;
const {render}=require('../frontend/markers.js');
class Element{
  constructor(value=''){this.value=value;this.dataset={};this.handlers={};this.children=[];this.style={};this.attributes={};this.clientWidth=100;this.textContent='';}
  addEventListener(name,handler){this.handlers[name]=handler;}setAttribute(name,value){this.attributes[name]=value;}replaceChildren(){this.children=[];}appendChild(child){this.children.push(child);}
}
async function main(){
 const nodes={dawMarkers:new Element(),dawMarkerAdd:new Element(),dawMarkerName:new Element('Bridge'),dawMarkerSeconds:new Element('2'),dawMarkerKind:new Element('section'),dawPlaybackBegin:new Element(),dawStatus:new Element()};
 const doc={querySelector:id=>nodes[id.slice(1)],createElement:()=>new Element()};const edits=[];const session={tempoMap:[{bpm:120}],markers:[{markerId:'m1',frame:192000,name:'Verse',kind:'section'}]};
 render({doc,session,zoomSeconds:10,snap:'beat',onEdit:value=>edits.push(value)});assert.equal(nodes.dawMarkers.children.length,1);
 const [locate,remove]=nodes.dawMarkers.children[0].children;locate.handlers.click();assert.equal(nodes.dawPlaybackBegin.value,'1.000');assert.match(nodes.dawStatus.textContent,/Located Verse/);
 locate.handlers.pointerdown({clientX:0,pointerId:1});locate.handlers.pointerup({clientX:10});assert.deepEqual(edits[0],{action:'move',markerId:'m1',frame:384000,snapFrames:96000});
 remove.handlers.click();assert.deepEqual(edits[1],{action:'delete',markerId:'m1'});
 nodes.dawMarkerAdd.handlers.click();assert.equal(edits[2].action,'add');assert.equal(edits[2].frame,192000);assert.equal(edits[2].name,'Bridge');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
