const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('frontend/app.js', 'utf8');
const start = source.indexOf('  let nativeStatusPending = false;');
const end = source.indexOf('  async function refreshNodeStatus()', start);
assert.ok(start >= 0 && end > start);
const elements = new Map();
let writes = 0, reads = 0, result = {available:true}, failure = null, deferred = null, abort;
const q = (selector) => {
  if (!elements.has(selector)) {
    const classes = new Set();
    elements.set(selector, {value:'', get textContent(){return this.value;},
      set textContent(value){this.value=value; ++writes;},
      classList:{toggle(name, on){on ? classes.add(name) : classes.delete(name);}, contains:name=>classes.has(name)}});
  }
  return elements.get(selector);
};
const context = vm.createContext({q, AbortController,
  setTimeout(callback, delay){assert.equal(delay,4000); abort=callback; return 1;},
  clearTimeout(){abort=null;},
  api:async(path, options)=>{
    assert.equal(path,'/api/v1/native'); ++reads;
    if (deferred) return deferred(options.signal);
    if (failure) throw typeof failure === 'string' ? new Error(failure) : failure;
    return result;
  }});
vm.runInContext(source.slice(start,end), context);
(async()=>{
  await context.refreshNative();
  assert.equal(q('#nativeStatus').textContent,'NATIVE LIVE');
  assert.equal(q('#nativeReadiness').classList.contains('ready'),true);
  assert.match(q('#nativeReadinessDetail').textContent,/hardware tests still required/);
  const previousWrites = writes;
  await context.refreshNative(); assert.equal(writes,previousWrites); // No repeated live announcements.
  result={available:false}; await context.refreshNative();
  assert.equal(q('#nativeStatus').textContent,'NATIVE FALLBACK');
  assert.equal(q('#nativeReadiness').classList.contains('ready'),false);
  assert.equal(q('#nativeReadiness').classList.contains('pending'),true);
  for (const malformed of [{}, {available:'true'}, null]) {
    result=malformed; await context.refreshNative();
    assert.equal(q('#nativeStatus').textContent,'NATIVE --');
  }
  failure='HTTP 503'; await context.refreshNative();
  assert.match(q('#nativeReadinessTitle').textContent,/Status Unavailable/);
  failure=Object.assign(new Error('engine unavailable'),{status:503,data:{available:false}});
  await context.refreshNative();
  assert.equal(q('#nativeStatus').textContent,'NATIVE FALLBACK');
  failure=null;
  deferred=signal=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('timed out'))));
  const pending=context.refreshNative(), before=reads;
  await context.refreshNative(); assert.equal(reads,before); // No overlapping status requests.
  abort(); await pending;
  assert.equal(q('#nativeStatus').textContent,'NATIVE --');
  deferred=null; result={available:true}; await context.refreshNative();
  assert.equal(q('#nativeStatus').textContent,'NATIVE LIVE'); // Retry after timeout can recover.
  assert.equal(abort,null);
  console.log('Native readiness workflow passed');
})().catch(error=>{console.error(error); process.exitCode=1;});
