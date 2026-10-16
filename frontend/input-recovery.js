(() => {
  function describe(data) {
    const input = data?.inputs?.find(item => item.slot === 0);
    const desired = input?.desiredDeviceId || "";
    const matches = (data?.devices || []).filter(item => item.connected && item.input && item.desiredInputSlots?.includes(0));
    const name = matches.length === 1 ? matches[0].name || "Selected input" : "Selected input";
    if (!data?.available || !input?.available) return {desired, canConnect:false, text:"Input status unavailable. Check the audio engine."};
    if (!desired) return {desired, canConnect:false, text:"Choose an audio input in Audio devices."};
    if (input.active) return {desired, canConnect:false, text:`${name} · Capture active`};
    if (!input.desiredConnected || matches.length !== 1) return {desired, canConnect:false, text:"Selected input disconnected or unverified. Connect the same device; capture is stopped."};
    return {desired, canConnect:true, text:`${name} · Ready to connect. Capture is stopped.`};
  }

  function create({status, button, request, getPolicy, confirmRoute, onRecovered}) {
    let data = null, busy = false, polling = false, notice = "", interrupted = false, desired = "", generation = 0;
    function update(next) {
      const view = describe(next);
      if (view.desired !== desired) { interrupted = false; notice = ""; desired = view.desired; }
      const input = next?.inputs?.find(item => item.slot === 0);
      const previous = data?.inputs?.find(item => item.slot === 0);
      if (input?.active !== previous?.active || input?.desiredConnected !== previous?.desiredConnected) notice = "";
      if (input?.active) interrupted = true;
      if (desired && input?.available && !input.desiredConnected) interrupted = true;
      data = next;
      status.textContent = notice || view.text;
      button.textContent = busy ? "Connecting…" : interrupted ? "Reconnect input" : "Connect input";
      button.disabled = busy || !view.canConnect;
      return view;
    }
    async function poll() {
      if (busy || polling) return;
      const started = generation;
      polling = true;
      try {
        const next = await request("/api/v1/audio/devices");
        if (!busy && started === generation) update(next);
      } catch (error) {
        if (!busy && started === generation) { button.disabled = true; status.textContent = `Input status unavailable: ${error.message}`; }
      } finally { polling = false; }
    }
    async function connect() {
      if (busy || button.disabled) return;
      const clickedDesired = desired;
      ++generation;
      busy = true; notice = ""; update(data);
      try {
        const next = await request("/api/v1/audio/devices");
        const view = update(next);
        if (view.desired !== clickedDesired) throw new Error("Selected input changed. Review it before connecting.");
        if (!view.canConnect) return;
        const input = next.inputs.find(item => item.slot === 0);
        const routed = Number(input.route?.gain || 0) > 0;
        if (routed && !confirmRoute(`Reconnect input with route gain ${input.route.gain} to graph output ${input.route.output ?? 0}?`)) return;
        const result = await request("/api/v1/audio/input/recover", {method:"POST", body:JSON.stringify({
          acknowledgeRecovery:true, acknowledgePhysicalInput:true, acknowledgeSignalRoute:routed,
          expectedDeviceId:view.desired, expectedRoute:input.route || {}, channels:2, conversionPolicy:getPolicy()
        })});
        if (!result.active) throw new Error("Capture did not start. Check the selected input and try again.");
        update({...next, inputs:next.inputs.map(item => item.slot === 0 ? {...item, ...result} : item)});
        await onRecovered();
      } catch (error) { notice = `Input connection failed: ${error.message}`; }
      finally { busy = false; update(data); }
    }
    button.addEventListener("click", connect);
    return {poll, connect};
  }
  globalThis.StageMeshInputRecovery = {describe, create};
})();
