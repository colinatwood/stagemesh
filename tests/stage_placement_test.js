const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
class Node {
  constructor(tag = 'div') { this.tag = tag; this.handlers = {}; this.children = []; this.style = {}; this.dataset = {}; this.isConnected = true; this.value = ''; }
  appendChild(node) { this.children.push(node); node.parentElement = this; return node; }
  setAttribute(key, value) { this[key] = value; }
  addEventListener(key, fn, capture) { (this.handlers[key] ||= []).push({fn, capture}); }
  fire(key, options = {}) { const event = {key: '', button: 0, pointerId: 1, clientX: 50, clientY: 50, target: this,
    preventDefault() {}, stopImmediatePropagation() {}, ...options}; for (const {fn} of this.handlers[key] || []) fn(event); }
  getBoundingClientRect() { return {left: 0, top: 0, bottom: 30, width: 100, height: 100}; }
  focus() { focused = this; }
  querySelectorAll() { return []; }
  closest() { return this.dataset.id ? this : null; }
  setPointerCapture(id) { this.captured = id; }
  hasPointerCapture(id) { return this.captured === id; }
  releasePointerCapture() { this.captured = null; }
}
let focused, objects = [], selection = null, writes = 0, failWrite = false, busy = false, hint = '';
const canvas = new Node(), body = new Node(), document = new Node();
document.body = body; document.createElement = tag => new Node(tag);
const context = {document, window: {innerWidth: 1000, innerHeight: 1000}};
vm.runInNewContext(fs.readFileSync('frontend/stage-placement.js', 'utf8'), context);
const controller = context.StageMeshPlacement.create({canvas, getObjects: () => objects, getSelection: () => selection,
  select: id => selection = id, assertAvailable: () => { if (busy || controller.isEditing()) throw Error('editor busy'); },
  render() {}, hint: text => hint = text, commit: (items, id) => { if (failWrite) throw Error('disk full'); objects = items; selection = id; writes++; }});
const panel = body.children[0], fields = panel.children.filter(node => node.tag === 'label').map(label => label.children[0]);
const buttons = panel.children.at(-1).children;
const [place, save, cancel] = buttons;
const anchor = new Node('button');
const original = {id: 'lead', type: 'performer', label: 'Lead', x: 50, y: 50};
controller.begin([original], anchor);
assert.equal(writes, 0); assert.equal(objects.length, 0); assert.equal(save.disabled, true);
place.fire('click');
canvas.fire('pointermove', {clientX: 30, clientY: 40});
canvas.fire('click', {clientX: 30, clientY: 40});
assert.equal(writes, 0); assert.equal(save.disabled, false);
fields[3].value = '90'; fields[3].fire('change');
assert.equal(controller.view()[0].rotation, 90);
canvas.fire('click');
assert.equal(writes, 1); assert.equal(objects[0].x, 30); assert.equal(objects[0].y, 40); assert.equal(objects[0].rotation, 90);
assert.equal(controller.isEditing(), false); assert.equal(panel.hidden, true);
// Reopening and moving remain provisional; a failed write can be retried or cancelled.
controller.editObject('lead', anchor);
controller.moveKey({key: 'ArrowRight', shiftKey: true});
assert.equal(controller.view()[0].x, 40); assert.equal(objects[0].x, 30);
failWrite = true; save.fire('click');
assert.equal(writes, 1); assert.equal(objects[0].x, 30); assert.equal(controller.isEditing(), true); assert.match(hint, /disk full/);
document.fire('keydown', {key: 'Escape'});
assert.equal(controller.isEditing(), false); assert.equal(objects[0].x, 30);
failWrite = false;
// Group rotation and translation preserve the layout until the final click.
controller.begin([{...original, id: 'left', x: 40}, {...original, id: 'right', x: 60}], anchor, {replace: true});
fields[3].value = '90'; fields[3].fire('change');
assert.ok(Math.abs(controller.view()[0].x - 50) < 1e-8); assert.equal(controller.view()[0].y, 40);
assert.equal(objects.length, 1); cancel.fire('click'); assert.equal(objects[0].id, 'lead');
// Only the initiating pointer owns a drag. Release does not save; final click does.
controller.editObject('lead', anchor);
const object = new Node('button'); object.dataset.id = 'lead';
canvas.fire('pointerdown', {target: object, pointerId: 7, clientX: 30, clientY: 40});
canvas.fire('pointermove', {pointerId: 8, clientX: 90, clientY: 90});
assert.equal(controller.view()[0].x, 30);
canvas.fire('pointermove', {pointerId: 7, clientX: 40, clientY: 50});
canvas.fire('pointerup', {pointerId: 8}); assert.equal(canvas.captured, 7);
canvas.fire('pointerup', {pointerId: 7}); canvas.fire('click');
assert.equal(writes, 1); assert.equal(controller.isEditing(), true);
canvas.fire('click'); assert.equal(writes, 2); assert.equal(objects[0].x, 40);
// Cancellation rolls back an interrupted drag; busy editor cannot start another session.
controller.editObject('lead', anchor);
canvas.fire('pointerdown', {target: object, pointerId: 9, clientX: 40, clientY: 50});
canvas.fire('pointermove', {pointerId: 9, clientX: 60, clientY: 70});
canvas.fire('lostpointercapture', {pointerId: 9}); assert.equal(controller.view()[0].x, 40);
cancel.fire('click'); busy = true; controller.begin([original], anchor); assert.equal(controller.isEditing(), false);
busy = false;
// Context menus have an equivalent keyboard activation.
let opened = 0; controller.contextOptions(anchor, () => opened++);
anchor.fire('contextmenu'); anchor.fire('keydown', {key: 'F10', shiftKey: true}); anchor.fire('keydown', {key: 'ContextMenu'});
assert.equal(opened, 3);
console.log('Stage placement transactions, transforms, ownership and context options passed');
