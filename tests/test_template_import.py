"""Exercise template import validation and replacement with real JS callbacks."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js required for frontend behavior checks")
class TemplateImportTests(unittest.TestCase):
    def test_import_preserves_components_or_rejects_the_whole_replacement(self):
        result = subprocess.run(["node", "-e", r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('frontend/stage-template.js', 'utf8');
const validatorStart = source.indexOf('  const validateTemplateDocument =');
const validatorEnd = source.indexOf('  const save =', validatorStart);
const importStart = source.indexOf('  q("#templateImport").addEventListener');
const importEnd = source.indexOf('  canvas.addEventListener("dragover"', importStart);
const code = source.slice(validatorStart, validatorEnd) + source.slice(importStart, importEnd);
assert.ok(code.includes('validateTemplateDocument') && code.includes('Template imported'), 'import callback must exist');
const original = [{id:'old',type:'marker',label:'Existing',x:10,y:20}];
const name = {value:'Existing draft'};
const hint = {};
let handler, disk, failWrite=false, renders=0;
const context = {objects:original, selectedId:'old', drag:null, serverTemplateId:'server-old', serverDirty:false, storageKey:'draft',
  q: selector => selector === '#templateName' ? name : selector === '#templateHint' ? hint : {addEventListener:(type,callback)=>{assert.equal(type,'change');handler=callback;}},
  localStorage: {setItem:(key,value)=>{if(failWrite)throw Error('disk full');disk=value;}}, render:()=>renders++};
vm.runInNewContext(code, context);
async function importValue(value) {
  const target={files:[{text:async()=>typeof value==='string'?value:JSON.stringify(value)}],value:'selected.json'};
  await handler({target}); assert.equal(target.value,'');
}
const valid={version:1,name:'Imported tour',objects:[{id:'lead',type:'performer',label:'L'.repeat(80),x:0,y:100,metadata:{instrument:'bass'}},{id:'light',type:'light',label:'Wash',x:75,y:12}]};
const invalid=[
  '{broken', {...valid,version:2}, {...valid,objects:[valid.objects[0],null]},
  {...valid,objects:[valid.objects[0],{...valid.objects[1],id:'lead'}]},
  {...valid,objects:[{...valid.objects[0],x:'0'}]}, {...valid,objects:[{...valid.objects[0],y:null}]},
  {...valid,objects:[{...valid.objects[0],x:101}]}, {...valid,objects:[{...valid.objects[0],label:'L'.repeat(129)}]},
  {...valid,name:''}, {...valid,objects:Array(5001).fill(valid.objects[0])}
];
(async()=>{
  for(const value of invalid) {
    await importValue(value); assert.match(hint.textContent,/Import rejected:/);
    assert.equal(context.objects,original);assert.equal(context.selectedId,'old');assert.equal(name.value,'Existing draft');
    assert.equal(context.serverDirty,false);assert.equal(disk,undefined);assert.equal(renders,0);
  }
  failWrite=true; await importValue(valid); assert.match(hint.textContent,/disk full/);
  assert.equal(context.objects,original);assert.equal(name.value,'Existing draft');assert.equal(context.serverDirty,false);
  failWrite=false; await importValue(valid);
  assert.equal(context.objects.length,2);assert.equal(context.objects[0].x,0);assert.equal(context.objects[0].label.length,80);
  assert.equal(context.objects[0].metadata.instrument,'bass');assert.equal(context.objects[1].id,'light');
  assert.equal(name.value,'Imported tour');assert.equal(context.selectedId,null);assert.equal(context.serverDirty,true);
  assert.deepEqual(JSON.parse(disk),valid);assert.equal(renders,1);
  await importValue({version:1,objects:[{label:'Defaults'}]});
  assert.equal(context.objects[0].x,50);assert.equal(context.objects[0].type,'marker');assert.ok(context.objects[0].id);
  assert.equal(name.value,'Imported tour');
  console.log('template import preservation passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_import_read_serializes_against_overlapping_replacements(self):
        result = subprocess.run(["node", "-e", r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/stage-template.js','utf8');
const validatorStart=source.indexOf('  const validateTemplateDocument =');
const validatorEnd=source.indexOf('  const save =',validatorStart);
const importStart=source.indexOf('  q("#templateImport").addEventListener');
const importEnd=source.indexOf('  canvas.addEventListener("dragover"',importStart);
const code=source.slice(validatorStart,validatorEnd)+source.slice(importStart,importEnd);
const original=[{id:'old',type:'marker',label:'Existing',x:10,y:20}];
const incoming={version:1,name:'Imported',objects:[{id:'new',type:'performer',label:'Lead',x:50,y:40}]};
const name={value:'Original'},hint={};let handler,release,writes=0,renders=0;
const context={objects:original,selectedId:'old',drag:null,serverTemplateId:null,serverDirty:false,storageKey:'draft',
  q:selector=>selector==='#templateName'?name:selector==='#templateHint'?hint:{addEventListener:(type,callback)=>handler=callback},
  localStorage:{setItem:()=>writes++},render:()=>renders++};
vm.runInNewContext(code,context);
const firstTarget={files:[{text:()=>new Promise(resolve=>release=resolve)}],value:'first.json'};
const blockedTarget=()=>({files:[{text:async()=>JSON.stringify(incoming)}],value:'blocked.json'});
(async()=>{
  const first=handler({target:firstTarget});await Promise.resolve();
  const second=blockedTarget();await handler({target:second});
  assert.match(hint.textContent,/wait for template import to finish/);assert.equal(second.value,'');
  const third=blockedTarget();await handler({target:third});
  assert.match(hint.textContent,/wait for template import to finish/);assert.equal(third.value,'');
  assert.equal(writes,0);assert.equal(renders,0);assert.equal(context.objects,original);
  release(JSON.stringify(incoming));await first;
  assert.equal(firstTarget.value,'');assert.equal(writes,1);assert.equal(renders,1);
  assert.equal(context.objects[0].id,'new');assert.equal(name.value,'Imported');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_draft_load_uses_strict_validation_without_rewriting_source(self):
        result = subprocess.run(["node", "-e", r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('frontend/stage-template.js', 'utf8');
const start = source.indexOf('  const validateTemplateDocument =');
const end = source.indexOf('  const selected =', start);
assert.ok(start > 0 && end > start, 'local draft loader must exist');
const code = source.slice(start, end) + '\nthis.loadDraft = load;';
function run(raw) {
  const name = {value:'Default name'}, hint = {};
  let writes = 0;
  const context = {objects:[{id:'before'}], serverTemplateId:null, serverDirty:false, storageKey:'draft',
    q: selector => selector === '#templateName' ? name : hint,
    localStorage:{getItem:key=>{assert.equal(key,'draft');return raw;},setItem:()=>writes++}};
  vm.runInNewContext(code, context); context.loadDraft();
  return {objects:context.objects,name:name.value,hint:hint.textContent,writes};
}
const valid = {version:1,name:'Recovered tour',objects:[
  {id:'lead',type:'performer',label:'Lead',x:0,y:100,metadata:{instrument:'bass'}},
  {id:'wash',type:'light',label:'Wash',x:75,y:12}
]};
let result = run(JSON.stringify(valid));
assert.equal(result.objects.length,2);assert.equal(result.objects[0].metadata.instrument,'bass');
assert.equal(result.name,'Recovered tour');assert.equal(result.hint,undefined);assert.equal(result.writes,0);
const invalid = [
  '{broken', JSON.stringify({...valid,version:2}),
  JSON.stringify({...valid,objects:[valid.objects[0],{...valid.objects[1],id:'lead'}]}),
  JSON.stringify({...valid,objects:[{label:'Missing internal fields'}]}),
  JSON.stringify({...valid,objects:[{...valid.objects[0],x:'0'}]}),
  JSON.stringify({...valid,objects:Array(5001).fill(valid.objects[0])})
];
for (const raw of invalid) {
  result=run(raw);assert.equal(result.objects.length,0);assert.equal(result.name,'Default name');
  assert.match(result.hint,/Local draft rejected:.*Stored data was preserved for recovery\./);
  assert.equal(result.writes,0);
}
result=run(null);assert.deepEqual(result.objects,[{id:'before'}]);assert.equal(result.hint,undefined);assert.equal(result.writes,0);
console.log('local template load validation passed');
'''], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
