"""Exercise persist-first server template mutations and refresh failures."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js required for frontend behavior checks")
class TemplateServerActionTests(unittest.TestCase):
    def run_node(self, script):
        result = subprocess.run(
            ["node", "-e", script], cwd=ROOT, text=True, capture_output=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_save_persists_normalized_draft_before_server_mutation(self):
        self.run_node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/stage-template.js','utf8');
const helperStart=source.indexOf('  let persistedName =');
const helperEnd=source.indexOf('  const load =',helperStart);
const actionStart=source.indexOf('  const saveServer =');
const actionEnd=source.indexOf('  const renderStatus =',actionStart);
const code=source.slice(helperStart,helperEnd)+source.slice(actionStart,actionEnd)+'\nthis.saveServer=saveServer;';
const original=[{id:'lead',type:'performer',label:'Lead',x:50,y:40}];
const name={value:'  Renamed tour  '},hint={};let disk,apiCalls=0,renders=0,refreshes=0,failWrite=false;
const context={objects:original,selectedId:'lead',drag:null,serverTemplateId:'server-old',serverRevision:2,serverDirty:false,storageKey:'draft',
  q:selector=>selector==='#templateName'?name:hint,
  localStorage:{setItem:(key,value)=>{assert.equal(key,'draft');if(failWrite)throw Error('disk full');disk=JSON.parse(value);}},
  api:async(method,path,body)=>{apiCalls++;assert.equal(method,'PATCH');assert.equal(path,'/api/v1/templates/server-old');
    assert.equal(body.expectedRevision,2);assert.equal(body.document.name,'Renamed tour');assert.equal(context.serverDirty,true);
    assert.equal(name.value,'Renamed tour');return {templateId:'server-old',revision:3};},
  refreshSaved:async id=>{refreshes++;assert.equal(id,'server-old');throw Error('library offline');},render:()=>renders++};
vm.runInNewContext(code,context);
(async()=>{
  await context.saveServer();assert.equal(apiCalls,1);assert.equal(refreshes,1);assert.equal(renders,1);
  assert.deepEqual(disk,{version:1,name:'Renamed tour',objects:original});assert.equal(name.value,'Renamed tour');
  assert.equal(context.serverTemplateId,'server-old');assert.equal(context.serverRevision,3);assert.equal(context.serverDirty,false);
  assert.match(hint.textContent,/Saved revision 3.*list refresh failed: library offline/);
  name.value='  Unsaved change  ';failWrite=true;
  await assert.rejects(context.saveServer(),/disk full/);assert.equal(apiCalls,1);assert.equal(refreshes,1);assert.equal(renders,1);
  assert.equal(name.value,'Renamed tour');assert.equal(context.serverRevision,3);assert.equal(context.serverDirty,false);
  context.drag={id:'lead',pointerId:4,x:50,y:40};failWrite=false;
  await assert.rejects(context.saveServer(),/finish or cancel the active object move/);
  assert.equal(apiCalls,1);assert.equal(refreshes,1);assert.equal(renders,1);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')

    def test_delete_commits_state_even_when_library_refresh_fails(self):
        self.run_node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/stage-template.js','utf8');
const helperStart=source.indexOf('  let persistedName =');
const helperEnd=source.indexOf('  const load =',helperStart);
const start=source.indexOf('  const deleteServer =');
const end=source.indexOf('  const renderStatus =',start);
const code=source.slice(helperStart,helperEnd)+source.slice(start,end)+'\nthis.deleteServer=deleteServer;';
const select={value:'server-old'},hint={};let apiCalls=0,refreshes=0,renders=0,failDelete=false;
const context={objects:[],selectedId:null,drag:null,storageKey:'draft',serverTemplateId:'server-old',serverRevision:4,serverDirty:true,
  localStorage:{setItem:()=>{}},
  q:selector=>selector==='#templateSaved'?select:hint,
  api:async(method,path,body)=>{apiCalls++;assert.equal(method,'DELETE');
    if(failDelete){assert.equal(path,'/api/v1/templates/server-new');assert.equal(body.expectedRevision,1);throw Error('conflict');}
    assert.equal(path,'/api/v1/templates/server-old');assert.equal(body.expectedRevision,4);return {deleted:true};},
  refreshSaved:async id=>{refreshes++;assert.equal(id,'');throw Error('library offline');},render:()=>renders++};
vm.runInNewContext(code,context);
(async()=>{
  await context.deleteServer();assert.equal(apiCalls,1);assert.equal(refreshes,1);assert.equal(renders,1);
  assert.equal(context.serverTemplateId,null);assert.equal(context.serverRevision,null);assert.equal(context.serverDirty,false);
  assert.equal(select.value,'');assert.match(hint.textContent,/Saved template deleted.*list refresh failed: library offline/);
  context.serverTemplateId='server-new';context.serverRevision=1;context.serverDirty=false;select.value='server-new';failDelete=true;
  await assert.rejects(context.deleteServer(),/conflict/);assert.equal(context.serverTemplateId,'server-new');
  assert.equal(context.serverRevision,1);assert.equal(select.value,'server-new');assert.equal(refreshes,1);assert.equal(renders,1);
  failDelete=false;context.drag={id:'lead',pointerId:7};
  await assert.rejects(context.deleteServer(),/finish or cancel the active object move/);assert.equal(apiCalls,2);
})().catch(error=>{console.error(error);process.exitCode=1;});
''')

    def test_pending_server_action_serializes_editor_mutations(self):
        self.run_node(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/stage-template.js','utf8');
const helperStart=source.indexOf('  let persistedName =');
const helperEnd=source.indexOf('  const load =',helperStart);
const loadStart=source.indexOf('  const loadSaved =');
const loadEnd=source.indexOf('  const renderStatus =',loadStart);
const code=source.slice(helperStart,helperEnd)+source.slice(loadStart,loadEnd)+
  '\nthis.loadSaved=loadSaved;this.saveServer=saveServer;this.deleteServer=deleteServer;this.assertEditorAvailable=assertEditorAvailable;';
const original=[{id:'lead',type:'performer',label:'Lead',x:50,y:40}];
const name={value:'Tour'},hint={},saved={value:'server-old'},deleteButton={disabled:false};
let release,apiCalls=0,writes=0,renders=0;
const response=new Promise(resolve=>release=resolve);
const context={objects:original,selectedId:'lead',drag:null,serverTemplateId:'server-old',serverRevision:2,serverDirty:true,storageKey:'draft',
  q:selector=>selector==='#templateName'?name:selector==='#templateSaved'?saved:selector==='#templateDeleteServer'?deleteButton:hint,
  localStorage:{setItem:()=>writes++},
  api:async()=>{apiCalls++;return response;},refreshSaved:async()=>[],render:()=>renders++};
vm.runInNewContext(code,context);
(async()=>{
  const first=context.saveServer();await Promise.resolve();
  assert.equal(apiCalls,1);assert.equal(writes,1);assert.equal(renders,0);
  await assert.rejects(context.saveServer(),/wait for server save to finish/);
  await assert.rejects(context.loadSaved('server-new'),/wait for server save to finish/);
  await assert.rejects(context.deleteServer(),/wait for server save to finish/);
  assert.throws(()=>context.assertEditorAvailable('adding an object'),/wait for server save to finish/);
  assert.equal(apiCalls,1);assert.equal(writes,1);assert.equal(context.serverRevision,2);
  release({templateId:'server-old',revision:3});await first;
  assert.equal(context.serverRevision,3);assert.equal(context.serverDirty,false);assert.equal(renders,1);
  assert.doesNotThrow(()=>context.assertEditorAvailable('adding an object'));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')


if __name__ == "__main__":
    unittest.main()
