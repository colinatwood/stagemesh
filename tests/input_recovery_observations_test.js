const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
require('../frontend/input-recovery.js');
function report({active=true, connected=true, desired='boom', callbacks=100, gain=0}={}) {
  return {available:true, devices:connected ? [{name:'BOOM', connected:true, input:true, desiredInputSlots:[0]}] : [],
    inputs:[{slot:0, available:true, active, desiredConnected:connected, desiredDeviceId:desired,
      deviceId:`${desired}-native`, executionBackend:'wasapi', route:{output:0,gain}, callbacks,
      configuredSampleRate:192000,configuredChannels:2,configuredPeriodFrames:256,configuredSampleFormat:'FLOAT_LE',
      xruns:0,droppedFrames:0,queuedFrames:0}]};
}
function harness() {
  let next=report(), clock=0, writes=0, announcements=0, failure=null;
  const status={value:'',get textContent(){return this.value;},set textContent(v){this.value=v; ++announcements;}},
    button={disabled:true,addEventListener(){}}, metrics={};
  const controller=globalThis.StageMeshInputRecovery.create({status,button,metrics,now:()=>clock,
    getPolicy:()=>({}),confirmRoute:()=>{clock+=20000; return true;},onRecovered:async()=>{},
    request:async(path,options)=>{
      if(options?.method==='POST'){++writes; clock+=300; return {active:true};}
      if(failure) throw new Error(failure);
      return next;
    }});
  return {status,button,metrics,controller,set:v=>{next=v;},at:v=>{clock=v;},fail:v=>{failure=v;},
    get writes(){return writes;},get announcements(){return announcements;}};
}
(async()=>{
  const h=harness(); await h.controller.poll();
  assert.match(h.metrics.textContent,/192000 Hz \/ 2 channels \/ 256 frames/);
  assert.match(h.metrics.textContent,/waiting for a second active sample/);
  const announcements=h.announcements;
  h.set(report({callbacks:120})); await h.controller.poll();
  assert.match(h.metrics.textContent,/increased by 20/);
  assert.equal(h.announcements,announcements); // Counters do not repeatedly announce primary status.
  await h.controller.poll(); assert.match(h.metrics.textContent,/unchanged since last sample/);
  h.set(report({callbacks:1})); await h.controller.poll(); assert.match(h.metrics.textContent,/counter reset/);

  h.at(1000); h.set(report({active:false,connected:false})); await h.controller.poll();
  h.at(9000); await h.controller.poll(); assert.match(h.metrics.textContent,/8\.0 s since first unverified/);
  h.at(14000); h.set(report({active:false,callbacks:999,gain:1})); await h.controller.poll();
  assert.match(h.metrics.textContent,/Observed input return: 13\.0 s between UI samples/);
  assert.equal(h.writes,0);
  await h.controller.connect();
  assert.equal(h.writes,1);
  assert.match(h.metrics.textContent,/Last connect response: 0\.3 s/); // Excludes route confirmation wait.
  assert.match(h.metrics.textContent,/Waiting for a fresh input status sample/);
  assert.doesNotMatch(h.metrics.textContent,/999/); // Activation response cannot reuse pre-rearm counters.
  h.set(report({callbacks:4})); await h.controller.poll();
  assert.match(h.metrics.textContent,/waiting for a second active sample/);
  h.set(report({callbacks:9})); await h.controller.poll(); assert.match(h.metrics.textContent,/increased by 5/);

  h.fail('offline'); await h.controller.poll();
  assert.equal(h.button.disabled,true); assert.match(h.metrics.textContent,/previous readings are stale/);
  assert.doesNotMatch(h.metrics.textContent,/increased|192000/);
  h.fail(null); await h.controller.poll(); assert.match(h.metrics.textContent,/waiting for a second active sample/);
  assert.doesNotMatch(h.metrics.textContent,/Observed input return/);
  h.set(report({desired:'other',callbacks:200})); await h.controller.poll();
  assert.doesNotMatch(h.metrics.textContent,/Last connect response/);
  assert.match(h.metrics.textContent,/waiting for a second active sample/);
  const unknown=report(); Object.assign(unknown.inputs[0],{callbacks:NaN,xruns:undefined,configuredSampleRate:0});
  h.set(unknown); await h.controller.poll();
  assert.match(h.metrics.textContent,/Callback activity unverified/);
  assert.match(h.metrics.textContent,/configured unreported Hz/);
  assert.match(h.metrics.textContent,/xruns: unreported/);
  unknown.inputs[0].available=false; h.set(unknown); await h.controller.poll();
  assert.match(h.metrics.textContent,/previous readings are stale/);

  let timer=null, held=false, reads=0;
  const sandbox={AbortController,performance:{now:()=>0},
    setTimeout(callback,delay){assert.equal(delay,6000); timer=callback; return 1;},clearTimeout(){timer=null;}};
  vm.createContext(sandbox); vm.runInContext(fs.readFileSync('frontend/input-recovery.js','utf8'),sandbox);
  const status={},metrics={},button={disabled:true,addEventListener(){}};
  const controller=sandbox.StageMeshInputRecovery.create({status,metrics,button,getPolicy:()=>({}),confirmRoute:()=>true,onRecovered:async()=>{},
    request:async(path,options)=>{++reads; assert.notEqual(options.method,'POST');
      if(held) return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('timed out'))));
      return report();}});
  await controller.poll(); held=true;
  const pending=controller.poll(); await controller.poll(); assert.equal(reads,2);
  timer(); await pending;
  assert.equal(button.disabled,true); assert.match(metrics.textContent,/previous readings are stale/);
  held=false; await controller.poll(); assert.match(metrics.textContent,/waiting for a second active sample/);
  assert.equal(timer,null);
  console.log('Input recovery observations passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
