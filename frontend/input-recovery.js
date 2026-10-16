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

  function create({status, button, metrics, request, getPolicy, confirmRoute, onRecovered, now = () => performance.now()}) {
    let data = null, busy = false, polling = false, notice = "", interrupted = false, desired = "", generation = 0;
    let lossAt = null, returnMs = null, responseMs = null, callbackSample = null;
    const write = (element, value) => { if (element && element.textContent !== value) element.textContent = value; };
    const seconds = value => `${(Math.max(0, value) / 1000).toFixed(1)} s`;
    const number = value => typeof value === "number" && Number.isFinite(value) && value >= 0 ? String(value) : "unreported";
    const positive = value => value > 0 ? number(value) : "unreported";
    function observe(next, input, fresh) {
      const lines = [];
      if (responseMs !== null) lines.push(`Last connect response: ${seconds(responseMs)} (activation acknowledged)`);
      if (!fresh) {
        callbackSample = null;
        lines.push("Waiting for a fresh input status sample.");
      } else if (!next?.available || !input?.available) {
        lossAt = returnMs = callbackSample = null;
        lines.push("Input status unavailable; previous readings are stale.");
      } else {
        const verified = input.desiredConnected && (next.devices || []).filter(item => item.connected && item.input && item.desiredInputSlots?.includes(0)).length === 1;
        if (desired && !verified) {
          if (lossAt === null) lossAt = now();
          returnMs = null;
          lines.push(`Waiting for selected input: ${seconds(now() - lossAt)} since first unverified observation.`);
        } else if (lossAt !== null) {
          returnMs = now() - lossAt; lossAt = null;
        }
        if (returnMs !== null) lines.push(`Observed input return: ${seconds(returnMs)} between UI samples; cable-to-ready latency is unmeasured.`);
        const count = input.callbacks;
        const key = JSON.stringify([desired, input.deviceId, input.executionBackend]);
        if (input.active && verified && Number.isSafeInteger(count) && count >= 0) {
          const previous = callbackSample;
          callbackSample = {key, count};
          const activity = !previous || previous.key !== key ? "waiting for a second active sample"
            : count > previous.count ? `increased by ${count - previous.count} since last sample`
            : count === previous.count ? "unchanged since last sample" : "counter reset; waiting for next sample";
          lines.push(`Reported callbacks: ${count} · ${activity}.`);
        } else {
          callbackSample = null;
          lines.push(input.active ? "Callback activity unverified." : "Capture is stopped; no live callback comparison.");
        }
        lines.push(`Backend: ${input.executionBackend || "unreported"} · configured ${positive(input.configuredSampleRate)} Hz / ${positive(input.configuredChannels)} channels / ${positive(input.configuredPeriodFrames)} frames · ${input.configuredSampleFormat || "unreported"}.`);
        lines.push(`Reported xruns: ${number(input.xruns)} · dropped frames: ${number(input.droppedFrames)} · queued frames: ${number(input.queuedFrames)}.`);
        if (input.error) lines.push(`Input error: ${input.error}`);
      }
      write(metrics, lines.join(" "));
    }
    async function readStatus() {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 6000);
      try { return await request("/api/v1/audio/devices", {signal:controller.signal}); }
      catch (error) { if (controller.signal.aborted) throw new Error("status check timed out"); throw error; }
      finally { clearTimeout(timeout); }
    }
    function update(next, fresh = true) {
      const view = describe(next);
      if (view.desired !== desired) { interrupted = false; notice = ""; desired = view.desired; lossAt = returnMs = responseMs = callbackSample = null; }
      const input = next?.inputs?.find(item => item.slot === 0);
      const previous = data?.inputs?.find(item => item.slot === 0);
      if (input?.active !== previous?.active || input?.desiredConnected !== previous?.desiredConnected) notice = "";
      if (input?.active) interrupted = true;
      if (desired && input?.available && !input.desiredConnected) interrupted = true;
      data = next;
      write(status, notice || view.text);
      write(button, busy ? "Connecting…" : interrupted ? "Reconnect input" : "Connect input");
      button.disabled = busy || !view.canConnect;
      observe(next, input, fresh);
      return view;
    }
    async function poll() {
      if (busy || polling) return;
      const started = generation;
      polling = true;
      try {
        const next = await readStatus();
        if (!busy && started === generation) update(next);
      } catch (error) {
        if (!busy && started === generation) {
          button.disabled = true;
          write(status, `Input status unavailable: ${error.message}`);
          lossAt = returnMs = callbackSample = null;
          write(metrics, "Input status unavailable; previous readings are stale.");
        }
      } finally { polling = false; }
    }
    async function connect() {
      if (busy || button.disabled) return;
      const clickedDesired = desired;
      ++generation;
      busy = true; notice = ""; responseMs = null; update(data, false);
      try {
        const next = await readStatus();
        const view = update(next);
        if (view.desired !== clickedDesired) throw new Error("Selected input changed. Review it before connecting.");
        if (!view.canConnect) return;
        const input = next.inputs.find(item => item.slot === 0);
        const routed = Number(input.route?.gain || 0) > 0;
        if (routed && !confirmRoute(`Reconnect input with route gain ${input.route.gain} to graph output ${input.route.output ?? 0}?`)) return;
        const requestAt = now();
        const result = await request("/api/v1/audio/input/recover", {method:"POST", body:JSON.stringify({
          acknowledgeRecovery:true, acknowledgePhysicalInput:true, acknowledgeSignalRoute:routed,
          expectedDeviceId:view.desired, expectedRoute:input.route || {}, channels:2, conversionPolicy:getPolicy()
        })});
        if (!result.active) throw new Error("Capture did not start. Check the selected input and try again.");
        responseMs = now() - requestAt;
        update({...next, inputs:next.inputs.map(item => item.slot === 0 ? {...item, ...result} : item)}, false);
        await onRecovered();
      } catch (error) { notice = `Input connection failed: ${error.message}`; }
      finally { busy = false; update(data, false); }
    }
    button.addEventListener("click", connect);
    return {poll, connect};
  }
  globalThis.StageMeshInputRecovery = {describe, create};
})();
