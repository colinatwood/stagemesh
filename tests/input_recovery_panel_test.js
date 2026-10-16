const assert = require('node:assert/strict');
require('../frontend/input-recovery.js');
const {describe, create} = globalThis.StageMeshInputRecovery;
function report({active=false, connected=true, desired='boom', gain=0}={}) {
  return {available:true, devices:connected ? [{name:'BOOM', connected:true, input:true, desiredInputSlots:[0]}] : [],
    inputs:[{slot:0, available:true, active, desiredConnected:connected, desiredDeviceId:desired, route:{output:0,gain}}]};
}
function harness() {
  let next = report(), writes = [], failure = null, confirm = true, hold = null;
  const status = {}, button = {disabled:true, addEventListener(){}};
  const controller = create({status,button,getPolicy:()=>({}),confirmRoute:()=>confirm,onRecovered:async()=>{},
    request:async(path, options) => {
      if (options?.method !== 'POST') { if (hold) return hold; return next; }
      writes.push({path, body:JSON.parse(options.body)});
      if (failure) throw new Error(failure);
      return {active:true};
    }});
  return {status,button,controller,writes,set(value){next=value;},fail(value){failure=value;},confirm(value){confirm=value;},hold(value){hold=value;}};
}
(async () => {
  const h = harness();
  h.set(report({active:true})); await h.controller.poll();
  assert.match(h.status.textContent,/BOOM.*Capture active/); assert.equal(h.button.disabled,true);
  h.set(report({connected:false})); await h.controller.poll();
  assert.match(h.status.textContent,/disconnected/); assert.equal(h.button.disabled,true);
  h.set(report()); await h.controller.poll();
  assert.equal(h.button.textContent,'Reconnect input'); assert.equal(h.button.disabled,false);
  assert.equal(h.writes.length,0); // Polling never activates or recovers.
  await h.controller.connect();
  assert.equal(h.writes.length,1); assert.equal(h.button.disabled,true);
  assert.equal(h.writes[0].path,'/api/v1/audio/input/recover');
  assert.equal(h.writes[0].body.expectedDeviceId,'boom');
  assert.deepEqual(h.writes[0].body.expectedRoute,{output:0,gain:0});
  assert.equal(h.writes[0].body.acknowledgeSignalRoute,false);
  h.set(report({connected:false})); await h.controller.poll();
  assert.match(h.status.textContent,/disconnected/); // Success must not mask the next loss.

  const other = report(); other.devices[0].desiredInputSlots = [];
  assert.equal(describe(other).canConnect,false); // Another connected input cannot substitute.
  const ambiguous = report(); ambiguous.devices.push({...ambiguous.devices[0]});
  assert.equal(describe(ambiguous).canConnect,false);
  assert.equal(describe({available:false}).canConnect,false);

  const stale = harness(); await stale.controller.poll(); stale.set(report({desired:'other'}));
  await stale.controller.connect(); assert.equal(stale.writes.length,0);
  assert.match(stale.status.textContent,/Selected input changed/);

  const routed = harness(); routed.set(report({gain:1})); await routed.controller.poll();
  routed.confirm(false); await routed.controller.connect(); assert.equal(routed.writes.length,0);
  routed.confirm(true); await routed.controller.connect();
  assert.equal(routed.writes[0].body.acknowledgeSignalRoute,true);

  const failed = harness(); await failed.controller.poll(); failed.fail('endpoint absent');
  await failed.controller.connect(); await failed.controller.poll();
  assert.match(failed.status.textContent,/connection failed.*endpoint absent/);
  assert.equal(failed.button.disabled,false);

  const pending = harness(); await pending.controller.poll();
  let release; pending.hold(new Promise(resolve=>{release=resolve;}));
  const action = pending.controller.connect(); await pending.controller.connect();
  assert.equal(pending.button.disabled,true); release(report()); await action;
  assert.equal(pending.writes.length,1);

  const oldPoll = harness(); await oldPoll.controller.poll();
  let oldRelease; oldPoll.hold(new Promise(resolve=>{oldRelease=resolve;}));
  const polling = oldPoll.controller.poll(); oldPoll.hold(null);
  await oldPoll.controller.connect(); oldRelease(report()); await polling;
  assert.equal(oldPoll.button.disabled,true); // A pre-click response cannot overwrite recovery.
  assert.match(oldPoll.status.textContent,/Capture active/);
  console.log('Input recovery workflow passed');
})().catch(error=>{ console.error(error); process.exitCode=1; });
