"""Run canvas object handlers to verify keyboard and pointer ownership behavior."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js required for frontend behavior checks")
class TemplateKeyboardTests(unittest.TestCase):
    def test_import_button_opens_existing_chooser_and_keeps_shared_validator(self):
        source = (ROOT / "frontend/stage-template.js").read_text()
        self.assertEqual(source.count("const validateTemplateDocument ="), 1)
        self.assertNotIn("const validateImport =", source)
        html = (ROOT / "frontend/app.html").read_text()
        self.assertIn('<button id="templateImportButton" type="button">', html)
        registration = next(line for line in source.splitlines()
                            if 'q("#templateImportButton").addEventListener' in line)
        result = subprocess.run(["node", "-e", r'''
const vm=require('node:vm'), assert=require('node:assert/strict');
let handler, clicks=0;
const q=selector=>selector==='#templateImportButton'
  ? {addEventListener:(type,callback)=>{assert.equal(type,'click');handler=callback;}}
  : {click:()=>clicks++};
vm.runInNewContext(process.argv[1],{q});
handler();assert.equal(clicks,1);
''', registration], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_selection_movement_and_pointer_capture_keep_the_same_node(self):
        result = subprocess.run(["node", "-e", r'''
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/stage-template.js','utf8');
const start=source.indexOf('      node.setAttribute("aria-label"');
const end=source.indexOf('      canvas.appendChild(node);',start);
assert.ok(start>0 && end>start);
const handlers={}, attributes={}, hint={}, del={disabled:true};
let saved=0, focused=0, capture, failSave=false;
const item={id:'lead',label:'Vocal',type:'performer',x:50,y:50};
const node={dataset:{id:'lead'},style:{},classList:{toggle:()=>{}},setAttribute:(key,value)=>attributes[key]=value,
  addEventListener:(type,callback)=>handlers[type]=callback,focus:()=>focused++,setPointerCapture:id=>capture=id};
const context={item,node,selectedId:null,drag:null,pendingAction:null,esc:value=>value,
  canvas:{querySelectorAll:()=>[node],getBoundingClientRect:()=>({left:0,top:0,width:100,height:100})},
  q:selector=>selector==='#templateDelete'?del:hint,save:()=>{if(failSave)throw Error('disk full');saved++;},render:()=>{throw Error('must not replace captured/focused node');}};
vm.runInNewContext(source.slice(start,end),context);
handlers.click();assert.equal(context.selectedId,'lead');assert.equal(del.disabled,false);assert.equal(attributes['aria-pressed'],'true');
function key(key,extra={}) {let prevented=false;handlers.keydown({key,preventDefault:()=>prevented=true,...extra});return prevented;}
context.pendingAction={action:'server save'};
assert.equal(key('ArrowLeft'),true);assert.equal(item.x,50);assert.equal(saved,0);
handlers.pointerdown({button:0,pointerId:6,preventDefault(){throw Error('pending action must block capture');}});
assert.equal(context.drag,null);assert.equal(capture,undefined);assert.match(hint.textContent,/wait for server save to finish/);
context.pendingAction=null;
assert.equal(key('ArrowLeft'),true);assert.equal(item.x,49);assert.equal(saved,1);
key('ArrowDown',{shiftKey:true});assert.equal(item.y,60);
for(let i=0;i<15;i++)key('ArrowRight',{shiftKey:true});assert.equal(item.x,100);
for(let i=0;i<15;i++)key('ArrowUp',{shiftKey:true});assert.equal(item.y,0);
assert.equal(node.style.left,'100%');assert.equal(node.style.top,'0%');
const before=saved;assert.equal(key('ArrowRight',{ctrlKey:true}),false);assert.equal(key('Enter'),false);assert.equal(saved,before);
handlers.pointerdown({button:2});assert.equal(context.drag,null);
handlers.pointerdown({button:0,pointerId:7,preventDefault(){}});assert.equal(capture,7);assert.equal(focused,1);
handlers.pointermove({pointerId:8,clientX:25,clientY:25});assert.equal(item.x,100);
handlers.pointermove({pointerId:7,clientX:25,clientY:25});assert.equal(item.x,25);assert.equal(item.y,25);
handlers.pointercancel({pointerId:7});assert.equal(item.x,100);assert.equal(item.y,0);assert.equal(context.drag,null);assert.equal(saved,before);
handlers.pointerdown({button:0,pointerId:9,preventDefault(){}});
handlers.pointermove({pointerId:9,clientX:35,clientY:45});handlers.pointerup({pointerId:9});
assert.equal(context.drag,null);assert.equal(item.x,35);assert.equal(item.y,45);assert.equal(saved,before+1);
// A second pointer and keyboard movement cannot take ownership of an active drag.
const savedAfterCommit=saved;
handlers.pointerdown({button:0,pointerId:10,preventDefault(){}});
handlers.pointerdown({button:0,pointerId:11,preventDefault(){throw Error('secondary pointer must be ignored');}});
assert.equal(context.drag.pointerId,10);assert.equal(capture,10);
key('ArrowRight');assert.equal(item.x,35);assert.equal(saved,savedAfterCommit);
handlers.pointermove({pointerId:10,clientX:55,clientY:65});
handlers.pointerup({pointerId:11});handlers.pointercancel({pointerId:11});handlers.lostpointercapture({pointerId:11});
assert.equal(context.drag.pointerId,10);assert.ok(Math.abs(item.x-55)<1e-9);assert.equal(saved,savedAfterCommit);
handlers.lostpointercapture({pointerId:10});
assert.equal(context.drag,null);assert.equal(item.x,35);assert.equal(item.y,45);assert.equal(saved,savedAfterCommit);
assert.equal(node.style.left,'35%');assert.equal(node.style.top,'45%');
// Successful completion is not rolled back by the browser's subsequent capture release.
handlers.pointerdown({button:0,pointerId:12,preventDefault(){}});
handlers.pointermove({pointerId:12,clientX:60,clientY:70});handlers.pointerup({pointerId:12});
handlers.lostpointercapture({pointerId:12});
assert.equal(item.x,60);assert.equal(item.y,70);assert.equal(saved,savedAfterCommit+1);
// A failed keyboard persistence attempt restores both model and rendered position.
failSave=true;key('ArrowLeft');
assert.equal(item.x,60);assert.equal(item.y,70);assert.equal(node.style.left,'60%');assert.equal(node.style.top,'70%');
assert.equal(saved,savedAfterCommit+1);assert.match(hint.textContent,/Move not saved: disk full.*Previous position restored/);
// A failed pointer persistence attempt also ends the gesture and restores its origin.
handlers.pointerdown({button:0,pointerId:14,preventDefault(){}});
handlers.pointermove({pointerId:14,clientX:80,clientY:85});handlers.pointerup({pointerId:14});
assert.equal(context.drag,null);assert.equal(item.x,60);assert.equal(item.y,70);
assert.equal(node.style.left,'60%');assert.equal(node.style.top,'70%');assert.equal(saved,savedAfterCommit+1);
assert.match(hint.textContent,/Move not saved: disk full.*Previous position restored/);
failSave=false;key('ArrowRight');assert.equal(item.x,61);assert.equal(saved,savedAfterCommit+2);
// Capture refusal leaves no active gesture or changed position.
node.setPointerCapture=()=>{throw Error('capture refused');};
handlers.pointerdown({button:0,pointerId:13,preventDefault(){}});
assert.equal(context.drag,null);assert.equal(item.x,61);assert.equal(saved,savedAfterCommit+2);
assert.match(hint.textContent,/Move could not start/);
console.log('template keyboard and pointer behavior passed');
'''], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
