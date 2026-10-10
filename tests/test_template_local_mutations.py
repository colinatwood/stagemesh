"""Exercise persist-first replacement of browser-local template drafts."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js required for frontend behavior checks")
class TemplateLocalMutationTests(unittest.TestCase):
    def run_node(self, script):
        result = subprocess.run(
            ["node", "-e", script], cwd=ROOT, text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_add_delete_reset_and_preset_persist_before_replacing_state(self):
        self.run_node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/stage-template.js','utf8');
const helperStart=source.indexOf('  let persistedName =');
const helperEnd=source.indexOf('  const load =',helperStart);
const selectedStart=source.indexOf('  const selected =');
const selectedEnd=source.indexOf('  const api =',selectedStart);
const presetStart=source.indexOf('  const makeObjects =');
const presetEnd=source.indexOf('  const renderPresets =',presetStart);
const actionStart=source.indexOf('  q("#templateAdd").addEventListener');
const actionEnd=source.indexOf('  q("#templateExport").addEventListener',actionStart);
assert.ok([helperStart,helperEnd,selectedStart,selectedEnd,presetStart,presetEnd,actionStart,actionEnd].every(value=>value>0));
const code=source.slice(helperStart,helperEnd)+source.slice(selectedStart,selectedEnd)+
  source.slice(presetStart,presetEnd)+'\nthis.applyPreset=applyPreset;\n'+source.slice(actionStart,actionEnd);
const handlers={},name={value:'Original'},hint={},type={value:'marker'},label={value:'Added'};
const original=[{id:'old',type:'marker',label:'Existing',x:10,y:20}];
let failWrite=true,disk,renders=0;
const controls={
  '#templateName':name,'#templateHint':hint,'#templateObjectType':type,'#templateObjectLabel':label,
  '#templateAdd':{addEventListener:(kind,callback)=>handlers.add=callback},
  '#templateDelete':{addEventListener:(kind,callback)=>handlers.delete=callback},
  '#templateReset':{addEventListener:(kind,callback)=>handlers.reset=callback}
};
const context={objects:original,selectedId:'old',serverTemplateId:'server-old',serverDirty:false,storageKey:'draft',
  presets:{club:{name:'Club',objects:[["performer","Lead",50,40]]}},q:selector=>controls[selector],
  localStorage:{setItem:(key,value)=>{assert.equal(key,'draft');if(failWrite)throw Error('disk full');disk=JSON.parse(value);}},
  render:()=>renders++};
vm.runInNewContext(code,context);
handlers.add();assert.equal(context.objects,original);assert.equal(context.selectedId,'old');assert.equal(context.serverDirty,false);
assert.equal(renders,0);assert.match(hint.textContent,/Object not added: disk full.*Previous draft preserved/);
handlers.delete();assert.equal(context.objects,original);assert.equal(context.selectedId,'old');assert.equal(renders,0);
assert.match(hint.textContent,/Object not deleted: disk full.*Previous draft preserved/);
handlers.reset();assert.equal(context.objects,original);assert.equal(context.selectedId,'old');assert.equal(renders,0);
assert.match(hint.textContent,/Draft not reset: disk full.*Previous draft preserved/);
context.applyPreset('club');assert.equal(context.objects,original);assert.equal(context.selectedId,'old');assert.equal(renders,0);
assert.match(hint.textContent,/Preset not applied: disk full.*Previous draft preserved/);
failWrite=false;handlers.add();assert.equal(context.objects.length,2);assert.equal(context.objects[0],original[0]);
assert.equal(context.selectedId,context.objects[1].id);assert.equal(context.serverDirty,true);assert.equal(renders,1);
assert.equal(disk.objects.length,2);assert.equal(disk.name,'Original');
handlers.delete();assert.equal(context.objects.length,1);assert.equal(context.objects[0],original[0]);assert.equal(context.selectedId,null);assert.equal(renders,2);
handlers.reset();assert.equal(context.objects.length,0);assert.equal(context.selectedId,null);assert.equal(renders,3);
context.applyPreset('club');assert.equal(context.objects.length,1);assert.equal(context.objects[0].label,'Lead');
assert.equal(context.selectedId,null);assert.equal(renders,4);assert.equal(disk.objects[0].label,'Lead');
console.log('local template mutations are persist-first');
''')

    def test_server_load_preserves_current_draft_when_local_write_fails(self):
        self.run_node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/stage-template.js','utf8');
const helperStart=source.indexOf('  let persistedName =');
const helperEnd=source.indexOf('  const load =',helperStart);
const loadStart=source.indexOf('  const loadSaved =');
const loadEnd=source.indexOf('  const saveServer =',loadStart);
assert.ok(helperStart>0&&helperEnd>helperStart&&loadStart>0&&loadEnd>loadStart);
const code=source.slice(helperStart,helperEnd)+source.slice(loadStart,loadEnd)+'\nthis.loadSaved=loadSaved;';
const original=[{id:'old',type:'marker',label:'Existing',x:10,y:20}];
const incoming={templateId:'server-new',revision:3,name:'Server draft',objects:[{id:'new',type:'performer',label:'Lead',x:50,y:40}]};
const name={value:'Original'},hint={},deleteServer={disabled:true};let failWrite=true,disk,renders=0;
const context={objects:original,selectedId:'old',serverTemplateId:'server-old',serverRevision:2,serverDirty:false,storageKey:'draft',
  q:selector=>selector==='#templateName'?name:selector==='#templateHint'?hint:deleteServer,
  localStorage:{setItem:(key,value)=>{assert.equal(key,'draft');if(failWrite)throw Error('disk full');disk=JSON.parse(value);}},
  api:async()=>incoming,render:()=>renders++};
vm.runInNewContext(code,context);
(async()=>{
  await assert.rejects(context.loadSaved('server-new'),/disk full/);
  assert.equal(context.objects,original);assert.equal(context.selectedId,'old');assert.equal(context.serverTemplateId,'server-old');
  assert.equal(context.serverRevision,2);assert.equal(context.serverDirty,false);assert.equal(name.value,'Original');
  assert.equal(renders,0);assert.equal(disk,undefined);assert.equal(deleteServer.disabled,true);
  failWrite=false;await context.loadSaved('server-new');
  assert.equal(context.objects,incoming.objects);assert.equal(context.selectedId,null);assert.equal(context.serverTemplateId,'server-new');
  assert.equal(context.serverRevision,3);assert.equal(context.serverDirty,false);assert.equal(name.value,'Server draft');
  assert.equal(renders,1);assert.equal(deleteServer.disabled,false);assert.deepEqual(disk,{version:1,name:'Server draft',objects:incoming.objects});
  assert.match(hint.textContent,/Loaded server revision 3/);
  console.log('server load persists before replacing local draft');
})().catch(error=>{console.error(error);process.exitCode=1;});
''')


if __name__ == "__main__":
    unittest.main()
