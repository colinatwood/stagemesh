(function () {
  "use strict";
  const review = (data, skipped = new Set()) => {
    const blockers = [], notes = [];
    if (data.native?.available !== true) blockers.push("The native engine is unavailable. Reconnect it before completing setup.");
    if (data.audio?.available !== true || !Array.isArray(data.audio.devices)) blockers.push("Audio discovery is unavailable.");
    if (!Array.isArray(data.inputs?.inputs) || !Array.isArray(data.outputs?.outputs) || typeof data.lighting?.armed !== "boolean") blockers.push("Current stream/output state could not be verified.");
    const inputId = data.audio?.desiredInputDeviceId || data.state?.audio?.inputDeviceId || "";
    const outputId = data.audio?.desiredDeviceId || data.state?.audio?.deviceId || "";
    const devices = Array.isArray(data.audio?.devices) ? data.audio.devices : [];
    for (const [direction, id] of [["input", inputId], ["output", outputId]]) {
      if (skipped.has(direction)) notes.push(`Audio ${direction} skipped; existing settings were retained.`);
      else if (!id || devices.filter(device => device.id === id && device.connected === true && device[direction] === true).length !== 1) blockers.push(`Choose an unambiguous connected audio ${direction}, or explicitly skip that step.`);
    }
    if (Array.isArray(data.inputs?.inputs) && data.inputs.inputs.some(item => item.active !== false)) blockers.push("Capture is active or unverified. Stop it for the setup baseline.");
    if (Array.isArray(data.outputs?.outputs) && data.outputs.outputs.some(item => item.active !== false)) blockers.push("Audio output is active or unverified. Stop it for the setup baseline.");
    if (data.lighting?.armed === true) blockers.push("Lighting output is armed. Disarm it for the setup baseline.");
    const gain = data.state?.audio?.inputRoute?.gain;
    if (typeof gain !== "number" || !Number.isFinite(gain) || gain !== 0) blockers.push("Save a muted input route (gain zero) in the Input step.");
    if (skipped.has("midi")) notes.push("MIDI skipped; existing mappings were retained.");
    else if (data.midi?.available !== true) blockers.push("MIDI discovery is unavailable. Retry or explicitly skip MIDI.");
    else if (!Array.isArray(data.midi.devices) || !data.midi.devices.some(device => device.connected === true && data.midi.bindings?.[device.id])) blockers.push("Bind a connected MIDI controller, or explicitly skip MIDI.");
    if (skipped.has("lighting")) notes.push("Lighting configuration skipped; its existing target was retained.");
    return {blockers, notes, ready: blockers.length === 0};
  };
  globalThis.StageMeshSetup = Object.freeze({review});
  if (typeof document === "undefined") return;
  const q = selector => document.querySelector(selector);
  if (!q("#setupContent") || !globalThis.StageMeshUI) return;
  const ui = globalThis.StageMeshUI;
  const steps = ["Start", "Audio input", "Audio output", "MIDI", "Lighting", "Review"];
  const keys = ["start", "input", "output", "midi", "lighting", "review"];
  let index = 0, generation = 0, busy = false, loading = false, data = null, fields = {}, assessment = null;
  const skipped = new Set();
  const content = q("#setupContent"), next = q("#setupNext"), back = q("#setupBack"), skip = q("#setupSkip");
  const status = text => { if (q("#setupStatus").textContent !== text) q("#setupStatus").textContent = text; };
  const add = (tag, text, parent = content) => { const node = document.createElement(tag); if (text) node.textContent = text; parent.appendChild(node); return node; };
  const field = (key, caption, type = "select", options = []) => {
    const group = add("div", ""); group.className = "setupField";
    const label = add("label", caption, group);
    const input = document.createElement(type === "select" ? "select" : "input");
    input.id = `setup-field-${key}`; label.htmlFor = input.id;
    if (type !== "select") input.type = type;
    for (const [value, text] of options) input.add(new Option(text, value));
    group.appendChild(input); fields[key] = input; return input;
  };
  const action = (caption, callback, parent = content) => {
    const button = add("button", caption, parent); button.type = "button"; button.addEventListener("click", callback); return button;
  };
  const controls = () => {
    back.disabled = index === 0 || busy;
    back.hidden = index === 0;
    skip.hidden = index === 0 || index === 5; skip.disabled = busy;
    next.disabled = busy || loading || (index === 5 && assessment?.ready !== true);
    next.textContent = busy ? "Saving…" : index === 0 ? "Start setup" : index === 5 ? "Finish and open Devices" : `Save ${keys[index]} + continue`;
    for (const input of Object.values(fields)) input.disabled = busy;
    q("#setupProgress").textContent = `Step ${index + 1} of ${steps.length}`;
  };
  const read = async path => {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 6000);
    try { return await ui.api(path, {signal:controller.signal}); }
    finally { clearTimeout(timer); }
  };
  const readData = async () => {
    const names = ["state", "audio", "midi", "lighting", "native", "inputs", "outputs"];
    const paths = ["/api/v1/state", "/api/v1/audio/devices", "/api/v1/midi/devices", "/api/v1/lighting/network", "/api/v1/native", "/api/v1/audio/inputs", "/api/v1/audio/outputs"];
    const results = await Promise.allSettled(paths.map(read));
    const result = {};
    for (let i = 0; i < names.length; i++) result[names[i]] = results[i].status === "fulfilled" ? results[i].value : null;
    return result;
  };
  const renderForm = () => {
    if (index === 1 || index === 2) {
      const direction = keys[index], desired = index === 1 ? data.audio?.desiredInputDeviceId || data.state?.audio?.inputDeviceId : data.audio?.desiredDeviceId || data.state?.audio?.deviceId;
      const choices = (Array.isArray(data.audio?.devices) ? data.audio.devices : []).filter(device => device[direction] === true && device.connected === true);
      const device = field("device", index === 1 ? "Recording input" : "Playback output", "select", [["", "Choose a connected device…"], ...choices.map(item => [item.id, item.name || item.id])]);
      device.value = choices.some(item => item.id === desired) ? desired : "";
      if (index === 1) {
        const player = field("player", "Performer / source", "select", [["", "Unassigned source"], ...(data.state?.players || []).map(item => [item.id, item.name])]);
        player.value = data.state?.audio?.inputPlayerId || "";
        add("p", "Saving selects this input and mutes its route to the main mix (gain zero). Start capture separately in Devices → Audio input.");
      } else {
        const ceiling = field("ceiling", "Output limiter ceiling (dBFS)", "number"); ceiling.min = -24; ceiling.max = 0; ceiling.step = 0.5; ceiling.value = data.state?.audio?.limiterCeilingDb ?? -1;
        add("p", "Saving selects the playback device and limiter. Playback starts only through an explicit activation in Devices → Audio output.");
      }
      if (data.audio?.available !== true || !choices.length) status("No connected device is available for this direction. Retry detection or skip for now; existing settings are retained.");
      else status("Choose the device you intend to use. Save applies only this step; Skip leaves current settings unchanged.");
    } else if (index === 3) {
      const devices = (Array.isArray(data.midi?.devices) ? data.midi.devices : []).filter(item => item.connected === true);
      field("device", "MIDI controller", "select", [["", "Choose a connected controller…"], ...devices.map(item => [item.id, item.name || item.id])]);
      field("player", "Control performer", "select", [["", "Choose a performer…"], ...(data.state?.players || []).map(item => [item.id, item.name])]);
      add("p", "Bind the controller to a performer. Existing mappings and advanced MIDI Learn controls remain available in Devices → MIDI controllers.");
      fields.device.addEventListener("change", () => { fields.player.value = data.midi?.bindings?.[fields.device.value] || ""; });
      status(data.midi?.available === true ? "Save binds only the selected controller. Repeat setup or use Devices to add more controllers." : "MIDI discovery is unavailable. Retry or skip this optional step.");
    } else if (index === 4) {
      const network = data.lighting?.desired || data.state?.lighting?.network || {};
      field("protocol", "Lighting protocol", "select", [["artnet", "Art-Net"], ["sacn", "sACN / E1.31"]]).value = network.protocol || "artnet";
      field("target", "Unicast destination", "text").value = network.target || "";
      const port = field("port", "UDP port", "number"); port.min = 1; port.max = 65535; port.value = network.port || 6454;
      const universe = field("universe", "Universe base", "number"); universe.min = 1; universe.max = 63984; universe.value = network.universeBase || 1;
      fields.protocol.addEventListener("change", () => { fields.port.value = fields.protocol.value === "sacn" ? 5568 : 6454; });
      add("p", "Save stores the lighting target. It does not arm lighting or transmit a test signal. Skip if lighting is not part of this session.");
      status("Keep physical lighting disarmed during baseline setup.");
    } else if (index === 5) {
      assessment = review(data, skipped);
      const list = add("dl", ""); list.className = "setupSummary";
      const devices = Array.isArray(data.audio?.devices) ? data.audio.devices : [];
      const name = id => devices.find(item => item.id === id)?.name || (id ? "Selected device unavailable" : "No device selected");
      for (const [caption, value] of [
        ["Audio input", name(data.audio?.desiredInputDeviceId || data.state?.audio?.inputDeviceId)],
        ["Audio output", name(data.audio?.desiredDeviceId || data.state?.audio?.deviceId)],
        ["MIDI mappings", String(Object.keys(data.midi?.bindings || {}).length)],
        ["Input route gain", String(data.state?.audio?.inputRoute?.gain ?? "Unknown")],
        ["Lighting output", data.lighting?.armed === false ? "Disarmed" : data.lighting?.armed === true ? "Armed" : "Unknown"]
      ]) { add("dt", caption, list); add("dd", value, list); }
      for (const note of assessment.notes) add("p", note).className = "hint";
      if (assessment.blockers.length) {
        const failures = add("ul", ""); failures.className = "setupBlockers";
        assessment.blockers.forEach(message => add("li", message, failures));
        action("Stop capture, audio output and lighting", async () => {
          if (busy || !globalThis.confirm("Stop current capture, audio output and lighting on this host?")) return;
          busy = true; controls();
          let failure = null;
          try {
            await ui.api("/api/v1/audio/input/deactivate", {method:"POST", body:"{}"});
            await ui.api("/api/v1/audio/deactivate", {method:"POST", body:"{}"});
            await ui.api("/api/v1/lighting/network/arm", {method:"POST", body:JSON.stringify({armed:false})});
          } catch (error) { failure = error; }
          finally { busy = false; await enter(index); if (failure) status(`Stop request failed: ${failure.message}. Some streams may already be stopped; review their current state.`); }
        });
      }
      add("p", "This saves your setup review on this device. No physical test has run. Start capture or playback separately from Devices when you are ready.");
      status(assessment.ready ? "Baseline reviewed: capture and outputs are stopped, with input routing muted. This is not a hardware test result."
        : "Resolve the items above, then refresh the review. Nothing is started by Next or Finish.");
    }
    action("Refresh detection", () => { if (!busy) enter(index); }); controls();
  };
  const enter = async target => {
    index = target; const current = ++generation; fields = {}; assessment = null; data = null;
    content.replaceChildren();
    const progress = q("#setupSteps"); progress.replaceChildren();
    steps.forEach((name, step) => { const item = add("li", `${step + 1}. ${name}`, progress); if (step === index) item.setAttribute("aria-current", "step"); });
    const heading = add("h2", steps[index]); heading.tabIndex = -1;
    if (index === 0) {
      loading = false;
      add("p", "Choose audio, MIDI and lighting one step at a time.");
      const points = add("ul", "");
      ["Save applies only the current step.", "Skip keeps your previous settings.", "Setup never starts streams; use Devices to activate them."].forEach(text => add("li", text, points));
      add("p", "Use the top menu to switch workspaces. Return to Setup any time.");
      status("Connect your hardware, then start setup. You can skip controls you are not using."); controls(); return;
    }
    loading = true; controls(); status("Reading current connections…");
    const loaded = await readData();
    if (current !== generation) return;
    data = loaded;
    loading = false; renderForm(); heading.focus({preventScroll:true});
  };
  back.addEventListener("click", () => { if (!busy && index > 0) enter(index - 1); });
  skip.addEventListener("click", () => { if (!busy && index > 0 && index < 5) { skipped.add(keys[index]); enter(index + 1); } });
  next.addEventListener("click", async () => {
    if (busy || loading) return;
    if (index === 0) { await enter(1); return; }
    if (index === 5) {
      if (!assessment?.ready) return;
      busy = true; controls();
      try {
        const fresh = await readData(); assessment = review(fresh, skipped);
        if (!assessment.ready) { busy = false; await enter(5); return; }
        localStorage.setItem("stagemesh.setup.review.v1", JSON.stringify({version:1, reviewed:true}));
        status("Setup review saved. Open Devices to begin an exercise.");
        busy = false; globalThis.StageMeshWorkspace?.navigate("operations", {device:"input"});
      } catch (error) { status(`Setup review could not be saved: ${error.message}`); }
      finally { busy = false; controls(); }
      return;
    }
    busy = true; controls();
    try {
      if (index === 1 || index === 2) {
        const direction = keys[index], device = fields.device.value;
        if (data.audio?.available !== true || !(data.audio?.devices || []).some(item => item.id === device && item.connected === true && item[direction] === true)) throw new Error("Choose a connected device or skip this step.");
        if (index === 1) await ui.configureAudio({inputDeviceId:device, inputPlayerId:fields.player.value, inputRoute:{output:0, gain:0}});
        else {
          const ceiling = fields.ceiling.value === "" ? NaN : Number(fields.ceiling.value);
          if (!Number.isFinite(ceiling) || ceiling < -24 || ceiling > 0) throw new Error("Limiter ceiling must be between -24 and 0 dBFS.");
          await ui.configureAudio({deviceId:device, limiterCeilingDb:ceiling});
        }
      } else if (index === 3) {
        if (data.midi?.available !== true || !fields.player.value || !(data.midi.devices || []).some(item => item.id === fields.device.value && item.connected === true)) throw new Error("Choose a connected controller and performer, or skip MIDI.");
        await ui.bindMidi(fields.device.value, fields.player.value);
      } else if (index === 4) {
        const target = fields.target.value.trim(), port = Number(fields.port.value), universeBase = Number(fields.universe.value);
        if (!target || !Number.isInteger(port) || port < 1 || port > 65535 || !Number.isInteger(universeBase) || universeBase < 1 || universeBase > 63984) throw new Error("Enter a destination, valid UDP port and universe, or skip lighting.");
        await ui.configureLighting({protocol:fields.protocol.value, target, port, universeBase});
      }
      skipped.delete(keys[index]); busy = false; await enter(index + 1);
    } catch (error) { status(`Settings were not confirmed: ${error.message}. Review this step and retry.`); }
    finally { busy = false; controls(); }
  });
  document.addEventListener("stagemesh:before-workspace-change", event => {
    if (busy) { event.preventDefault(); status("Wait for the current save to finish before changing workspaces."); }
  });
  enter(0);
}());
