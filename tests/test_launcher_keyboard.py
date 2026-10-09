"""Execute the registered launcher shortcut callback without a hardware/backend session."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node.js is required for frontend behavior checks")
class LauncherKeyboardTests(unittest.TestCase):
    def test_shortcuts_preserve_native_controls_and_only_use_unmodified_background_keys(self):
        result = subprocess.run(["node", "-e", r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('frontend/app.js', 'utf8');
const registration = source.split('\n').find(line => line.includes('document.addEventListener("keydown"'));
assert.ok(registration, 'launcher keyboard callback must be registered');
let handler;
const calls = [];
const document = {activeElement: null, addEventListener: (type, callback) => {assert.equal(type, 'keydown'); handler = callback;}};
vm.runInNewContext(registration, {document, launcherState: {pads: [{shortcut:'1', resourceId:'pad-1'}]},
  launcherAction: (...args) => {calls.push(args); return Promise.resolve();}, q: () => ({})});
function run(extra={}, focused=null) {
  calls.length = 0;
  document.activeElement = focused;
  let prevented = false;
  handler({code:'Space', key:' ', preventDefault(){prevented=true;}, ...extra});
  return {calls: [...calls], prevented};
}
assert.equal(run().calls[0][0], 'transport.toggle');
assert.equal(run().prevented, true);
assert.equal(run({code:'Escape', key:'Escape'}).calls[0][0], 'transport.stop');
assert.equal(run({code:'Digit1', key:'1'}).calls[0][0], 'sample.trigger');
assert.equal(run({code:'KeyX', key:'x'}).calls.length, 0);
for (const flag of ['defaultPrevented','repeat','isComposing','ctrlKey','altKey','metaKey','shiftKey']) {
  const result = run({[flag]:true}); assert.equal(result.calls.length, 0, flag); assert.equal(result.prevented, false, flag);
}
for (const control of ['input','select','textarea','button','a[href]','summary','[role=button]','[role=link]','[role=textbox]','[role=combobox]','[role=slider]']) {
  const focused = {closest: selector => selector.split(',').includes(control) ? {} : null};
  for (const key of [{}, {code:'Escape',key:'Escape'}, {code:'Digit1',key:'1'}]) {
    const result = run(key, focused); assert.equal(result.calls.length, 0, control); assert.equal(result.prevented, false, control);
  }
}
assert.equal(run({}, {isContentEditable:true}).calls.length, 0);
assert.equal(run({}, {closest:()=>null}).calls[0][0], 'transport.toggle');
console.log('launcher keyboard behavior passed');
'''], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
