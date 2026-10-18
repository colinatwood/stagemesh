"""Review must refuse unknown or live output state before saving a setup baseline."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js required for UI behavior checks")
class SetupReviewTests(unittest.TestCase):
    def test_review_rejects_unknown_active_or_unmuted_baselines(self):
        result = subprocess.run(["node", "-e", r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const context={};vm.runInNewContext(fs.readFileSync('frontend/setup-wizard.js','utf8'),context);
const review=context.StageMeshSetup.review;
const baseline=()=>({native:{available:true},audio:{available:true,desiredInputDeviceId:'in',desiredDeviceId:'out',devices:[{id:'in',input:true,connected:true},{id:'out',output:true,connected:true}]},state:{audio:{inputRoute:{gain:0}}},inputs:{inputs:[{active:false}]},outputs:{outputs:[{active:false}]},lighting:{armed:false},midi:{available:true,bindings:{midi:'lead'},devices:[{id:'midi',connected:true}]}});
assert.equal(review(baseline()).ready,true);
for(const change of [d=>d.native.available=false,d=>d.audio.available=false,d=>d.inputs=null,d=>d.outputs={},d=>d.inputs.inputs[0].active=true,d=>delete d.inputs.inputs[0].active,d=>d.outputs.outputs[0].active=true,d=>d.lighting.armed=true,d=>delete d.lighting.armed,d=>d.state.audio.inputRoute.gain=1,d=>d.state.audio.inputRoute.gain='0',d=>d.audio.devices[0].connected=false,d=>d.midi.available=false,d=>d.midi.bindings={}]){
 const data=baseline();change(data);assert.equal(review(data).ready,false);
}
const skipped=baseline();skipped.audio.devices=[];skipped.midi.available=false;
assert.equal(review(skipped,new Set(['input','output','midi','lighting'])).ready,true);
assert.equal(review({},new Set(['input','output','midi','lighting'])).ready,false);
const ambiguous=baseline();ambiguous.audio.devices.push({...ambiguous.audio.devices[0]});assert.equal(review(ambiguous).ready,false);
const missingMidi=baseline();missingMidi.midi.devices[0].connected=false;assert.equal(review(missingMidi).ready,false);
console.log('Setup baseline fail-closed review passed');
'''], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_setup_configuration_bridge_propagates_conflicts_and_errors(self):
        result = subprocess.run(["node", "-e", r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync('frontend/app.js','utf8');
const start=source.indexOf('  async function command('),end=source.indexOf('  function connectEvents()',start);
assert.ok(start>0&&end>start);
let failure=null;const current={revision:2};
const context={snapshot:{revision:1,resourceRevisions:{audio:1}},commandId:()=> 'command',api:async()=>{if(failure)throw failure;return current;},render:()=>{},refreshPlan:()=>{},refreshNative:()=>{},refreshNodeStatus:()=>{},refreshClockStatus:()=>{},refreshAudioDevices:()=>{},refreshAudioStream:()=>{},refreshAudioInput:()=>{},refreshLightingNetwork:()=>{},refreshTechnologyOpenness:()=>{},eventStream:null,q:()=>({}),console:{error:()=>{}}};
vm.runInNewContext(source.slice(start,end)+'\nthis.command=command;',context);
(async()=>{
 assert.equal(await context.command('/api/v1/audio','POST',{},'audio',{throwOnFailure:true}),current);
 for(const status of [409,403,500]){
  failure=Object.assign(Error('refused'),{status,data:{current}});
  await assert.rejects(context.command('/api/v1/audio','POST',{},'audio',{throwOnFailure:true}),/refused/);
 }
 failure=Object.assign(Error('conflict'),{status:409,data:{current}});
 assert.equal(await context.command('/api/v1/audio','POST',{},'audio'),current);
 context.snapshot=null;failure=null;
 await assert.rejects(context.command('/api/v1/audio','POST',{},'audio',{throwOnFailure:true}),/current show state/);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
