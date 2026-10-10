(function () {
  "use strict";
  const q = (selector) => document.querySelector(selector);
  const canvas = q("#templateCanvas");
  if (!canvas) return;
  const storageKey = "stagemesh.stage-template.v1";
  let objects = [];
  let selectedId = null;
  let drag = null;
  let serverTemplateId = null;
  let serverRevision = null;
  let serverDirty = false;
  const presets = {
    club: {name: "Small club", description: "Compact vocal, guitar, drum, and monitor layout", objects: [
      ["performer", "Lead vocal", 50, 42], ["microphone", "Vocal mic", 50, 53], ["monitor", "Wedge L", 35, 62], ["monitor", "Wedge R", 65, 62], ["speaker", "Main L", 16, 30], ["speaker", "Main R", 84, 30]
    ]},
    arena: {name: "Arena stage", description: "Frontline, backline, PA, and side-fill starter layout", objects: [
      ["performer", "Lead vocal", 50, 40], ["performer", "Drums", 50, 25], ["performer", "Bass", 32, 42], ["performer", "Keys", 68, 42], ["microphone", "Vocal mic", 50, 52], ["monitor", "Side-fill L", 18, 50], ["monitor", "Side-fill R", 82, 50], ["speaker", "PA L", 9, 26], ["speaker", "PA R", 91, 26], ["light", "Front wash", 50, 10]
    ]},
    festival: {name: "Festival stage", description: "Large-stage systems, FOH, power, and calibration markers", objects: [
      ["performer", "Lead vocal", 50, 45], ["performer", "Drums", 50, 28], ["performer", "Guitar L", 30, 45], ["performer", "Guitar R", 70, 45], ["microphone", "Calibration mic", 50, 72], ["monitor", "Monitor L", 27, 63], ["monitor", "Monitor R", 73, 63], ["speaker", "Array L", 8, 25], ["speaker", "Array R", 92, 25], ["light", "Truss wash L", 25, 12], ["light", "Truss wash R", 75, 12], ["marker", "FOH", 50, 88]
    ]}
  };
  const esc = (value) => String(value).replace(/[&<>\"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[char]));
  const validateTemplateDocument = (parsed, {allowObjectDefaults = false, fallbackName = ""} = {}) => {
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) || parsed.version !== 1) throw new Error("supported template version 1 required");
    if (!Array.isArray(parsed.objects) || parsed.objects.length > 5000) throw new Error("objects must be an array of at most 5000 entries");
    if (parsed.name !== undefined && (typeof parsed.name !== "string" || !parsed.name.trim() || parsed.name.length > 128)) throw new Error("template name must contain 1–128 characters");
    const ids = new Set();
    const normalized = parsed.objects.map((item, index) => {
      const fail = (message) => { throw new Error(`Object ${index + 1}: ${message}`); };
      if (!item || typeof item !== "object" || Array.isArray(item)) fail("object record required");
      if (typeof item.label !== "string" || !item.label.trim() || item.label.length > 128) fail("label must contain 1–128 characters");
      const id = item.id === undefined && allowObjectDefaults ? `import-${Date.now()}-${index}` : item.id;
      if (typeof id !== "string" || !id || ids.has(id)) fail("nonempty unique ID required");
      ids.add(id);
      const type = item.type === undefined && allowObjectDefaults ? "marker" : item.type;
      if (typeof type !== "string" || !type || type.length > 32) fail("type must contain 1–32 characters");
      const x = item.x === undefined && allowObjectDefaults ? 50 : item.x;
      const y = item.y === undefined && allowObjectDefaults ? 50 : item.y;
      if (![x, y].every((value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100)) fail("coordinates must be finite numbers between 0 and 100");
      return {...item, id, type, x, y};
    });
    return {version: 1, name: parsed.name === undefined ? fallbackName : parsed.name, objects: normalized};
  };
  let persistedName = q("#templateName").value;
  const writeDraft = (nextObjects = objects, nextName = q("#templateName").value) => {
    if (typeof nextName !== "string" || !nextName.trim() || nextName.length > 128) throw new Error("template name must contain 1–128 characters");
    localStorage.setItem(storageKey, JSON.stringify({version: 1, name: nextName, objects: nextObjects}));
    persistedName = nextName;
  };
  const save = () => {
    writeDraft();
    if (serverTemplateId) serverDirty = true;
  };
  const replaceLocalDraft = (nextObjects, nextSelectedId, nextName = q("#templateName").value) => {
    writeDraft(nextObjects, nextName);
    objects = nextObjects; selectedId = nextSelectedId; q("#templateName").value = nextName;
    if (serverTemplateId) serverDirty = true;
  };
  const load = () => {
    try {
      const serialized = localStorage.getItem(storageKey);
      if (serialized === null) return;
      const parsed = validateTemplateDocument(JSON.parse(serialized), {fallbackName: q("#templateName").value});
      objects = parsed.objects;
      q("#templateName").value = parsed.name;
      persistedName = parsed.name;
    } catch (error) {
      objects = [];
      q("#templateHint").textContent = `Local draft rejected: ${error.message}. Stored data was preserved for recovery.`;
    }
  };
  const selected = () => objects.find((item) => item.id === selectedId);
  const api = async (method, path, body) => {
    const response = await fetch(path, {
      method: method, headers: body ? {"Content-Type": "application/json"} : {},
      body: body ? JSON.stringify(body) : undefined
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Request failed (" + response.status + ")");
    return result;
  };
  const refreshSaved = async (selectId) => {
    const select = q("#templateSaved");
    const data = await api("GET", "/api/v1/templates");
    select.replaceChildren(new Option("Select a saved template", ""));
    (data.templates || []).forEach((item) => {
      select.add(new Option(item.name + " · r" + item.revision + " · " + item.state, item.templateId));
    });
    if (selectId && Array.from(select.options).some((option) => option.value === selectId)) select.value = selectId;
    q("#templateLoadSaved").disabled = !select.value;
    return data.templates || [];
  };
  const loadSaved = async (templateId) => {
    const item = await api("GET", "/api/v1/templates/" + encodeURIComponent(templateId));
    writeDraft(item.objects, item.name);
    serverTemplateId = item.templateId; serverRevision = item.revision; serverDirty = false;
    objects = item.objects; selectedId = null; q("#templateName").value = item.name;
    render();
    q("#templateDeleteServer").disabled = false;
    q("#templateHint").textContent = "Loaded server revision " + serverRevision + ". Local edits must be saved as a new revision.";
  };
  const saveServer = async () => {
    const document = {name: q("#templateName").value.trim() || "Untitled stage template", objects: objects};
    const item = serverTemplateId
      ? await api("PATCH", "/api/v1/templates/" + encodeURIComponent(serverTemplateId), {expectedRevision: serverRevision, document: document})
      : await api("POST", "/api/v1/templates", document);
    serverTemplateId = item.templateId; serverRevision = item.revision; serverDirty = false;
    await refreshSaved(serverTemplateId); render();
    q("#templateHint").textContent = "Saved revision " + serverRevision + " to the StageMesh server. Physical outputs remain disarmed.";
  };
  const deleteServer = async () => {
    if (!serverTemplateId) return;
    await api("DELETE", "/api/v1/templates/" + encodeURIComponent(serverTemplateId), {expectedRevision: serverRevision});
    serverTemplateId = null; serverRevision = null; serverDirty = false;
    await refreshSaved(""); render();
    q("#templateHint").textContent = "Saved template deleted. The local draft remains available.";
  };
  const renderStatus = () => {
    const stateLabel = serverTemplateId ? "SERVER r" + serverRevision + (serverDirty ? " · UNSAVED" : "") : "LOCAL DRAFT";
    q("#templateStatus").textContent = objects.length + " OBJECT" + (objects.length === 1 ? "" : "S") + " · " + stateLabel;
  };
  const render = () => {
    canvas.querySelectorAll(".templateObject").forEach((node) => node.remove());
    q("#templateDelete").disabled = !selected();
    q("#templateLoadSaved").disabled = !q("#templateSaved").value;
    q("#templateDeleteServer").disabled = !serverTemplateId || q("#templateSaved").value !== serverTemplateId;
    renderStatus();
    const empty = q(".templateEmpty");
    if (empty) empty.hidden = objects.length > 0;
    objects.forEach((item) => {
      const node = document.createElement("button");
      node.type = "button"; node.className = `templateObject template-${item.type}${item.id === selectedId ? " selected" : ""}`;
      node.dataset.id = item.id; node.style.left = `${item.x}%`; node.style.top = `${item.y}%`;
      node.setAttribute("aria-label", `${item.label}, ${item.type}. Use arrow keys to move; Shift moves ten percent.`);
      node.setAttribute("aria-pressed", String(item.id === selectedId));
      const selectObject = () => {
        selectedId = item.id;
        canvas.querySelectorAll(".templateObject").forEach((button) => {
          const active = button.dataset.id === selectedId;
          button.classList.toggle("selected", active); button.setAttribute("aria-pressed", String(active));
        });
        q("#templateDelete").disabled = false;
      };
      node.addEventListener("click", selectObject);
      node.addEventListener("keydown", (event) => {
        const direction = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[event.key];
        if (!direction || event.ctrlKey || event.altKey || event.metaKey || event.isComposing) return;
        event.preventDefault();
        if (drag) return;
        selectObject();
        const step = event.shiftKey ? 10 : 1;
        const previous = {x: item.x, y: item.y};
        item.x = Math.max(0, Math.min(100, item.x + direction[0] * step));
        item.y = Math.max(0, Math.min(100, item.y + direction[1] * step));
        node.style.left = `${item.x}%`; node.style.top = `${item.y}%`;
        try {
          save();
          q("#templateHint").textContent = `${item.label}: ${item.x}%, ${item.y}%. Position saved to this local draft.`;
        } catch (error) {
          item.x = previous.x; item.y = previous.y;
          node.style.left = `${item.x}%`; node.style.top = `${item.y}%`;
          q("#templateHint").textContent = `Move not saved: ${error.message}. Previous position restored.`;
        }
      });
      node.innerHTML = `<strong>${esc(item.label)}</strong><small>${esc(item.type)}</small>`;
      node.addEventListener("pointerdown", (event) => {
        if (drag || (event.button !== undefined && event.button !== 0)) return;
        event.preventDefault();
        try { node.setPointerCapture(event.pointerId); }
        catch { q("#templateHint").textContent = "Move could not start. Previous position preserved."; return; }
        selectObject(); node.focus();
        drag = {id: item.id, pointerId: event.pointerId, x: item.x, y: item.y};
      });
      node.addEventListener("pointermove", (event) => {
        if (!drag || drag.id !== item.id || drag.pointerId !== event.pointerId) return;
        const rect = canvas.getBoundingClientRect();
        item.x = Math.max(4, Math.min(96, ((event.clientX - rect.left) / rect.width) * 100));
        item.y = Math.max(7, Math.min(93, ((event.clientY - rect.top) / rect.height) * 100));
        node.style.left = `${item.x}%`; node.style.top = `${item.y}%`;
      });
      node.addEventListener("pointerup", (event) => {
        if (drag?.id !== item.id || drag.pointerId !== event.pointerId) return;
        const previous = drag;
        drag = null;
        try {
          save();
          q("#templateHint").textContent = "Position saved to this local draft.";
        } catch (error) {
          item.x = previous.x; item.y = previous.y;
          node.style.left = `${item.x}%`; node.style.top = `${item.y}%`;
          q("#templateHint").textContent = `Move not saved: ${error.message}. Previous position restored.`;
        }
      });
      const cancelMove = (event) => {
        if (drag?.id !== item.id || drag.pointerId !== event.pointerId) return;
        item.x = drag.x; item.y = drag.y; drag = null;
        node.style.left = `${item.x}%`; node.style.top = `${item.y}%`;
        q("#templateHint").textContent = "Move cancelled. Previous position preserved.";
      };
      node.addEventListener("pointercancel", cancelMove);
      node.addEventListener("lostpointercapture", cancelMove);
      canvas.appendChild(node);
    });
  };
  const makeObjects = (preset) => preset.objects.map(([type, label, x, y], index) => ({id: `${type}-${Date.now()}-${index}-${Math.random().toString(16).slice(2)}`, type, label, x, y}));
  const applyPreset = (key) => {
    const preset = presets[key]; if (!preset) return;
    try {
      replaceLocalDraft(makeObjects(preset), null); render();
      q("#templateHint").textContent = `${preset.name} loaded into the local draft. Customize before export.`;
    } catch (error) { q("#templateHint").textContent = `Preset not applied: ${error.message}. Previous draft preserved.`; }
  };
  const renderPresets = () => {
    const host = q("#templatePresets");
    Object.entries(presets).forEach(([key, preset]) => {
      const card = document.createElement("article"); card.className = "templatePreset"; card.draggable = true;
      card.innerHTML = `<div><strong>${esc(preset.name)}</strong><span>${esc(preset.description)}</span><small>${preset.objects.length} starter objects · open JSON</small></div><button type="button">Apply</button>`;
      card.querySelector("button").addEventListener("click", () => applyPreset(key));
      card.addEventListener("dragstart", (event) => { event.dataTransfer.setData("application/x-stagemesh-template", key); event.dataTransfer.effectAllowed = "copy"; });
      host.appendChild(card);
    });
  };
  q("#templateName").addEventListener("change", () => {
    if (drag) {
      q("#templateName").value = persistedName;
      q("#templateHint").textContent = "Name not saved while an object is moving. Finish or cancel the move, then rename.";
      return;
    }
    try {
      save(); renderStatus();
      q("#templateHint").textContent = "Template name saved to this local draft. Save to the server to create a new revision.";
    } catch (error) {
      q("#templateName").value = persistedName;
      q("#templateHint").textContent = `Name not saved: ${error.message}. Previous name restored.`;
    }
  });
  q("#templateSaved").addEventListener("change", () => {
    q("#templateLoadSaved").disabled = !q("#templateSaved").value;
    q("#templateDeleteServer").disabled = !serverTemplateId || q("#templateSaved").value !== serverTemplateId;
  });
  q("#templateLoadSaved").addEventListener("click", async () => {
    try { await loadSaved(q("#templateSaved").value); }
    catch (error) { q("#templateHint").textContent = "Load failed: " + error.message + ". Previous local draft preserved."; }
  });
  q("#templateSaveServer").addEventListener("click", async () => {
    try { await saveServer(); }
    catch (error) { q("#templateHint").textContent = "Save failed: " + error.message + ". Reload before overwriting if another editor changed the template."; }
  });
  q("#templateDeleteServer").addEventListener("click", async () => {
    try { await deleteServer(); }
    catch (error) { q("#templateHint").textContent = "Delete failed: " + error.message; }
  });
  q("#templateAdd").addEventListener("click", () => {
    const type = q("#templateObjectType").value;
    const label = q("#templateObjectLabel").value.trim() || "New object";
    const item = {id: `${type}-${Date.now()}-${Math.random().toString(16).slice(2)}`, type, label, x: 50, y: 50};
    try {
      replaceLocalDraft([...objects, item], item.id); render();
      q("#templateHint").textContent = `${label} added. Drag it to position it.`;
    } catch (error) { q("#templateHint").textContent = `Object not added: ${error.message}. Previous draft preserved.`; }
  });
  q("#templateDelete").addEventListener("click", () => {
    if (!selected()) return;
    try { replaceLocalDraft(objects.filter((item) => item.id !== selectedId), null); render(); }
    catch (error) { q("#templateHint").textContent = `Object not deleted: ${error.message}. Previous draft preserved.`; }
  });
  q("#templateReset").addEventListener("click", () => {
    try {
      replaceLocalDraft([], null); render();
      q("#templateHint").textContent = "Draft reset. No backend or hardware state was changed.";
    } catch (error) { q("#templateHint").textContent = `Draft not reset: ${error.message}. Previous draft preserved.`; }
  });
  q("#templateExport").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify({version: 1, name: q("#templateName").value, objects}, null, 2)], {type: "application/json"});
    const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "stagemesh-stage-template.json"; link.click(); URL.revokeObjectURL(link.href);
  });
  q("#templateImportButton").addEventListener("click", () => q("#templateImport").click());
  q("#templateImport").addEventListener("change", async (event) => {
    const file = event.target.files?.[0]; if (!file) return;
    try {
      const imported = validateTemplateDocument(JSON.parse(await file.text()), {allowObjectDefaults: true, fallbackName: q("#templateName").value});
      // Persist the complete validated replacement before changing the visible draft.
      writeDraft(imported.objects, imported.name);
      objects = imported.objects; selectedId = null; q("#templateName").value = imported.name;
      if (serverTemplateId) serverDirty = true;
      render(); q("#templateHint").textContent = "Template imported into the local draft.";
    } catch (error) { q("#templateHint").textContent = `Import rejected: ${error.message}`; }
    event.target.value = "";
  });
  canvas.addEventListener("dragover", (event) => { if (event.dataTransfer.types.includes("application/x-stagemesh-template")) { event.preventDefault(); canvas.classList.add("dropTarget"); } });
  canvas.addEventListener("dragleave", () => canvas.classList.remove("dropTarget"));
  canvas.addEventListener("drop", (event) => { const key = event.dataTransfer.getData("application/x-stagemesh-template"); if (!key) return; event.preventDefault(); canvas.classList.remove("dropTarget"); applyPreset(key); });
  load(); render();
  renderPresets();
  refreshSaved("").catch((error) => {
    q("#templateHint").textContent = "Server template library unavailable: " + error.message + ". Local editing remains available.";
  });
}());
