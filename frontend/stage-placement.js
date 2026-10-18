(function () {
  "use strict";
  // A placement is a private preview until commit succeeds. No provisional
  // coordinates enter local storage, exports, or a server request.
  globalThis.StageMeshPlacement = {create(host) {
    const {canvas} = host;
    let session = null;
    let gesture = null;
    let suppressClick = false;
    const panel = document.createElement("div");
    panel.className = "stageOptions"; panel.hidden = true;
    panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Stage object options");
    const title = document.createElement("strong"); panel.appendChild(title);
    const fields = {};
    for (const [key, caption, type, min, max] of [
      ["label", "Label", "text"], ["x", "X position (%)", "number", 0, 100],
      ["y", "Y position (%)", "number", 0, 100], ["rotation", "Orientation (degrees)", "number", 0, 359]
    ]) {
      const label = document.createElement("label"); label.textContent = caption;
      const input = document.createElement("input"); input.type = type;
      if (type === "number") { input.min = min; input.max = max; input.step = 1; }
      else input.maxLength = 128;
      label.appendChild(input); panel.appendChild(label); fields[key] = input;
      input.addEventListener("change", () => {
        if (!session) return;
        if (key === "label") {
          if (!input.value.trim() || input.value.length > 128) { host.hint("Enter a label of 1–128 characters."); sync(); return; }
          session.items[0].label = input.value.trim();
        } else {
          const value = input.value === "" ? NaN : Number(input.value);
          if (!Number.isFinite(value) || value < min || value > max) { host.hint(`Enter ${caption} between ${min} and ${max}.`); sync(); return; }
          const next = {...session.transform, [key]: value};
          if (!transform(next)) { sync(); return; }
        }
        host.render(); sync();
      });
    }
    const instructions = document.createElement("p"); panel.appendChild(instructions);
    const actions = document.createElement("div"); actions.className = "stageOptionActions"; panel.appendChild(actions);
    const button = (text, action) => {
      const node = document.createElement("button"); node.type = "button"; node.textContent = text;
      node.addEventListener("click", action); actions.appendChild(node); return node;
    };
    const move = button("Place on stage", () => {
      if (!session) return;
      session.phase = "placing"; save.disabled = true; canvas.focus();
      host.hint("Move onto the stage and click to place. Adjust orientation or drag, then click the stage again to save. Escape cancels.");
    });
    const save = button("Save placement", () => commit());
    button("Cancel", () => cancel());
    document.body.appendChild(panel);
    const positionPanel = (rect) => {
      const box = panel.getBoundingClientRect();
      panel.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - box.width - 8))}px`;
      panel.style.top = `${Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - box.height - 8))}px`;
    };
    const sync = () => {
      if (!session) return;
      fields.label.value = session.items[0].label;
      fields.label.parentElement.hidden = session.items.length !== 1;
      for (const key of ["x", "y", "rotation"]) fields[key].value = Math.round(session.transform[key] * 100) / 100;
      move.textContent = session.phase === "options" ? "Place on stage" : "Move on stage";
      save.disabled = session.phase !== "adjusting";
      instructions.textContent = session.replace
        ? "This layout replaces the current stage only when saved. Drag to move; set orientation; click the stage to save. Escape cancels."
        : "Drag to move; set orientation; click the stage to save. Escape cancels.";
    };
    const transform = (next) => {
      const radians = (next.rotation - session.initialRotation) * Math.PI / 180;
      const c = Math.cos(radians), s = Math.sin(radians);
      const {width, height} = canvas.getBoundingClientRect();
      if (!width || !height) return false;
      const items = session.base.map((item, index) => {
        const dx = (item.x - session.center.x) * width, dy = (item.y - session.center.y) * height;
        return {...session.items[index], x: next.x + (dx * c - dy * s) / width, y: next.y + (dx * s + dy * c) / height,
          rotation: ((item.rotation || 0) + next.rotation - session.initialRotation + 360) % 360};
      });
      if (items.some(item => item.x < 0 || item.x > 100 || item.y < 0 || item.y > 100)) {
        host.hint("Keep the entire placement inside the stage. Move it toward the center before rotating."); return false;
      }
      session.items = items; session.transform = next; return true;
    };
    const begin = (items, anchor, {replace = false, existing = false, title: heading = "Object options"} = {}) => {
      try { host.assertAvailable("opening placement options"); }
      catch (error) { host.hint(error.message); return; }
      if (!items.length) return;
      const anchorRect = anchor.getBoundingClientRect();
      const center = {x: items.reduce((sum, item) => sum + item.x, 0) / items.length,
        y: items.reduce((sum, item) => sum + item.y, 0) / items.length};
      const rotation = items.length === 1 ? (items[0].rotation || 0) : 0;
      session = {items: items.map(item => ({...item})), base: items.map(item => ({...item})), center,
        transform: {...center, rotation}, initialRotation: rotation, replace, existing, anchor,
        previousSelection: host.getSelection(), phase: existing ? "adjusting" : "options"};
      host.select(items[0].id); title.textContent = heading;
      panel.hidden = false; host.render(); sync(); positionPanel(anchorRect);
      fields.label.parentElement.hidden ? fields.x.focus() : fields.label.focus();
      host.hint(existing ? "Edit orientation or drag to move. Click the stage to save; Escape cancels."
        : "Choose options, then Place on stage. Changes save only after your final click.");
    };
    const restoreFocus = (previous) => {
      const object = Array.from(canvas.querySelectorAll(".templateObject")).find(node => node.dataset.id === host.getSelection());
      (object || (previous.anchor.isConnected && previous.anchor) || canvas).focus();
    };
    const commit = () => {
      if (!session || session.phase !== "adjusting" || gesture) return;
      try {
        const next = view();
        host.commit(next, session.items[0].id);
        const previous = session; session = null; panel.hidden = true; suppressClick = false;
        host.render(); restoreFocus(previous); host.hint("Placement saved to this local draft.");
      } catch (error) { host.hint(`Placement not saved: ${error.message}. Retry Save or press Escape to cancel.`); }
    };
    const cancel = () => {
      if (!session) return;
      const previous = session; session = null; gesture = null; suppressClick = false; panel.hidden = true;
      host.select(previous.previousSelection); host.render(); restoreFocus(previous);
      host.hint("Placement cancelled. Previous draft preserved.");
    };
    const view = () => {
      if (!session) return host.getObjects();
      if (session.replace) return session.items;
      const ids = new Set(session.items.map(item => item.id));
      if (session.existing) return host.getObjects().map(item => session.items.find(preview => preview.id === item.id) || item);
      return [...host.getObjects().filter(item => !ids.has(item.id)), ...session.items];
    };
    const point = (event) => {
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height) return null;
      return {x: Math.max(0, Math.min(100, (event.clientX - rect.left) / rect.width * 100)),
        y: Math.max(0, Math.min(100, (event.clientY - rect.top) / rect.height * 100))};
    };
    canvas.addEventListener("click", event => {
      if (!session || event.button > 0) return;
      event.preventDefault(); event.stopImmediatePropagation();
      if (suppressClick) { suppressClick = false; return; }
      if (session.phase === "placing") {
        const p = point(event);
        if (p && transform({...session.transform, ...p})) {
          session.phase = "adjusting"; host.render(); sync();
          host.hint("Placed. Drag or adjust orientation, then left-click the stage again to save.");
        }
      } else if (session.phase === "adjusting") commit();
    }, true);
    canvas.addEventListener("pointerdown", event => {
      if (!gesture) suppressClick = false;
      if (!session || session.phase !== "adjusting" || gesture || event.button !== 0) return;
      const node = event.target.closest(".templateObject");
      if (!node || !session.items.some(item => item.id === node.dataset.id)) return;
      const p = point(event); if (!p) return;
      try { canvas.setPointerCapture(event.pointerId); }
      catch { host.hint("Move could not start. Placement preserved."); return; }
      gesture = {pointerId: event.pointerId, point: p, transform: {...session.transform}, moved: false};
      event.preventDefault();
    });
    canvas.addEventListener("pointermove", event => {
      if (!session || event.isPrimary === false || (gesture && gesture.pointerId !== event.pointerId)) return;
      const p = point(event); if (!p) return;
      if (session.phase === "placing") transform({...session.transform, ...p});
      else if (gesture) {
        const dx = p.x - gesture.point.x, dy = p.y - gesture.point.y;
        if (Math.abs(dx) + Math.abs(dy) < 0.2 && !gesture.moved) return;
        gesture.moved = true;
        transform({...gesture.transform, x: gesture.transform.x + dx, y: gesture.transform.y + dy});
      } else return;
      host.render(); sync();
    });
    canvas.addEventListener("pointerup", event => {
      if (!gesture || gesture.pointerId !== event.pointerId) return;
      suppressClick = gesture.moved; gesture = null;
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    });
    const cancelGesture = event => {
      if (!gesture || gesture.pointerId !== event.pointerId) return;
      transform(gesture.transform); gesture = null; suppressClick = true; host.render(); sync();
    };
    canvas.addEventListener("pointercancel", cancelGesture);
    canvas.addEventListener("lostpointercapture", cancelGesture);
    document.addEventListener("keydown", event => {
      if (session && event.key === "Escape") { event.preventDefault(); cancel(); }
    });
    const contextOptions = (node, action) => {
      node.addEventListener("contextmenu", event => { event.preventDefault(); action(); });
      node.addEventListener("keydown", event => {
        if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) { event.preventDefault(); action(); }
      });
    };
    return {view, isEditing: () => Boolean(session), begin, contextOptions,
      editObject: (id, anchor) => {
        const item = host.getObjects().find(item => item.id === id);
        if (item) begin([item], anchor, {existing: true, title: `${item.label} options`});
      },
      moveKey(event) {
        if (!session || gesture || session.phase !== "adjusting") return;
        const delta = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[event.key];
        if (!delta) return;
        const step = event.shiftKey ? 10 : 1;
        transform({...session.transform, x: session.transform.x + delta[0] * step, y: session.transform.y + delta[1] * step});
        host.render(); sync(); restoreFocus(session);
      }
    };
  }};
}());
