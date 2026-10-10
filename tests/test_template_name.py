"""Run the actual template-name callback and persistence helpers in Node."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/stage-template.js','utf8');
const helperStart=source.indexOf('  const validateTemplateDocument =');
const helperEnd=source.indexOf('  const selected =',helperStart);
const statusStart=source.indexOf('  const renderStatus =');
const statusEnd=source.indexOf('  const render =',statusStart);
const nameStart=source.indexOf('  q("#templateName").addEventListener');
const nameEnd=source.indexOf('  q("#templateSaved").addEventListener',nameStart);
const loadStart=source.indexOf('  const loadSaved =');
const loadEnd=source.indexOf('  const saveServer =',loadStart);
assert.ok([helperStart,helperEnd,statusStart,statusEnd,nameStart,nameEnd,loadStart,loadEnd].every(value=>value>0));
const code=source.slice(helperStart,helperEnd)+source.slice(statusStart,statusEnd)+
  source.slice(loadStart,loadEnd)+source.slice(nameStart,nameEnd)+
  '\nthis.loadDraft=load;this.loadSaved=loadSaved;this.replaceDraft=replaceLocalDraft;';
function setup({raw=null,serverId='server-old'}={}) {
  let handler,writes=0,renders=0,failWrite=false,reads=0,disk=raw,incoming;
  const original=[{id:'old',type:'marker',label:'Existing',x:10,y:20}];
  const name={value:'Original',addEventListener:(kind,callback)=>{assert.equal(kind,'change');handler=callback;}};
  const hint={},status={},deleteServer={disabled:true};
  const controls={'#templateName':name,'#templateHint':hint,'#templateStatus':status,'#templateDeleteServer':deleteServer};
  const context={objects:original,selectedId:'old',serverTemplateId:serverId,serverRevision:2,serverDirty:false,storageKey:'draft',
    q:selector=>{assert.ok(controls[selector],selector);return controls[selector];},
    localStorage:{getItem:()=>disk,setItem:(key,value)=>{assert.equal(key,'draft');if(failWrite)throw Error('disk full');disk=value;writes++;}},
    render:()=>renders++,api:async()=>{reads++;return incoming;}};
  vm.runInNewContext(code,context);context.loadDraft();
  return {context,original,name,hint,status,rename:value=>{name.value=value;handler();},
    fail:value=>failWrite=value,incoming:value=>incoming=value,
    writes:()=>writes,renders:()=>renders,reads:()=>reads,disk:()=>disk};
}
'''


@unittest.skipUnless(shutil.which("node"), "Node.js required for frontend behavior checks")
class TemplateNameTests(unittest.TestCase):
    def run_node(self, script):
        result = subprocess.run(
            ["node", "-e", HARNESS + script], cwd=ROOT, text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rename_survives_reload_and_marks_server_revision_unsaved(self):
        self.run_node(r'''
const run=setup();run.rename('Tour & lights');
assert.equal(run.writes(),1);assert.equal(run.context.serverDirty,true);
assert.equal(run.context.serverTemplateId,'server-old');assert.equal(run.context.serverRevision,2);
assert.equal(run.context.objects,run.original);assert.equal(run.context.selectedId,'old');
assert.equal(run.renders(),0);assert.equal(run.reads(),0);
assert.match(run.status.textContent,/SERVER r2 · UNSAVED/);
assert.match(run.hint.textContent,/Template name saved to this local draft/);
const saved=JSON.parse(run.disk());assert.equal(saved.name,'Tour & lights');assert.deepEqual(saved.objects,run.original);
const reloaded=setup({raw:run.disk(),serverId:null});assert.equal(reloaded.name.value,'Tour & lights');
assert.deepEqual(JSON.parse(JSON.stringify(reloaded.context.objects)),run.original);
reloaded.rename('Local only');assert.equal(reloaded.context.serverDirty,false);
assert.match(reloaded.status.textContent,/LOCAL DRAFT/);
''')

    def test_refused_and_invalid_rename_preserve_committed_name_and_draft(self):
        self.run_node(r'''
const run=setup();run.fail(true);run.rename('Refused');
assert.equal(run.name.value,'Original');assert.equal(run.context.serverDirty,false);
assert.equal(run.writes(),0);assert.equal(run.disk(),null);
assert.match(run.hint.textContent,/Name not saved: disk full.*Previous name restored/);
run.fail(false);run.rename('N'.repeat(128));assert.equal(run.writes(),1);
const saved=run.disk();
for(const invalid of ['', '   ', 'N'.repeat(129)]) {
  run.rename(invalid);assert.equal(run.name.value,'N'.repeat(128));assert.equal(run.disk(),saved);
  assert.equal(run.writes(),1);assert.match(run.hint.textContent,/Name not saved: template name must contain/);
}
run.fail(true);run.rename('Another refusal');assert.equal(run.name.value,'N'.repeat(128));
assert.equal(run.disk(),saved);assert.equal(run.context.serverDirty,true);
assert.equal(run.context.objects,run.original);assert.equal(run.context.selectedId,'old');
assert.equal(run.renders(),0);assert.equal(run.reads(),0);
run.fail(false);run.rename('Recovered');assert.equal(run.writes(),2);
assert.equal(JSON.parse(run.disk()).name,'Recovered');
''')

    def test_rollback_name_tracks_restored_and_replaced_drafts(self):
        self.run_node(r'''
const raw=JSON.stringify({version:1,name:'Restored',objects:[{id:'a',type:'marker',label:'A',x:0,y:100}]});
const run=setup({raw});run.fail(true);run.rename('Refused');
assert.equal(run.name.value,'Restored');assert.equal(run.disk(),raw);assert.equal(run.writes(),0);
run.fail(false);run.context.replaceDraft(run.original,null,'Imported');
run.fail(true);run.rename('Refused again');assert.equal(run.name.value,'Imported');
run.fail(false);run.incoming({templateId:'server-new',revision:5,name:'Loaded server',objects:run.original});
(async()=>{
  await run.context.loadSaved('server-new');
  const serverDisk=run.disk();run.fail(true);run.rename('Refused server rename');
  assert.equal(run.name.value,'Loaded server');assert.equal(run.disk(),serverDisk);
  assert.equal(run.context.serverDirty,false);assert.equal(run.context.serverTemplateId,'server-new');
  assert.equal(run.context.serverRevision,5);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')


if __name__ == "__main__":
    unittest.main()
