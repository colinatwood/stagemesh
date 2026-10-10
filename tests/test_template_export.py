"""Exercise validated, read-only stage-template export behavior."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js required for frontend behavior checks")
class TemplateExportTests(unittest.TestCase):
    def test_export_refuses_transient_state_and_remains_available_without_storage(self):
        result = subprocess.run(["node", "-e", r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/stage-template.js','utf8');
const helperStart=source.indexOf('  const validateTemplateDocument =');
const helperEnd=source.indexOf('  const load =',helperStart);
const exportStart=source.indexOf('  q("#templateExport").addEventListener');
const exportEnd=source.indexOf('  q("#templateImportButton").addEventListener',exportStart);
const code=source.slice(helperStart,helperEnd)+source.slice(exportStart,exportEnd)+
  '\nthis.beginAction=beginAsyncAction;this.endAction=endAsyncAction;';
const original=[{id:'lead',type:'performer',label:'Lead',x:50,y:40}];
const name={value:'Committed'},hint={},status={};let handler,writes=0,disk,clicks=0,failWrite=false,blobParts,revoke;
const context={objects:original,selectedId:'lead',drag:null,serverTemplateId:'server-old',serverRevision:2,serverDirty:false,storageKey:'draft',
  q:selector=>selector==='#templateName'?name:selector==='#templateHint'?hint:selector==='#templateStatus'?status:
    {addEventListener:(type,callback)=>handler=callback},
  localStorage:{setItem:(key,value)=>{if(failWrite)throw Error('disk full');writes++;disk=value;}},
  renderStatus:()=>{status.renders=(status.renders||0)+1;},
  Blob:function(parts,options){blobParts=parts;this.options=options;},
  URL:{createObjectURL:()=> 'blob:export',revokeObjectURL:value=>revoke=value},
  document:{createElement:()=>({click:()=>clicks++})}};
vm.runInNewContext(code,context);
context.drag={id:'lead',pointerId:7,x:50,y:40};original[0].x=75;name.value='During drag';handler();
assert.equal(writes,0);assert.equal(clicks,0);assert.match(hint.textContent,/finish or cancel the active object move/);
original[0].x=50;context.drag=null;
const operation=context.beginAction('server load');name.value='During load';handler();context.endAction(operation);
assert.equal(writes,0);assert.equal(clicks,0);assert.match(hint.textContent,/wait for server load to finish/);
name.value='   ';handler();assert.equal(writes,0);assert.equal(clicks,0);
assert.match(hint.textContent,/template name must contain/);
failWrite=true;name.value='Tour export';handler();assert.equal(writes,0);assert.equal(clicks,1);
assert.match(hint.textContent,/Template export download requested/);
failWrite=false;name.value='Tour export';handler();assert.equal(writes,0);assert.equal(clicks,2);assert.equal(revoke,'blob:export');
assert.equal(context.serverDirty,false);assert.equal(status.renders,undefined);assert.match(hint.textContent,/Template export download requested/);
assert.equal(disk,undefined);const downloaded=JSON.parse(blobParts[0]);
assert.deepEqual(downloaded,{version:1,name:'Tour export',objects:original});
context.objects=[{...original[0],x:101}];handler();assert.equal(clicks,2);assert.equal(writes,0);
assert.match(hint.textContent,/coordinates must be finite/);context.objects=original;
context.document.createElement=()=>({click:()=>{throw Error('download refused');}});revoke=null;handler();
assert.equal(revoke,'blob:export');assert.equal(writes,0);assert.equal(context.serverDirty,false);
assert.match(hint.textContent,/Export could not start: download refused.*Local draft preserved/);
'''], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
