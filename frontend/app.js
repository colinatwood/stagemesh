(() => {
  const q = (s) => document.querySelector(s);
  const qa = (s) => [...document.querySelectorAll(s)];
  q("#audioProbeRun").addEventListener("click", async () => {
    const button = q("#audioProbeRun"), status = q("#audioProbeStatus");
    button.disabled = true; status.textContent = "Checking hardware constraints…";
    try {
      const report = await api("/api/v1/hardware/audio-preflight", {method:"POST", body:JSON.stringify({
        address:q("#audioProbeAddress").value, direction:q("#audioProbeDirection").value,
        sampleRate:Number(q("#audioProbeRate").value), channels:Number(q("#audioProbeChannels").value),
        periodFrames:Number(q("#audioProbePeriod").value), format:q("#audioProbeFormat").value
      })});
      status.textContent = `${report.status}: ${report.nextAction} Audio has not been started by this check.`;
    } catch (error) { status.textContent = `Preflight failed: ${error.message}`; }
    finally { button.disabled = false; }
  });
  q("#hardwareRescan").addEventListener("click", async () => {
    const button = q("#hardwareRescan");
    const status = q("#hardwareDiagnosisStatus");
    const list = q("#hardwareDiagnosisDevices");
    button.disabled = true;
    list.replaceChildren();
    status.textContent = "Scanning server hardware…";
    try {
      const report = await api("/api/v1/hardware/diagnostics");
      status.textContent = `${report.host.os} ${report.host.release}: ${report.devices.length} USB entries. ${report.issues.join(" ")} Discovery does not establish audio readiness.`;
      const addLinks = (container, links) => links.forEach(link => {
        const url = new URL(link.url);
        if (url.protocol !== "https:") return;
        const a = document.createElement("a");
        a.textContent = link.label;
        a.href = url.href;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        const p = document.createElement("p"); p.append(a); container.append(p);
      });
      addLinks(list, report.officialGuidance);
      report.devices.forEach(device => {
        const row = document.createElement("div");
        const text = document.createElement("p");
        text.textContent = `${device.name} (${device.hardwareId || "unknown ID"}): ${device.diagnosis}. ${device.nextAction}`;
        row.append(text); addLinks(row, device.driverLookup); list.append(row);
      });
    } catch (error) { status.textContent = `Hardware scan failed: ${error.message}`; }
    finally { button.disabled = false; }
  });
  let snapshot = null;
  let selectedPlayer = null;
  let pendingMonitorTimer = null;
  let localClockAtFetch = performance.now();
  let localClockSeconds = 0;
  let localClockRunning = false;
  let eventStream = null;
  let midiDeviceState = null;
  let midiMappingState = null;
  let midiMappingTargets = null;
  let audioDeviceState = null;
  let lightingNetworkState = null;
  let nodeState = null;
  let failoverState = null;
  let handoffState = null;
  let handoffDecisionState = null;
  let technologyAssessmentState = null;
  let venueAdaptationState = null;
  let venueReconciliationState = null;
  let selectedVenueAdaptationId = null;
  let userProfileState = null;
  let dawSessionState = null;
  let dawSelectedClipId = null;
  let launcherState = null;

  function commandId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function bootstrapDesktopSession() {
    const fragment = new URLSearchParams(globalThis.location.hash.replace(/^#/, ""));
    const token = fragment.get("stagemesh-session") || "";
    if (!token) return Promise.resolve();
    globalThis.history.replaceState(null, "", globalThis.location.pathname + globalThis.location.search);
    return fetch("/desktop/session", {
      method: "POST",
      headers: {"X-StageMesh-Desktop-Token": token}
    }).then(async (response) => {
      if (response.ok) return;
      const result = await response.json().catch(() => ({}));
      throw new Error(result.error || `Desktop session failed (${response.status})`);
    });
  }

  const desktopReady = bootstrapDesktopSession();

  async function api(path, options = {}) {
    await desktopReady;
    const response = await fetch(path, {
      ...options,
      headers: {"Content-Type": "application/json", ...(options.headers || {})}
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || `HTTP ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }
  globalThis.StageMeshUI = Object.freeze({api});

  function playerById(id) {
    return snapshot?.players.find((p) => p.id === id) || null;
  }

  function render(state) {
    if (snapshot && state.revision < snapshot.revision) return;
    snapshot = state;
    localClockAtFetch = performance.now();
    localClockSeconds = state.transport.seconds;
    localClockRunning = state.transport.running;
    q("#bpm").value = state.transport.bpm;
    q("#key").value = state.transport.key;
    q("#play").textContent = state.transport.running ? "❚❚" : "▶";
    q("#quality").textContent = state.system.quality + "%";
    q("#qualityBar").style.width = state.system.quality + "%";
    q("#capacity").value = state.system.capacity;
    q("#capacityValue").textContent = Math.round(state.system.capacity) + "%";
    q("#systemMode").value = state.system.mode;
    q("#modeTag").textContent = state.system.mode.toUpperCase();
    q("#venue").textContent = state.system.venue;
    q("#manager").textContent = state.system.productionManager;
    q("#revision").textContent = `REV ${state.revision}`;
    if (state.audio) {
      q("#limiterCeiling").value = state.audio.limiterCeilingDb;
      q("#limiterValue").textContent = `${Number(state.audio.limiterCeilingDb).toFixed(1)} dBFS`;
      const route = state.audio.inputRoute || {output:0, gain:0};
      if (document.activeElement !== q("#audioInputRouteOutput")) q("#audioInputRouteOutput").value = route.output ?? 0;
      if (document.activeElement !== q("#audioInputRouteGain")) q("#audioInputRouteGain").value = route.gain ?? 0;
      const playerSelect = q("#audioInputPlayer");
      const options = [`<option value="">Unassigned source</option>`, ...(state.players || []).map((player) => `<option value="${escapeHtml(player.id)}">${escapeHtml(player.name)} · ${escapeHtml(player.role)}</option>`)];
      if (document.activeElement !== playerSelect) { playerSelect.innerHTML = options.join(""); playerSelect.value = state.audio.inputPlayerId || ""; }
    }
    if (state.technology && document.activeElement !== q("#technologyParticipants")) q("#technologyParticipants").value = state.technology.ecosystemParticipants || 1;
    const lightingNetwork = state.lighting?.network;
    if (lightingNetwork) {
      if (document.activeElement !== q("#lightingProtocol")) q("#lightingProtocol").value = lightingNetwork.protocol || "artnet";
      if (document.activeElement !== q("#lightingTarget")) q("#lightingTarget").value = lightingNetwork.target || "";
      if (document.activeElement !== q("#lightingPort")) q("#lightingPort").value = lightingNetwork.port || 6454;
      if (document.activeElement !== q("#lightingUniverseBase")) q("#lightingUniverseBase").value = lightingNetwork.universeBase || 1;
    }
    renderProtection(state.system);
    renderEvents(state.events);
    if (selectedPlayer) { renderMonitor(); renderNotation(); }
  }

  function renderProtection(system) {
    const keep = ["audio clock", "transport", "show state"];
    const reduce = [];
    if (system.mode !== "audio") keep.push("MIDI", "DMX", "cues", "logistics");
    if (system.capacity < 85 || system.mode !== "full") reduce.push("AI/background analysis");
    if (system.capacity < 70 || ["safe", "audio"].includes(system.mode)) reduce.push("3D/visual rendering");
    if (system.capacity < 55 || system.mode === "audio") reduce.push("heavy spatial/effects processing");
    q("#protectionSummary").textContent = `Keep: ${keep.join(", ")}. Reduce/suspend: ${reduce.length ? reduce.join(", ") : "nothing"}.`;
  }

  function renderEvents(events) {
    q("#events").innerHTML = events.slice(0, 7).map((e) =>
      `<div class="event"><strong>${escapeHtml(e.text)}</strong><span>${escapeHtml(e.category)} · ${e.showTimeSeconds.toFixed(3)} s · rev ${e.revision}</span></div>`
    ).join("");
  }

  function renderMonitor() {
    const player = playerById(selectedPlayer);
    if (!player) return;
    q("#playerTitle").textContent = `${player.name} · ${player.role}`;
    q("#monitorControls").classList.remove("hidden");
    qa("[data-player]").forEach((el) => el.classList.toggle("selected", el.dataset.player === selectedPlayer));
    qa("[data-monitor]").forEach((input) => {
      const key = input.dataset.monitor;
      if (document.activeElement !== input) input.value = player.monitor[key];
      q(`#v-${key}`).textContent = Math.round(player.monitor[key]) + "%";
    });
    q("#muteMine").textContent = player.monitor.muted ? "Unmute mine" : "Mute mine";
  }

  function notationById(id) {
    return snapshot?.notation?.[id] || null;
  }

  function renderNotation() {
    const part = notationById(selectedPlayer);
    if (!part) return;
    q("#notationControls").classList.remove("hidden");
    q("#notationEnabled").checked = Boolean(part.settings.enabled);
    q("#notationGrid").value = part.settings.quantize;
    q("#notationCount").textContent = `${part.notes.length} NOTES`;
    q("#musicXml").href = `/api/v1/players/${encodeURIComponent(selectedPlayer)}/notation.musicxml`;
    const notes = part.notes.slice(-16);
    q("#notationPreview").innerHTML = notes.length
      ? staffSvg(notes) + `<div class="noteStrip">${notes.map((n) => `<span class="noteToken" title="raw ${Number(n.rawStartSeconds).toFixed(3)}s">${escapeHtml(n.name)} · ${Number(n.durationBeats).toFixed(2)}b</span>`).join("")}</div>`
      : "No completed notes captured yet.";
  }

  function staffSvg(notes) {
    const width = 520, height = 112, left = 28, right = 500;
    const lines = [32,42,52,62,72].map((y) => `<line x1="${left}" y1="${y}" x2="${right}" y2="${y}"/>`).join("");
    const stepIndex = {C:0,D:1,E:2,F:3,G:4,A:5,B:6};
    const starts = notes.map((n) => Number(n.startBeats));
    const minStart = Math.min(...starts);
    const maxStart = Math.max(...starts, minStart + 4);
    const span = Math.max(4, maxStart - minStart + 1);
    const marks = notes.map((n) => {
      const diatonic = Number(n.octave) * 7 + stepIndex[n.step];
      const y = 72 - (diatonic - 30) * 5; // E4 is the treble staff bottom line.
      const x = left + 20 + ((Number(n.startBeats) - minStart) / span) * (right - left - 50);
      const ledger = [];
      if (y >= 77) for (let ly=82; ly<=y+1; ly+=10) ledger.push(`<line class="ledger" x1="${x-8}" y1="${ly}" x2="${x+8}" y2="${ly}"/>`);
      if (y <= 27) for (let ly=22; ly>=y-1; ly-=10) ledger.push(`<line class="ledger" x1="${x-8}" y1="${ly}" x2="${x+8}" y2="${ly}"/>`);
      const accidental = Number(n.alter) > 0 ? "♯" : Number(n.alter) < 0 ? "♭" : "";
      return `${ledger.join("")}<g><title>${escapeHtml(n.name)} at ${Number(n.startBeats).toFixed(2)} beats</title>${accidental ? `<text class="accidental" x="${x-12}" y="${y+4}">${accidental}</text>` : ""}<ellipse class="noteHead" cx="${x}" cy="${y}" rx="6" ry="4"/><line class="stem" x1="${x+5}" y1="${y}" x2="${x+5}" y2="${y-24}"/></g>`;
    }).join("");
    return `<svg class="staff" viewBox="0 0 ${width} ${height}" role="img" aria-label="Auto notation staff preview"><g class="staffLines">${lines}</g><text class="clefLabel" x="3" y="55">𝄞</text>${marks}</svg>`;
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));
  }

  async function refresh() {
    try {
      const state = await api("/api/v1/state");
      render(state);
      q("#connection").textContent = eventStream ? "LIVE" : "CONNECTED";
      return state;
    } catch (error) {
      q("#connection").textContent = "OFFLINE";
      console.error(error);
    }
  }

  function renderLauncher(state) {
    launcherState=state;q("#launcherAuthority").textContent=String(state.authority||"core").toUpperCase();
    q("#launcherPlay").setAttribute("aria-pressed",String(Boolean(state.transport?.running)));
    const pads=(state.pads||[]).map((pad)=>`<button class="launcherPad ${state.feedback?.resourceId===pad.resourceId?"triggered":""}" type="button" data-launcher-pad="${escapeHtml(pad.padId)}" data-resource="${escapeHtml(pad.resourceId)}" ${pad.ready?"":"disabled"} aria-label="Trigger ${escapeHtml(pad.label)} with key ${escapeHtml(pad.shortcut)}"><span>${escapeHtml(pad.label)}</span><small>${escapeHtml(pad.mode)} · <kbd>${escapeHtml(pad.shortcut)}</kbd></small></button>`);
    q("#launcherPads").innerHTML=pads.length?pads.join(""):'<p class="hint">Preload short DAW clips to populate up to eight performance pads.</p>';
    const capture=state.capture||{};q("#launcherStatus").textContent=`${state.transport?.bpm||120} BPM · ${state.transport?.key||"C"} · capture ${capture.state||"idle"} · ${capture.dropoutBlocks||0} gaps · output remains separately armed`;
    const feedback=state.feedback||{};q("#launcherFeedback").textContent=feedback.sequence?`${String(feedback.source).toUpperCase()} · ${feedback.action}`:`MIDI ${feedback.nativeMidiSubmitted||0}`;
  }

  async function refreshLauncher(){try{renderLauncher(await api("/api/v1/stage/launcher"));}catch(error){q("#launcherStatus").textContent=error.message;}}
  async function launcherAction(action,source="touch",extra={}){const state=await api("/api/v1/stage/launcher/action",{method:"POST",body:JSON.stringify({action,source,actionId:commandId(),...extra})});renderLauncher(state);return state;}

  function preferenceValue(profile, namespace, key, fallback) {
    const matches=(profile?.preferences||[]).filter((item)=>item.namespace===namespace&&item.key===key);
    matches.sort((a,b)=>(a.revision||0)-(b.revision||0));
    return matches.length ? matches[matches.length-1].value : fallback;
  }

  async function refreshProfile() {
    try {
      const [profile,projection]=await Promise.all([api("/api/v1/profile"),api("/api/v1/profile/projection")]);
      userProfileState=profile;
      q("#profileDensity").value=preferenceValue(profile,"org.upp.ui","density","comfortable");
      q("#profileContrast").value=preferenceValue(profile,"org.upp.accessibility","contrast","standard");
      q("#profileReducedMotion").checked=Boolean(preferenceValue(profile,"org.upp.accessibility","reduced-motion",false));
      q("#profileLayout").value=preferenceValue(profile,"org.upp.controls","layout","performer-default");
      q("#profileStatus").textContent=`${profile.profileId} · revision ${profile.revision} · unknown fields preserved`;
      const consent=projection.consentRequired||[];
      q("#projectionStatus").textContent=consent.length ? `${consent.length} displacement(s) require consent before activation.` : "Projection is compatible; no preference displacement requires consent.";
      q("#projectionValues").innerHTML=(projection.values||[]).slice(0,12).map((item)=>`<div class="midiDevice"><strong>${escapeHtml(item.namespace)} / ${escapeHtml(item.key)}</strong><div class="hint">${escapeHtml(item.layer)} · ${escapeHtml(JSON.stringify(item.value))}</div></div>`).join("");
      document.documentElement.dataset.density=q("#profileDensity").value;
      document.documentElement.dataset.contrast=q("#profileContrast").value;
      document.documentElement.dataset.reducedMotion=String(q("#profileReducedMotion").checked);
    } catch(error) { q("#profileStatus").textContent=error.message; }
  }

  async function saveProfile() {
    const previous=userProfileState||{profileId:"default",revision:0,preferences:[]};
    const revision=Number(previous.revision||0)+1;
    const retained=(previous.preferences||[]).filter((item)=>!["org.upp.ui/density","org.upp.accessibility/contrast","org.upp.accessibility/reduced-motion","org.upp.controls/layout"].includes(`${item.namespace}/${item.key}`));
    const pref=(namespace,key,type,value)=>({namespace,key,layer:"user",type,value,revision});
    const next={...previous,revision,preferences:[...retained,pref("org.upp.ui","density","token",q("#profileDensity").value),pref("org.upp.accessibility","contrast","token",q("#profileContrast").value),pref("org.upp.accessibility","reduced-motion","boolean",q("#profileReducedMotion").checked),pref("org.upp.controls","layout","token",q("#profileLayout").value.trim()||"performer-default")]};
    await api("/api/v1/profile",{method:"POST",body:JSON.stringify(next)});await refreshProfile();
  }

  function renderDaw(session) {
    dawSessionState=session;const tracks=session.tracks||[];const zoomSeconds=Number(q("#dawZoom")?.value||60);
    q("#dawStatus").textContent=`${session.sessionId} · revision ${session.revision} · ${tracks.length} tracks · float32 / 192 kHz`;
    q("#dawClipTrack").innerHTML=tracks.map((track)=>`<option value="${escapeHtml(track.trackId)}">${escapeHtml(track.name)}</option>`).join("");
    q("#dawTracks").innerHTML=tracks.map((track)=>`<div class="dawTrack"><div><strong>${escapeHtml(track.name)}</strong><span>${escapeHtml(track.kind)} · gain ${Number(track.gain).toFixed(2)} · pan ${Number(track.pan).toFixed(2)}</span><div class="dawMixer"><label>Gain<input type="range" min="0" max="4" step="0.01" value="${Number(track.gain)}" data-daw-field="gain" data-daw-track="${escapeHtml(track.trackId)}"></label><label>Pan<input type="range" min="-1" max="1" step="0.01" value="${Number(track.pan)}" data-daw-field="pan" data-daw-track="${escapeHtml(track.trackId)}"></label><button type="button" class="${track.muted?"active":""}" data-daw-toggle="muted" data-daw-track="${escapeHtml(track.trackId)}">M</button><button type="button" class="${track.solo?"active":""}" data-daw-toggle="solo" data-daw-track="${escapeHtml(track.trackId)}">S</button></div></div><div class="dawLane" data-daw-lane="${escapeHtml(track.trackId)}">${(track.clips||[]).map((clip)=>`<button type="button" class="dawClip ${clip.clipId===dawSelectedClipId?"selected":""}" data-daw-clip="${escapeHtml(clip.clipId)}" data-daw-track="${escapeHtml(track.trackId)}" title="${escapeHtml(clip.source?.uri||clip.clipId)}" style="--clip-left:${Math.min(100,Number(clip.startFrame)/(192000*zoomSeconds)*100)}%;--clip-width:${Math.max(1,Math.min(100,Number(clip.lengthFrames)/(192000*zoomSeconds)*100))}%"><i data-daw-resize="start" aria-hidden="true"></i><span>${escapeHtml(clip.clipId)}</span><i data-daw-resize="end" aria-hidden="true"></i></button>`).join("")}</div></div>`).join("")||'<p class="hint">Add an audio track to begin arranging.</p>';
    const selectClip=(clipId)=>{dawSelectedClipId=clipId;q("#dawSelectedClip").value=clipId;renderDaw(dawSessionState);renderDawWaveform().catch((error)=>q("#dawWaveform").textContent=error.message);};
    if(globalThis.StageMeshArrangement)globalThis.StageMeshArrangement.bindClips({doc:document,session:dawSessionState,zoomSeconds,snap:q("#dawSnap").value,onSelect:(clipIds,primary)=>selectClip(primary),onEdit:(body)=>dawEdit(body)});
    else qa("[data-daw-clip]").forEach((button)=>button.addEventListener("click",()=>selectClip(button.dataset.dawClip)));
    globalThis.StageMeshMarkers?.render({doc:document,session:dawSessionState,zoomSeconds,snap:q("#dawSnap").value,onEdit:(body)=>dawMarkerEdit(body)});
    globalThis.StageMeshAutomation?.render({doc:document,session:dawSessionState,zoomSeconds,onEdit:(body)=>dawAutomationEdit(body)});
    qa("[data-daw-field]").forEach((input)=>input.addEventListener("change",()=>updateDawTrack(input.dataset.dawTrack,input.dataset.dawField,Number(input.value))));
    qa("[data-daw-toggle]").forEach((button)=>button.addEventListener("click",()=>{const track=tracks.find((item)=>item.trackId===button.dataset.dawTrack);return updateDawTrack(button.dataset.dawTrack,button.dataset.dawToggle,!Boolean(track?.[button.dataset.dawToggle]));}));
  }
  async function updateDawTrack(trackId,field,value){const next=structuredClone(dawSessionState);const track=next.tracks.find((item)=>item.trackId===trackId);if(!track)return;track[field]=value;await saveDaw(next);}
  async function renderDawWaveform(){const clip=(dawSessionState?.tracks||[]).flatMap((track)=>track.clips||[]).find((item)=>item.clipId===dawSelectedClipId);if(!clip?.source?.uri){q("#dawWaveform").textContent="Selected clip has no inspectable WAV source.";return;}q("#dawWaveform").textContent="Inspecting source peaks…";const media=await api("/api/v1/daw/media/inspect",{method:"POST",body:JSON.stringify({path:clip.source.uri,peakBuckets:256})});const buckets=media.waveform?.buckets||[];if(!buckets.length){q("#dawWaveform").textContent="No waveform samples available.";return;}const width=512,height=80,mid=height/2;const lines=buckets.map((bucket,index)=>{const peak=bucket[0]||{min:0,max:0};const x=(index+.5)*width/buckets.length;const y1=mid-Number(peak.max)*mid;const y2=mid-Number(peak.min)*mid;return `<line x1="${x.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x.toFixed(2)}" y2="${y2.toFixed(2)}"/>`;}).join("");q("#dawWaveform").innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Waveform peaks for ${escapeHtml(clip.clipId)}"><line class="axis" x1="0" y1="${mid}" x2="${width}" y2="${mid}"/>${lines}</svg>`;}
  async function refreshDaw(){try{renderDaw(await api("/api/v1/daw/session"));}catch(error){q("#dawStatus").textContent=error.message;}}
  async function saveDaw(next){next.revision=Number(dawSessionState?.revision||0)+1;renderDaw(await api("/api/v1/daw/session",{method:"POST",body:JSON.stringify(next)}));}
  async function addDawTrack(){const name=q("#dawTrackName").value.trim();if(!name)return;const next=structuredClone(dawSessionState);next.tracks.push({trackId:`track-${Date.now()}`,name,kind:"audio",gain:1,pan:0,clips:[]});await saveDaw(next);q("#dawTrackName").value="";}
  async function addDawClip(){const next=structuredClone(dawSessionState);const track=next.tracks.find((item)=>item.trackId===q("#dawClipTrack").value);if(!track)return;const uri=q("#dawClipUri").value.trim();if(!uri)return;track.clips.push({clipId:`clip-${Date.now()}`,startFrame:Math.round(Number(q("#dawClipStart").value)*192000),lengthFrames:Math.max(1,Math.round(Number(q("#dawClipDuration").value)*192000)),sourceOffsetFrames:0,source:{type:"audio-file",uri}});await saveDaw(next);}
  async function dawEdit(body){const clipId=body.clipId||dawSelectedClipId;if(!clipId&&body.op!=="moveMany")return;renderDaw(await api("/api/v1/daw/edit",{method:"POST",body:JSON.stringify({...(clipId?{clipId}:{}),expectedRevision:dawSessionState.revision,...body})}));}
  async function dawMarkerEdit(body){renderDaw(await api("/api/v1/daw/markers",{method:"POST",body:JSON.stringify({expectedRevision:dawSessionState.revision,...body})}));}
  async function dawAutomationEdit(body){renderDaw(await api("/api/v1/daw/automation",{method:"POST",body:JSON.stringify({expectedRevision:dawSessionState.revision,...body})}));}


  function renderAudioDevices(data) {
    audioDeviceState = data;
    const devices = Array.isArray(data?.devices) ? data.devices : [];
    const desired = data?.desiredDeviceId || snapshot?.audio?.deviceId || "null-audio";
    const desiredInput = data?.desiredInputDeviceId || snapshot?.audio?.inputDeviceId || "";
    q("#audioBackend").textContent = data?.available
      ? `${devices.length} discovered · out ${desired} · in ${desiredInput || "none"} · execution ${data.executionBackend || "unknown"}`
      : `Native audio unavailable · desired mappings preserved`;
    q("#audioDevices").innerHTML = devices.length ? devices.map((device) => {
      const outputSelected = device.id === desired;
      const inputSelected = device.id === desiredInput;
      const labels = [];
      if (outputSelected) labels.push(device.connected ? "OUT" : "OUT PENDING");
      if (inputSelected) labels.push(device.connected ? "IN" : "IN PENDING");
      if (!labels.length) labels.push(device.connected ? "AVAILABLE" : "OFFLINE");
      const outButton = device.output ? `<button type="button" data-audio-select="${escapeHtml(device.id)}" ${outputSelected ? "disabled" : ""}>${outputSelected ? "Output selected" : "Use output"}</button>` : "";
      const inButton = device.input ? `<button type="button" data-audio-input-select="${escapeHtml(device.id)}" ${inputSelected ? "disabled" : ""}>${inputSelected ? "Input selected" : "Use input"}</button>` : "";
      const rebindOut = device.output && desired && device.id !== desired && device.reconnectStatus === "explicit-recovery-required" ? `<button type="button" data-audio-rebind="output" data-audio-current="${escapeHtml(device.id)}" data-audio-desired="${escapeHtml(desired)}">Trust as output replacement</button>` : "";
      const rebindIn = device.input && desiredInput && device.id !== desiredInput && device.reconnectStatus === "explicit-recovery-required" ? `<button type="button" data-audio-rebind="input" data-audio-current="${escapeHtml(device.id)}" data-audio-desired="${escapeHtml(desiredInput)}">Trust as input replacement</button>` : "";
      return `<div class="midiDevice ${(outputSelected || inputSelected) && !device.connected ? "midiPending" : ""}"><div class="midiDeviceHead"><div><strong>${escapeHtml(device.name || device.id)}</strong><div class="hint">${escapeHtml(device.backend || "unknown")} · ${escapeHtml(device.id)} · ${escapeHtml(device.identityStrength || "volatile")}</div></div><span>${labels.join(" · ")}</span></div><div class="pair">${outButton}${inButton}${rebindOut}${rebindIn}</div></div>`;
    }).join("") : '<div class="hint">No native audio endpoints reported. Desired mappings remain in show state.</div>';
    qa("[data-audio-select]").forEach((button) => button.addEventListener("click", async () => {
      await command("/api/v1/audio", "POST", {deviceId: button.dataset.audioSelect}, "audio");
      refreshAudioDevices();
    }));
    qa("[data-audio-input-select]").forEach((button) => button.addEventListener("click", async () => {
      await command("/api/v1/audio", "POST", {inputDeviceId: button.dataset.audioInputSelect}, "audio");
      refreshAudioDevices();
      refreshAudioInput();
    }));
    qa("[data-audio-rebind]").forEach((button) => button.addEventListener("click", async () => {
      if (!globalThis.confirm(`Trust ${button.dataset.audioCurrent} as the replacement for ${button.dataset.audioDesired}? All ${button.dataset.audioRebind} streams must be stopped.`)) return;
      await api("/api/v1/audio/identity/rebind", {method:"POST", body:JSON.stringify({desiredDeviceId:button.dataset.audioDesired,currentDeviceId:button.dataset.audioCurrent,direction:button.dataset.audioRebind,acknowledgeIdentityReplacement:true})});
      refreshAudioDevices();
    }));
  }

  async function refreshAudioDevices(rescan = false) {
    try {
      if (rescan) await api("/api/v1/audio/scan", {method:"POST", body:"{}"});
      renderAudioDevices(await api("/api/v1/audio/devices"));
    } catch (error) {
      q("#audioBackend").textContent = "Audio discovery unavailable";
      console.error(error);
    }
  }

  async function refreshAudioStream() {
    try {
      const response = await api("/api/v1/audio/outputs");
      const outputs = Array.isArray(response.outputs) ? response.outputs : [];
      const stream = outputs[0] || await api("/api/v1/audio/stream");
      const backend = stream.executionBackend || "unknown";
      const active = Boolean(stream.active);
      q("#audioStreamStatus").textContent = `FOH ${active ? "ACTIVE" : "IDLE"} · ${backend} · callbacks ${stream.callbacks || 0} · xruns ${stream.xruns || 0} · graph output ${stream.output || 0}`;
      q("#audioOutputSlots").innerHTML = outputs.map((item) => `<div class="midiDevice"><div class="midiDeviceHead"><div><strong>Output ${item.slot} · ${escapeHtml(item.purpose || "aux")}</strong><div class="hint">${escapeHtml(item.playerId || "shared bus")} · ${escapeHtml(item.desiredDeviceId || "no device")} · graph ${item.output ?? 0}</div></div><span>${item.active ? "ACTIVE" : item.desiredDeviceId ? "READY" : "EMPTY"}</span></div><div class="hint">callbacks ${item.callbacks || 0} · xruns ${item.xruns || 0} · fanout queued ${item.queuedFrames || 0} · dropped ${item.droppedFrames || 0} · underrun ${item.underrunFrames || 0}${item.rateMeasured ? ` · clock ${Number(item.ratePpm || 0).toFixed(1)} ppm` : ""}${item.driftEnabled ? ` · correction ${Number(item.correctionPpm || 0).toFixed(1)} ppm · adjusted ${item.compensatedBlocks || 0} blocks${item.driftPolicyApplied === false ? " · policy pending re-arm" : ""}` : " · drift raw"}${item.maxExcessGapMs ? ` · excess gap ${Number(item.maxExcessGapMs).toFixed(1)} ms` : ""}</div></div>`).join("");
      q("#activateAudio").disabled = active;
      q("#deactivateAudio").disabled = !active;
    } catch (error) {
      q("#audioStreamStatus").textContent = "Audio execution stream unavailable";
      q("#audioOutputSlots").innerHTML = "";
      console.error(error);
    }
  }

  async function refreshAudioInput() {
    try {
      const response = await api("/api/v1/audio/inputs");
      const inputs = Array.isArray(response.inputs) ? response.inputs : [];
      const input = inputs[0] || {};
      const desired = snapshot?.audio?.inputDeviceId || "none";
      const active = Boolean(input.active);
      q("#audioInputStatus").textContent = `Slot 0 ${active ? "ACTIVE" : "IDLE"} · desired ${desired || "none"} · ${input.executionBackend || "none"} · source ${input.source ?? 24}`;
      q("#audioInputSlots").innerHTML = inputs.map((item) => `<div class="midiDevice"><div class="midiDeviceHead"><div><strong>Input ${item.slot}</strong><div class="hint">${escapeHtml(item.playerId || "unassigned")} · ${escapeHtml(item.desiredDeviceId || "no device")} · source ${item.source}</div></div><span>${item.active ? "ACTIVE" : item.desiredDeviceId ? "READY" : "EMPTY"}</span></div><div class="hint">FOH out ${item.route?.output ?? 0} @ ${Number(item.route?.gain || 0).toFixed(2)} · queued ${item.queuedFrames || 0} · dropped ${item.droppedFrames || 0}</div></div>`).join("");
      q("#activateAudioInput").disabled = active || !snapshot?.audio?.inputDeviceId;
      q("#deactivateAudioInput").disabled = !active;
    } catch (error) {
      q("#audioInputStatus").textContent = "Audio input execution unavailable";
      q("#audioInputSlots").innerHTML = "";
    }
  }

  function renderLightingNetwork(data) {
    lightingNetworkState = data;
    const desired = data?.desired || snapshot?.lighting?.network || {};
    if (document.activeElement !== q("#lightingProtocol")) q("#lightingProtocol").value = desired.protocol || data?.protocol || "artnet";
    if (document.activeElement !== q("#lightingTarget")) q("#lightingTarget").value = desired.target || "";
    if (document.activeElement !== q("#lightingPort")) q("#lightingPort").value = desired.port || 6454;
    if (document.activeElement !== q("#lightingUniverseBase")) q("#lightingUniverseBase").value = desired.universeBase || data?.universeBase || 1;
    const armed = Boolean(data?.armed);
    q("#armLighting").textContent = armed ? "Disarm physical output" : "Arm physical output";
    const protocol = data?.protocol || desired.protocol || "artnet";
    const universe = protocol === "sacn" ? ` · universe base ${data?.universeBase || desired.universeBase || 1}` : "";
    q("#lightingNetworkStatus").textContent = `${armed ? "ARMED" : "DISARMED"} · ${protocol.toUpperCase()} · ${data?.configured ? `${data.target}:${data.port}` : "no active target"}${universe} · packets ${data?.packetsSent || 0} · errors ${data?.sendErrors || 0}`;
  }

  async function refreshLightingNetwork() {
    try {
      renderLightingNetwork(await api("/api/v1/lighting/network"));
    } catch (error) {
      q("#lightingNetworkStatus").textContent = "Lighting network unavailable";
      console.error(error);
    }
  }

  function renderMidiDevices(data) {
    midiDeviceState = data;
    const devices = Array.isArray(data?.devices) ? data.devices : [];
    const bindings = data?.bindings || {};
    q("#midiBackend").textContent = data?.available
      ? `${data.backend || "native"} · ${devices.length} discovered · ${Object.keys(bindings).length} mapped`
      : `Native MIDI unavailable · ${Object.keys(bindings).length} desired mappings preserved`;

    const seen = new Set();
    const cards = devices.map((device) => {
      seen.add(device.id);
      const playerId = bindings[device.id] || device.playerId || "";
      const playerOptions = (snapshot?.players || []).map((player) =>
        `<option value="${escapeHtml(player.id)}" ${player.id === playerId ? "selected" : ""}>${escapeHtml(player.name)} · ${escapeHtml(player.role)}</option>`
      ).join("");
      return `<div class="midiDevice" data-midi-card="${escapeHtml(device.id)}"><div class="midiDeviceHead"><div><strong>${escapeHtml(device.name || device.id)}</strong><div class="hint">${escapeHtml(device.id)}</div></div><span>${device.connected ? (playerId ? "MAPPED" : "AVAILABLE") : "OFFLINE"}</span></div><div class="midiDeviceControls"><select data-midi-player="${escapeHtml(device.id)}"><option value="">Choose player…</option>${playerOptions}</select><button type="button" data-midi-bind="${escapeHtml(device.id)}">${playerId ? "Update" : "Bind"}</button></div>${playerId ? `<button class="midiDetach" type="button" data-midi-detach="${escapeHtml(device.id)}">Forget mapping</button>` : ""}</div>`;
    });
    for (const [deviceId, playerId] of Object.entries(bindings)) {
      if (seen.has(deviceId)) continue;
      const player = playerById(playerId);
      cards.push(`<div class="midiDevice midiPending"><div class="midiDeviceHead"><div><strong>${escapeHtml(deviceId)}</strong><div class="hint">Expected for ${escapeHtml(player?.name || playerId)}</div></div><span>PENDING</span></div><button class="midiDetach" type="button" data-midi-detach="${escapeHtml(deviceId)}">Forget mapping</button></div>`);
    }
    q("#midiDevices").innerHTML = cards.length ? cards.join("") : '<div class="hint">No MIDI input devices detected. Desired mappings will reattach when matching endpoints appear.</div>';

    qa("[data-midi-bind]").forEach((button) => button.addEventListener("click", async () => {
      const deviceId = button.dataset.midiBind;
      const select = q(`[data-midi-player="${CSS.escape(deviceId)}"]`);
      const playerId = select?.value;
      if (!playerId) return;
      await command(`/api/v1/midi/devices/${encodeURIComponent(deviceId)}/attach`, "POST", {playerId}, "midi-bindings");
      refreshMidiDevices();
    }));
    qa("[data-midi-detach]").forEach((button) => button.addEventListener("click", async () => {
      const deviceId = button.dataset.midiDetach;
      await command(`/api/v1/midi/devices/${encodeURIComponent(deviceId)}/detach`, "POST", {}, "midi-bindings");
      refreshMidiDevices();
    }));
  }

  async function refreshMidiDevices(rescan = false) {
    try {
      if (rescan) await api("/api/v1/midi/scan", {method:"POST", body:"{}"});
      renderMidiDevices(await api("/api/v1/midi/devices"));
    } catch (error) {
      q("#midiBackend").textContent = "MIDI discovery unavailable";
      console.error(error);
    }
  }

  function renderMidiMappings(status) {
    midiMappingState=status;const learning=status.learning;const panel=q(".midiLearnPanel");panel.classList.toggle("waiting",Boolean(learning));q("#midiLearnState").textContent=learning?"MOVE A CONTROL":"READY";q("#midiLearnHint").textContent=learning?`Waiting for a pad, knob, or slider for ${learning.target.name}…`:"Choose a target, click Learn, then move one knob, slider, or pad.";
    const mappings=status.mappings||[];q("#midiMappings").innerHTML=mappings.length?mappings.map((mapping)=>{const source=mapping.source;const control=source.message==="cc"?`CC ${source.number}`:source.message==="note"?`Note ${source.number}`:source.message;const resource=mapping.target.resourceId?` · clip ${escapeHtml(mapping.target.resourceId)}`:"";return `<div class="midiDevice"><div class="midiDeviceHead"><div><strong>${escapeHtml(mapping.name)}</strong><div class="hint midiMapSource">${escapeHtml(source.deviceId)} · ch ${Number(source.channel)+1} · ${escapeHtml(control)}</div></div><span>${escapeHtml(mapping.behavior.toUpperCase())}</span></div><div class="hint">${mapping.quantize==="off"?"immediate":`${escapeHtml(mapping.quantize)} beat sync`}${mapping.keySync?` · master ${escapeHtml(mapping.scale)} key`:""}${resource}</div><button type="button" data-midi-map-delete="${escapeHtml(mapping.mappingId)}">Remove mapping</button></div>`;}).join(""):'<div class="hint">No learned controls yet.</div>';
    qa("[data-midi-map-delete]").forEach((button)=>button.addEventListener("click",async()=>{await api(`/api/v1/midi/mappings/${encodeURIComponent(button.dataset.midiMapDelete)}/delete`,{method:"POST",body:"{}"});await refreshMidiMappings();}));
  }

  async function refreshMidiMappings(){try{if(!midiMappingTargets){midiMappingTargets=await api("/api/v1/midi/mapping-targets");q("#midiLearnTarget").innerHTML=(midiMappingTargets.targets||[]).map((target)=>`<option value="${escapeHtml(target.targetId)}">${escapeHtml(target.name)} · ${escapeHtml(target.suggestedControl)}</option>`).join("");}renderMidiMappings(await api("/api/v1/midi/mappings"));}catch(error){q("#midiLearnHint").textContent=error.message;}}

  async function refreshClockStatus() {
    try {
      const clock = await api("/api/v1/clock");
      const label = clock.source === "local" ? "CLOCK LOCAL" : `CLOCK ${String(clock.state || "--").toUpperCase()}`;
      q("#clockStatus").textContent = label;
      q("#clockStatus").title = `${clock.source} · offset ${clock.offsetNs} ns · drift ${Number(clock.driftPpm).toFixed(3)} ppm`;
    } catch (error) {
      q("#clockStatus").textContent = "CLOCK --";
    }
  }

  async function refreshNative() {
    try {
      const response = await fetch("/api/v1/native", {headers: {"Accept": "application/json"}});
      const native = await response.json();
      q("#nativeStatus").textContent = native.available ? "NATIVE LIVE" : "NATIVE FALLBACK";
    } catch (error) {
      q("#nativeStatus").textContent = "NATIVE --";
    }
  }

  async function refreshNodeStatus() {
    try {
      [nodeState, failoverState, handoffState, handoffDecisionState] = await Promise.all([api("/api/v1/node"), api("/api/v1/failover"), api("/api/v1/failover/readiness"), api("/api/v1/handoff/decision")]);
      const role = String(nodeState.role || "unknown").toUpperCase();
      q("#nodeStatus").textContent = `NODE ${role}`;
      const peer = nodeState.replicationTransport || {};
      q("#nodeAuthorityDetail").textContent = `${nodeState.nodeId} · epoch ${nodeState.epoch} · ${nodeState.physicalAuthority ? "physical authority available" : "physical authority fenced"}${nodeState.replicaAgeMs == null ? "" : ` · replica ${nodeState.replicaAgeMs} ms old`}${peer.peerUrl ? ` · peer ${peer.peerUrl}` : ""}`;
      const continuity = failoverState.continuity || {};
      const continuityText = continuity.measured ? ` · clock ${continuity.grade} ${Number(continuity.timelineErrorMs || 0).toFixed(1)} ms` : " · clock continuity unmeasured";
      const audioResume = continuity.firstAudioWriteAfterMs == null ? ` · audio ${continuity.audioResumptionGrade || "not-rearmed"}` : ` · first write ${Number(continuity.firstAudioWriteAfterMs).toFixed(1)} ms · ${continuity.audioResumptionGrade}${continuity.maxObservedOutputGapMs == null ? "" : ` · sink gap ${Number(continuity.maxObservedOutputGapMs).toFixed(1)} ms`}`;
      const programHandoff = continuity.crossNodeProgramGapMs == null
        ? ` · handoff ${continuity.handoffMode || "state-warm"}`
        : ` · program gap ${Number(continuity.crossNodeProgramGapMs || 0).toFixed(1)} ms${Number(continuity.crossNodeProgramOverlapMs || 0) > 0 ? ` / overlap ${Number(continuity.crossNodeProgramOverlapMs).toFixed(1)} ms` : ""} · ${continuity.crossNodeProgramGrade}`;
      const readiness = handoffState || {};
      const prebuffer = readiness.deterministicPrebufferEligible ? ` · prebuffer ${readiness.prebufferReady ? "ready" : "eligible"}` : "";
      const readinessText = readiness.sourceProgramCursorNs == null ? "" : ` · warm ${readiness.mode}${readiness.localLagMs == null ? "" : ` · lag ${Number(readiness.localLagMs).toFixed(1)} ms`}`;
      const decision = handoffDecisionState || {};
      const decisionText = decision.recommendedAction ? ` · logic ${decision.recommendedAction}${decision.programBlockers?.length ? ` · ${decision.programBlockers.length} program blocker${decision.programBlockers.length === 1 ? "" : "s"}` : ""}${decision.programLogicReady ? ` · execution ${decision.executionReady ? "ready" : "waiting"}` : ""}` : "";
      q("#failoverDetail").textContent = `Failover ${String(failoverState.state || "--").toUpperCase()} · suspect ${failoverState.suspectAfterMs} ms · eligible ${failoverState.promotionEligibleAfterMs} ms${continuityText}${audioResume}${programHandoff}${readinessText}${prebuffer}${decisionText}`;
      const witness = failoverState.witness || nodeState.witness || {};
      q("#witnessDetail").textContent = witness.configured ? `Witness ${witness.leaseValid ? "LEASED" : "NO LEASE"} · ${witness.witnesses} witnesses · quorum ${witness.quorum} · epoch ${witness.leaseEpoch || 0}${witness.leaseExpiresInMs == null ? "" : ` · ${witness.leaseExpiresInMs} ms left`}` : "Witness quorum not configured · manual failover mode";
      q("#toggleNodeRole").textContent = nodeState.role === "primary" ? "Make standby" : "Standby locked";
      q("#toggleNodeRole").disabled = nodeState.role !== "primary";
      q("#promoteFailover").disabled = !Boolean(failoverState.safeToPromote);
    } catch (error) {
      q("#nodeStatus").textContent = "NODE --";
      q("#nodeAuthorityDetail").textContent = "Node authority unavailable";
      q("#failoverDetail").textContent = "Failover status unavailable";
      q("#witnessDetail").textContent = "Witness status unavailable";
    }
  }

  async function refreshTechnologyOpenness() {
    try {
      technologyAssessmentState = await api("/api/v1/technology/assessment");
      const a = technologyAssessmentState;
      q("#technologyOpenStatus").textContent = `${String(a.openness || "--").toUpperCase()} · ${a.scaleTier || "emerging"} scale · Standard needs ${a.standardIndependentGroupsRequired} independent groups · Core needs ${a.coreIndependentGroupsRequired} · unknown preservation ${a.preserveUnknownCapabilities ? "ON" : "OFF"} · no-AI valid ${a.noAiParticipantValid ? "YES" : "NO"}`;
      const rows = Array.isArray(a.extensions) ? a.extensions : [];
      q("#technologyExtensions").innerHTML = rows.length ? rows.map((item) => `<div class="midiDevice"><div class="midiDeviceHead"><div><strong>${escapeHtml(item.id)}</strong><div class="hint">declared ${escapeHtml(item.declaredMaturity)} · eligible ${escapeHtml(item.highestEligibleMaturity)} · ${item.independentGroupCount} independent groups</div></div><span>${item.coreEligible ? "CORE-ELIGIBLE" : item.scaleRevalidationNeeded ? "REVALIDATE" : item.declaredMaturityValid ? "VALID" : "EVIDENCE NEEDED"}</span></div>${item.maturityBlockers?.length ? `<div class="hint">${item.maturityBlockers.map(escapeHtml).join(" · ")}</div>` : item.scaleRevalidationBlockers?.length ? `<div class="hint">Recognized standard; broader scale evidence: ${item.scaleRevalidationBlockers.map(escapeHtml).join(" · ")}</div>` : ""}</div>`).join("") : '<div class="hint">No technology extensions registered. Experimental namespaces remain valid without registration.</div>';
    } catch (error) {
      q("#technologyOpenStatus").textContent = "Technology openness assessment unavailable";
      q("#technologyExtensions").innerHTML = "";
    }
  }

  async function refreshCompatibility() {
    try {
      const [profile, show] = await Promise.all([api("/api/v1/compatibility"), api("/api/v1/compatibility/show-state")]);
      const caps = Array.isArray(profile.capabilities) ? profile.capabilities.length : 0;
      q("#compatibilityStatus").textContent = `UPP API ${profile.apiVersions?.join(", ") || "--"} · show ${String(show.mode || "--").toUpperCase()} · unknown preservation ${profile.preservesUnknown ? "ON" : "OFF"} · ${caps} capabilities`;
      const rows = [
        ["Show reader", `API ${show.currentApiVersion || 1} · minimum ${show.minimumReaderApiVersion || 1}`],
        ["Forward fields", show.unknownFieldsPreserved ? "PRESERVED" : "UNSAFE"],
        ["Offline", profile.offlineCapable ? "COMPATIBLE" : "DEPENDENT"],
      ];
      q("#compatibilityDetails").innerHTML = rows.map(([name,value]) => `<div class="midiDevice"><div class="midiDeviceHead"><strong>${escapeHtml(name)}</strong><span>${escapeHtml(value)}</span></div></div>`).join("");
    } catch (error) {
      q("#compatibilityStatus").textContent = "Compatibility status unavailable";
      q("#compatibilityDetails").innerHTML = "";
    }
  }

  async function refreshVenueCompatibility(useLocalDiscovery = false) {
    try {
      const plan = await api("/api/v1/venue/plan", { method: "POST", body: JSON.stringify({ useLocalDiscovery }) });
      const venueName = plan.venue?.name || plan.venue?.id || "venue";
      q("#venueCompatibilityStatus").textContent = `${venueName} · ${String(plan.grade || "--").toUpperCase()} · ${String(plan.readiness || "--").toUpperCase()} · ${plan.blockers?.length || 0} blocker${plan.blockers?.length === 1 ? "" : "s"}${useLocalDiscovery ? " · LIVE DISCOVERY" : " · PROFILE PREFLIGHT"}`;
      const rows = Array.isArray(plan.devicePlan) ? plan.devicePlan : [];
      q("#venueCompatibilityDetails").innerHTML = rows.length ? rows.map((item) => {
        const d = item.decision || {};
        const provider = item.provider ? `${item.provider.type}:${item.provider.name || item.provider.id}` : "none";
        const timing = item.timing?.status && item.timing.status !== "not-specified" ? ` · timing ${item.timing.status}` : "";
        const patch = item.patchStatus === "mapped" ? ` · patch ${item.patch?.target || "mapped"}` : " · patch UNMAPPED";
        return `<div class="midiDevice"><div class="midiDeviceHead"><div><strong>${escapeHtml(item.id)}</strong><div class="hint">${escapeHtml(d.status || "unknown")} · ${escapeHtml(d.quality || "--")} · ${escapeHtml(provider)}${escapeHtml(timing)}${escapeHtml(patch)}</div></div><span>${Number(d.qualityScore ?? 0)}%</span></div></div>`;
      }).join("") : '<div class="hint">No show requirements were generated for this venue plan.</div>';
    } catch (error) {
      q("#venueCompatibilityStatus").textContent = "Venue compatibility plan unavailable";
      q("#venueCompatibilityDetails").innerHTML = "";
    }
  }

  async function refreshVenueReconciliation(useLocalDiscovery = false) {
    try {
      const query = useLocalDiscovery ? "?useLocalDiscovery=1" : "";
      venueReconciliationState = await api(`/api/v1/venue/reconciliation${query}`);
      const status = String(venueReconciliationState.status || "--").toUpperCase();
      const realized = venueReconciliationState.realized ? "REALIZED" : "NOT PROVEN";
      const blockers = venueReconciliationState.blockers?.length || 0;
      const warnings = venueReconciliationState.warnings?.length || 0;
      q("#venueReconciliationStatus").textContent = `${status} · ${realized} · ${blockers} blocker${blockers === 1 ? "" : "s"} · ${warnings} warning${warnings === 1 ? "" : "s"}`;
      const rows = Array.isArray(venueReconciliationState.mappings) ? venueReconciliationState.mappings : [];
      q("#venueReconciliationDetails").innerHTML = rows.length ? rows.map((item) => {
        const provider = item.currentProvider ? `${item.currentProvider.type}:${item.currentProvider.name || item.currentProvider.id}` : "none";
        const evidence = item.evidence?.fresh ? `${item.evidenceStatus} · ${Number(item.evidence.ageMs || 0).toFixed(0)}ms old` : "unverified";
        return `<div class="midiDevice"><div class="midiDeviceHead"><div><strong>${escapeHtml(item.patchKey)}</strong><div class="hint">${escapeHtml(item.status)} · ${escapeHtml(provider)} · ${escapeHtml(evidence)}</div></div><span>${item.realized ? "REALIZED" : "CHECK"}</span></div>${item.reasons?.length ? `<div class="hint">${item.reasons.map(escapeHtml).join(" · ")}</div>` : ""}</div>`;
      }).join("") : '<div class="hint">No active patch mappings to reconcile.</div>';
      const authority = await api("/api/v1/venue/authority");
      const leases = Array.isArray(authority.active) ? authority.active : [];
      q("#venueAuthorityLeases").innerHTML = leases.length ? leases.map((lease) => `<div class="midiDevice"><div class="midiDeviceHead"><div><strong>${escapeHtml(lease.scope)}</strong><div class="hint">${escapeHtml(lease.grantee)} · ${Number(lease.remainingSeconds || 0).toFixed(0)}s remaining</div></div><button type="button" data-authority-revoke="${escapeHtml(lease.leaseId)}">Revoke</button></div></div>`).join("") : '<div class="hint">No temporary authority leases.</div>';
      qa("[data-authority-revoke]").forEach((button) => button.addEventListener("click", async () => {
        try {
          await api(`/api/v1/venue/authority/leases/${encodeURIComponent(button.dataset.authorityRevoke)}/revoke`, {method:"POST", body:JSON.stringify({requestedBy:"control-ui"})});
          await refreshVenueReconciliation(false);
        } catch (error) { q("#venueReconciliationStatus").textContent = error.message; }
      }));
    } catch (error) {
      q("#venueReconciliationStatus").textContent = "Venue reconciliation unavailable";
      q("#venueReconciliationDetails").innerHTML = "";
      q("#venueAuthorityLeases").innerHTML = "";
    }
  }

  async function refreshVenueAdaptations() {
    try {
      venueAdaptationState = await api("/api/v1/venue/adaptations");
      const active = venueAdaptationState.active;
      const txs = Array.isArray(venueAdaptationState.transactions) ? venueAdaptationState.transactions : [];
      if (!selectedVenueAdaptationId && txs.length) selectedVenueAdaptationId = txs[0].transactionId;
      const selected = txs.find((item) => item.transactionId === selectedVenueAdaptationId) || txs[0];
      const activeText = active ? `active ${active.venueName || active.venueId} · patch rev ${active.patchRevision}` : "no active patch";
      const txText = selected ? `${selected.status} · ${selected.venueName || selected.venueId} · ${selected.validation?.valid ? "VALID" : "NOT VALIDATED"}` : "no transaction";
      q("#venueAdaptationStatus").textContent = `${activeText} · ${txText}`;
      const changes = Array.isArray(selected?.changes) ? selected.changes : [];
      if (changes.length) {
        q("#venueAdaptationDetails").innerHTML = changes.map((change) => {
          const next = change.to || {};
          const previous = change.from || {};
          const prevTarget = previous.target || "unmapped";
          const nextTarget = next.target || "logical";
          const provider = next.provider ? `${next.provider.type}:${next.provider.name || next.provider.id}` : "none";
          return `<div class="midiDevice"><div class="midiDeviceHead"><div><strong>${escapeHtml(next.patchKey || change.requirementId)}</strong><div class="hint">${escapeHtml(change.changeType || "change")} · ${escapeHtml(next.resolution || "mapped")} · ${escapeHtml(provider)}</div></div><span>${escapeHtml(prevTarget)} → ${escapeHtml(nextTarget)}</span></div></div>`;
        }).join("");
      } else {
        const mappings = active?.mappings ? Object.entries(active.mappings) : [];
        q("#venueAdaptationDetails").innerHTML = mappings.length ? mappings.map(([key, value]) => `<div class="midiDevice"><div class="midiDeviceHead"><strong>${escapeHtml(key)}</strong><span>${escapeHtml(value.target || "logical")}</span></div></div>`).join("") : '<div class="hint">No proposed Venue Patch Layer mappings.</div>';
      }
    } catch (error) {
      q("#venueAdaptationStatus").textContent = "Venue adaptation state unavailable";
      q("#venueAdaptationDetails").innerHTML = "";
    }
  }

  async function refreshCommunityGovernance() {
    try {
      const monitor = await api("/api/v1/community/monitor");
      const proposals = monitor.proposals || [];
      q("#communityGovernanceStatus").textContent = `${monitor.hypeRule} · ${proposals.length} proposal${proposals.length === 1 ? "" : "s"}`;
      q("#communityGovernanceProposals").innerHTML = proposals.length ? proposals.map((item) => `<div class="midiDevice"><div class="midiDeviceHead"><div><strong>${escapeHtml(item.title)}</strong><div class="hint">${escapeHtml(item.status)} · hype ${Number(item.hype).toFixed(3)} · durable ${Number(item.durableFraction).toFixed(3)}</div></div><span>${item.bindingChangeReady ? "BINDING READY" : "MATURING"}</span></div><div class="hint">raw votes ${item.totalRawVotes} · durable units ${Number(item.totalDurableVoteUnits).toFixed(3)}${item.bindingBlockers?.length ? ` · ${item.bindingBlockers.map(escapeHtml).join(" · ")}` : ""}</div></div>`).join("") : '<div class="hint">No community change proposals are currently registered.</div>';
    } catch (error) {
      q("#communityGovernanceStatus").textContent = "Community governance monitor unavailable";
      q("#communityGovernanceProposals").innerHTML = "";
    }
  }

  async function refreshPlan() {
    try {
      const plan = await api("/api/v1/system/plan");
      const active = plan.decisions.filter((x) => x.status !== "off").length;
      q("#runtimePlan").textContent = `${active}/${plan.decisions.length} adapters active · ${plan.headroom}% estimated CPU headroom`;
    } catch (error) {
      q("#runtimePlan").textContent = "Runtime plan unavailable";
    }
  }

  async function command(path, method, body, resourceKey) {
    try {
      const headers = {"X-StageMesh-Command-Id": commandId()};
      if (snapshot?.revision) headers["If-Match"] = `"rev-${snapshot.revision}"`;
      const resourceRevision = resourceKey && snapshot?.resourceRevisions?.[resourceKey];
      if (resourceRevision) headers["X-StageMesh-Resource-If-Match"] = `"${resourceKey}@${resourceRevision}"`;
      const state = await api(path, {method, headers, body: JSON.stringify(body)});
      render(state);
      refreshPlan();
      refreshNative();
      refreshNodeStatus();
      refreshClockStatus();
      if (resourceKey === "audio") { refreshAudioDevices(); refreshAudioStream(); refreshAudioInput(); }
      if (resourceKey === "lighting-network") refreshLightingNetwork();
      if (resourceKey === "technology") refreshTechnologyOpenness();
      q("#connection").textContent = eventStream ? "LIVE" : "CONNECTED";
      return state;
    } catch (error) {
      if (error.status === 409 && error.data?.current) {
        render(error.data.current);
        q("#connection").textContent = "RESYNCED";
        return error.data.current;
      }
      q("#connection").textContent = "ERROR";
      console.error(error);
      return null;
    }
  }

  function connectEvents() {
    if (!("EventSource" in globalThis)) {
      q("#streamMode").textContent = "POLL FALLBACK";
      setInterval(refresh, 1500);
      return;
    }
    eventStream = new EventSource("/api/v1/events");
    q("#streamMode").textContent = "SSE";
    eventStream.addEventListener("stagemesh", (event) => {
      try {
        const notice = JSON.parse(event.data);
        if (!snapshot || notice.revision > snapshot.revision) refresh();
      } catch (error) {
        console.error(error);
      }
    });
    eventStream.onopen = () => { q("#connection").textContent = "LIVE"; };
    eventStream.onerror = () => { q("#connection").textContent = "RECONNECTING"; };
  }

  q("#play").addEventListener("click", () => command("/api/v1/transport", "POST", {action: snapshot?.transport.running ? "pause" : "play"}, "transport"));
  q("#stop").addEventListener("click", () => command("/api/v1/transport", "POST", {action: "stop"}, "transport"));
  q("#launcherPlay").addEventListener("click",()=>launcherAction("transport.toggle").catch((error)=>q("#launcherStatus").textContent=error.message));
  q("#launcherStop").addEventListener("click",()=>launcherAction("transport.stop").catch((error)=>q("#launcherStatus").textContent=error.message));
  q("#launcherPads").addEventListener("click",(event)=>{const button=event.target.closest("[data-launcher-pad]");if(!button)return;launcherAction("sample.trigger","touch",{resourceId:button.dataset.resource}).then(()=>{button.classList.add("triggered");setTimeout(()=>button.classList.remove("triggered"),140);}).catch((error)=>q("#launcherStatus").textContent=error.message);});
  document.addEventListener("keydown",(event)=>{if(event.repeat||/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName||""))return;const report=(error)=>q("#launcherStatus").textContent=error.message||"Stage control failed.";if(event.code==="Space"){event.preventDefault();launcherAction("transport.toggle","keyboard").catch(report);return;}if(event.code==="Escape"){launcherAction("transport.stop","keyboard").catch(report);return;}const pad=launcherState?.pads?.find((item)=>item.shortcut===event.key);if(pad){event.preventDefault();launcherAction("sample.trigger","keyboard",{resourceId:pad.resourceId}).catch(report);}});
  q("#bpm").addEventListener("change", (e) => command("/api/v1/show", "PATCH", {bpm: Number(e.target.value)}, "show"));
  q("#key").addEventListener("change", (e) => command("/api/v1/show", "PATCH", {key: e.target.value}, "show"));
  q("#capacity").addEventListener("input", (e) => { q("#capacityValue").textContent = e.target.value + "%"; });
  q("#capacity").addEventListener("change", (e) => command("/api/v1/system", "PATCH", {capacity: Number(e.target.value)}, "system"));
  q("#systemMode").addEventListener("change", (e) => command("/api/v1/system", "PATCH", {mode: e.target.value}, "system"));
  q("#venuePreflight").addEventListener("click", () => refreshVenueCompatibility(false));
  q("#venueLiveVerify").addEventListener("click", () => refreshVenueCompatibility(true));
  q("#venueReconcileCheck").addEventListener("click", () => refreshVenueReconciliation(true));
  q("#venueReconcileRepair").addEventListener("click", async () => {
    try {
      const proposed = await api("/api/v1/venue/reconciliation/repair", {method:"POST", body:JSON.stringify({useLocalDiscovery:true})});
      selectedVenueAdaptationId = proposed.transactionId;
      await refreshVenueAdaptations();
      await refreshVenueReconciliation(true);
    } catch (error) { q("#venueReconciliationStatus").textContent = error.message; }
  });
  q("#venueAuthorityGrant").addEventListener("click", async () => {
    const scope = q("#venueAuthorityScope").value.trim();
    const grantee = q("#venueAuthorityGrantee").value.trim();
    if (!scope || !grantee) { q("#venueReconciliationStatus").textContent = "Authority scope and holder are required."; return; }
    try {
      await api("/api/v1/venue/authority/leases", {method:"POST", body:JSON.stringify({scope, grantee, ttlSeconds:300, grantedBy:"control-ui", reason:"temporary live control"})});
      await refreshVenueReconciliation(false);
    } catch (error) { q("#venueReconciliationStatus").textContent = error.message; }
  });
  q("#venueAdaptPropose").addEventListener("click", async () => {
    try {
      const proposed = await api("/api/v1/venue/adaptations/propose", {method:"POST", body:JSON.stringify({useLocalDiscovery:false})});
      selectedVenueAdaptationId = proposed.transactionId;
      await api(`/api/v1/venue/adaptations/${encodeURIComponent(proposed.transactionId)}/validate`, {method:"POST", body:"{}"});
      await refreshVenueAdaptations();
    } catch (error) { q("#venueAdaptationStatus").textContent = error.message; }
  });
  async function commitVenueAdaptation(mode) {
    if (!selectedVenueAdaptationId) return;
    try {
      await api(`/api/v1/venue/adaptations/${encodeURIComponent(selectedVenueAdaptationId)}/commit`, {method:"POST", body:JSON.stringify({mode, requestedBy:"control-ui"})});
      await refreshVenueAdaptations();
      await refreshVenueReconciliation(false);
      await refresh();
    } catch (error) { q("#venueAdaptationStatus").textContent = error.message; }
  }
  q("#venueAdaptCommitBar").addEventListener("click", () => commitVenueAdaptation("next-bar"));
  q("#venueAdaptCommitNow").addEventListener("click", () => commitVenueAdaptation("immediate"));
  q("#venueAdaptRollback").addEventListener("click", async () => {
    const activeId = venueAdaptationState?.active?.transactionId;
    if (!activeId) return;
    try {
      await api(`/api/v1/venue/adaptations/${encodeURIComponent(activeId)}/rollback`, {method:"POST", body:JSON.stringify({requestedBy:"control-ui"})});
      selectedVenueAdaptationId = null;
      await refreshVenueAdaptations();
      await refreshVenueReconciliation(false);
      await refresh();
    } catch (error) { q("#venueAdaptationStatus").textContent = error.message; }
  });

  q("#saveTechnologyScale").addEventListener("click", async () => {
    const ecosystemParticipants = Number(q("#technologyParticipants").value || 1);
    await command("/api/v1/technology", "PATCH", {ecosystemParticipants}, "technology");
  });

  qa("[data-player]").forEach((node) => node.addEventListener("click", () => { selectedPlayer = node.dataset.player; renderMonitor(); renderNotation(); }));

  qa("[data-monitor]").forEach((input) => input.addEventListener("input", () => {
    const player = playerById(selectedPlayer);
    if (!player) return;
    const key = input.dataset.monitor;
    player.monitor[key] = Number(input.value);
    q(`#v-${key}`).textContent = input.value + "%";
    clearTimeout(pendingMonitorTimer);
    const playerId = selectedPlayer;
    const value = Number(input.value);
    pendingMonitorTimer = setTimeout(() => command(`/api/v1/players/${encodeURIComponent(playerId)}/monitor`, "PATCH", {[key]: value}, `monitor:${playerId}`), 80);
  }));

  q("#moreMe").addEventListener("click", () => {
    const player = playerById(selectedPlayer); if (!player) return;
    command(`/api/v1/players/${encodeURIComponent(selectedPlayer)}/monitor`, "PATCH", {self: Math.min(100, player.monitor.self + 8)}, `monitor:${selectedPlayer}`);
  });
  q("#lessClick").addEventListener("click", () => {
    const player = playerById(selectedPlayer); if (!player) return;
    command(`/api/v1/players/${encodeURIComponent(selectedPlayer)}/monitor`, "PATCH", {click: Math.max(0, player.monitor.click - 8)}, `monitor:${selectedPlayer}`);
  });
  q("#muteMine").addEventListener("click", () => {
    const player = playerById(selectedPlayer); if (!player) return;
    command(`/api/v1/players/${encodeURIComponent(selectedPlayer)}/monitor`, "PATCH", {muted: !player.monitor.muted}, `monitor:${selectedPlayer}`);
  });

  q("#notationEnabled").addEventListener("change", (e) => {
    if (!selectedPlayer) return;
    command(`/api/v1/players/${encodeURIComponent(selectedPlayer)}/notation/settings`, "PATCH", {enabled: e.target.checked}, `notation:${selectedPlayer}`);
  });

  q("#notationGrid").addEventListener("change", (e) => {
    if (!selectedPlayer) return;
    command(`/api/v1/players/${encodeURIComponent(selectedPlayer)}/notation/settings`, "PATCH", {quantize: e.target.value}, `notation:${selectedPlayer}`);
  });

  q("#clearNotation").addEventListener("click", () => {
    if (!selectedPlayer) return;
    command(`/api/v1/players/${encodeURIComponent(selectedPlayer)}/notation/clear`, "POST", {}, `notation:${selectedPlayer}`);
  });

  q("#devNote").addEventListener("click", async () => {
    if (!selectedPlayer || !snapshot) return;
    const start = localClockSeconds + (localClockRunning ? (performance.now() - localClockAtFetch) / 1000 : 0);
    const durationSeconds = 60 / Number(snapshot.transport.bpm);
    const first = await command(`/api/v1/players/${encodeURIComponent(selectedPlayer)}/midi/input`, "POST", {status:144, data1:60, data2:100, showTimeSeconds:start}, `midi:${selectedPlayer}`);
    if (!first) return;
    await command(`/api/v1/players/${encodeURIComponent(selectedPlayer)}/midi/input`, "POST", {status:128, data1:60, data2:0, showTimeSeconds:start + durationSeconds}, `midi:${selectedPlayer}`);
  });

  q("#scanAudio").addEventListener("click", () => refreshAudioDevices(true));
  q("#limiterCeiling").addEventListener("input", (e) => { q("#limiterValue").textContent = `${Number(e.target.value).toFixed(1)} dBFS`; });
  q("#limiterCeiling").addEventListener("change", (e) => command("/api/v1/audio", "POST", {limiterCeilingDb:Number(e.target.value)}, "audio"));
  q("#activateAudio").addEventListener("click", async () => {
    try {
      const conversionPolicy=q("#allowOutputRateConversion").checked?{sampleRate:"bounded-sinc"}:{};
      await api("/api/v1/audio/activate", {method:"POST", body:JSON.stringify({acknowledgePhysicalOutput:true, output:0,conversionPolicy})});
      await refreshAudioDevices();
      await refreshAudioStream();
    } catch (error) {
      q("#audioStreamStatus").textContent = error.message;
      console.error(error);
    }
  });
  q("#deactivateAudio").addEventListener("click", async () => {
    try {
      await api("/api/v1/audio/deactivate", {method:"POST", body:"{}"});
      await refreshAudioDevices();
      await refreshAudioStream();
    } catch (error) { console.error(error); }
  });
  q("#recoverAudio").addEventListener("click", async () => {
    try {
      const conversionPolicy=q("#allowOutputRateConversion").checked?{sampleRate:"bounded-sinc"}:{};
      await api("/api/v1/audio/recover", {method:"POST",body:JSON.stringify({acknowledgeRecovery:true,acknowledgePhysicalOutput:true,conversionPolicy})});
      await refreshAudioDevices(true); await refreshAudioStream();
    } catch (error) { q("#audioStreamStatus").textContent=error.message; }
  });
  q("#saveAudioInputRoute").addEventListener("click", async () => {
    const output = Number(q("#audioInputRouteOutput").value || 0);
    const gain = Number(q("#audioInputRouteGain").value || 0);
    const inputPlayerId = q("#audioInputPlayer").value || "";
    await command("/api/v1/audio", "POST", {inputPlayerId, inputRoute:{output, gain}}, "audio");
  });
  q("#activateAudioInput").addEventListener("click", async () => {
    try {
      const gain = Number(snapshot?.audio?.inputRoute?.gain || 0);
      const conversionPolicy=q("#allowInputRateConversion").checked?{sampleRate:"bounded-sinc"}:{};
      await api("/api/v1/audio/input/activate", {method:"POST", body:JSON.stringify({acknowledgePhysicalInput:true, acknowledgeSignalRoute:gain > 0, channels:2,conversionPolicy})});
      await refreshAudioInput();
    } catch (error) { q("#audioInputStatus").textContent = error.message; }
  });
  q("#deactivateAudioInput").addEventListener("click", async () => {
    try {
      await api("/api/v1/audio/input/deactivate", {method:"POST", body:"{}"});
      await refreshAudioInput();
    } catch (error) { q("#audioInputStatus").textContent = error.message; }
  });
  q("#recoverAudioInput").addEventListener("click", async () => {
    try {
      const gain=Number(snapshot?.audio?.inputRoute?.gain||0);
      const conversionPolicy=q("#allowInputRateConversion").checked?{sampleRate:"bounded-sinc"}:{};
      await api("/api/v1/audio/input/recover",{method:"POST",body:JSON.stringify({acknowledgeRecovery:true,acknowledgePhysicalInput:true,acknowledgeSignalRoute:gain>0,channels:2,conversionPolicy})});
      await refreshAudioDevices(true); await refreshAudioInput();
    } catch(error){q("#audioInputStatus").textContent=error.message;}
  });
  q("#saveLightingNetwork").addEventListener("click", async () => {
    const protocol = q("#lightingProtocol").value || "artnet";
    const target = q("#lightingTarget").value.trim();
    const port = Number(q("#lightingPort").value || (protocol === "sacn" ? 5568 : 6454));
    const universeBase = Number(q("#lightingUniverseBase").value || 1);
    await command("/api/v1/lighting/network", "POST", {protocol, target, port, universeBase}, "lighting-network");
    await refreshLightingNetwork();
  });
  q("#lightingProtocol").addEventListener("change", () => {
    if (document.activeElement === q("#lightingPort") || lightingNetworkState?.armed) return;
    q("#lightingPort").value = q("#lightingProtocol").value === "sacn" ? 5568 : 6454;
  });
  q("#armLighting").addEventListener("click", async () => {
    const armed = !Boolean(lightingNetworkState?.armed);
    try {
      const next = await api("/api/v1/lighting/network/arm", {method:"POST", body:JSON.stringify({armed, acknowledgePhysicalOutput:armed})});
      renderLightingNetwork(next);
    } catch (error) {
      q("#lightingNetworkStatus").textContent = error.message;
      console.error(error);
    }
  });
  q("#toggleNodeRole").addEventListener("click", async () => {
    if (nodeState?.role !== "primary") return;
    try {
      nodeState = await api("/api/v1/node/role", {method:"POST", body:JSON.stringify({role:"standby", acknowledgeAuthorityChange:true})});
      await refreshNodeStatus();
      await refreshAudioStream();
      await refreshAudioInput();
      await refreshLightingNetwork();
      await refreshMidiDevices();
    } catch (error) {
      q("#nodeAuthorityDetail").textContent = error.message;
    }
  });
  q("#promoteFailover").addEventListener("click", async () => {
    try {
      await api("/api/v1/failover/promote", {method:"POST", body:JSON.stringify({acknowledgeAuthorityChange:true})});
      await refreshNodeStatus();
      await refreshAudioStream();
      await refreshAudioInput();
      await refreshLightingNetwork();
    } catch (error) { q("#failoverDetail").textContent = error.message; }
  });
  q("#scanMidi").addEventListener("click", () => refreshMidiDevices(true));
  q("#midiLearnStart").addEventListener("click",async()=>{try{const target=(midiMappingTargets?.targets||[]).find((item)=>item.targetId===q("#midiLearnTarget").value);if(["sample.trigger","loop.toggle","loop.clear"].includes(target?.targetId)&&!dawSelectedClipId)throw new Error("Select a DAW clip first so this pad has something concrete to control.");const status=await api("/api/v1/midi/learn",{method:"POST",body:JSON.stringify({targetId:q("#midiLearnTarget").value,resourceId:dawSelectedClipId||"",quantize:q("#midiLearnQuantize").value,keySync:q("#midiLearnKeySync").checked,scale:q("#midiLearnScale").value})});renderMidiMappings(status);q("#midiLearnHint").textContent=`Move one ${target?.suggestedControl||"control"} now…`; }catch(error){q("#midiLearnHint").textContent=error.message;}});
  q("#midiLearnCancel").addEventListener("click",async()=>{try{renderMidiMappings(await api("/api/v1/midi/learn/cancel",{method:"POST",body:"{}"}));}catch(error){q("#midiLearnHint").textContent=error.message;}});
  q("#midiLearnTarget").addEventListener("change",()=>{const target=(midiMappingTargets?.targets||[]).find((item)=>item.targetId===q("#midiLearnTarget").value);q("#midiLearnQuantize").value=target?.quantize||"off";q("#midiLearnKeySync").checked=Boolean(target?.keySync);});
  q("#saveProfile").addEventListener("click",()=>saveProfile().catch((error)=>{q("#profileStatus").textContent=error.message;}));
  q("#dawAddTrack").addEventListener("click",()=>addDawTrack().catch((error)=>q("#dawStatus").textContent=error.message));
  q("#dawAddClip").addEventListener("click",()=>addDawClip().catch((error)=>q("#dawStatus").textContent=error.message));
  q("#dawZoom").addEventListener("input",(event)=>{q("#dawZoomValue").textContent=`${event.target.value} seconds`;if(dawSessionState)renderDaw(dawSessionState);});
  q("#dawSnap").addEventListener("change",()=>{if(dawSessionState)renderDaw(dawSessionState);});
  q("#dawTrimStart").addEventListener("click",()=>dawEdit({op:"trim",trimStartFrames:Math.round(Number(q("#dawEditSeconds").value)*192000),trimEndFrames:0}).catch((error)=>q("#dawStatus").textContent=error.message));
  q("#dawSplit").addEventListener("click",()=>dawEdit({op:"split",splitFrame:Math.round(localClockSeconds*192000),newClipId:`clip-${Date.now()}`}).catch((error)=>q("#dawStatus").textContent=error.message));
  q("#dawFade").addEventListener("click",()=>{const frames=Math.round(Number(q("#dawEditSeconds").value)*192000);return dawEdit({op:"fade",fadeInFrames:frames,fadeOutFrames:frames,curve:"equal-power"}).catch((error)=>q("#dawStatus").textContent=error.message);});
  q("#dawUndo").addEventListener("click",async()=>{try{renderDaw(await api("/api/v1/daw/undo",{method:"POST",body:"{}"}));}catch(error){q("#dawStatus").textContent=error.message;}});
  q("#dawRedo").addEventListener("click",async()=>{try{renderDaw(await api("/api/v1/daw/redo",{method:"POST",body:"{}"}));}catch(error){q("#dawStatus").textContent=error.message;}});
  q("#dawRender").addEventListener("click",async()=>{try{const receipt=await api("/api/v1/daw/render",{method:"POST",body:JSON.stringify({fileName:q("#dawExportName").value,bits:Number(q("#dawExportBits").value),startFrame:0,endFrame:192000*10,ditherSeed:0})});q("#dawProductionStatus").textContent=`Rendered ${receipt.frames} frames · SHA-256 ${receipt.outputSha256.slice(0,16)}… · limiter ${Number(receipt.limiterGain).toFixed(3)}`;}catch(error){q("#dawProductionStatus").textContent=error.message;}});
  q("#dawAutosave").addEventListener("click",async()=>{try{const receipt=await api("/api/v1/daw/autosave",{method:"POST",body:"{}"});q("#dawProductionStatus").textContent=`Autosaved revision ${receipt.revision} · ${receipt.sha256.slice(0,16)}…`;}catch(error){q("#dawProductionStatus").textContent=error.message;}});
  q("#dawLocateBeat").addEventListener("click",async()=>{try{const located=await api("/api/v1/daw/beat-frame",{method:"POST",body:JSON.stringify({beat:Number(q("#dawBeat").value)})});q("#dawProductionStatus").textContent=`Beat ${located.beat} = frame ${located.frame} at 192 kHz`;}catch(error){q("#dawProductionStatus").textContent=error.message;}});
  q("#dawPrepareTake").addEventListener("click",async()=>{try{const take=await api("/api/v1/daw/takes/prepare",{method:"POST",body:JSON.stringify({trackId:q("#dawClipTrack").value,startFrame:Math.round(localClockSeconds*192000),preRollFrames:384000})});q("#dawProductionStatus").textContent=`Take ${take.takeId} prepared with two-second pre-roll; physical input remains disarmed.`;}catch(error){q("#dawProductionStatus").textContent=error.message;}});
  q("#dawScanPlugins").addEventListener("click",async()=>{try{const catalog=await api("/api/v1/daw/plugins");q("#dawProductionStatus").textContent=`${catalog.plugins.length} adapter manifests · ${catalog.plugins.filter((p)=>p.quarantined).length} quarantined · isolated scan`;}catch(error){q("#dawProductionStatus").textContent=error.message;}});
  q("#dawPreviewPlan").addEventListener("click",async()=>{try{const plan=await api("/api/v1/daw/render-plan",{method:"POST",body:JSON.stringify({startFrame:0,endFrame:192000*60})});q("#dawPlan").textContent=`Validated ${plan.regions.length} bounded regions for offline render; outputs remain disarmed.`;}catch(error){q("#dawPlan").textContent=error.message;}});

  function clockFrame(now) {
    let seconds = localClockSeconds;
    if (localClockRunning) seconds += (now - localClockAtFetch) / 1000;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor(seconds / 60) % 60;
    const s = Math.floor(seconds) % 60;
    const ms = Math.floor((seconds % 1) * 1000);
    q("#clock").textContent = [h,m,s].map((v) => String(v).padStart(2,"0")).join(":") + "." + String(ms).padStart(3,"0");
    requestAnimationFrame(clockFrame);
  }

  desktopReady.then(() => {
    refresh().then(() => { refreshPlan(); refreshNative(); refreshNodeStatus(); refreshClockStatus(); refreshTechnologyOpenness(); refreshCommunityGovernance(); refreshCompatibility(); refreshVenueAdaptations(); refreshVenueReconciliation(false); refreshAudioDevices(); refreshAudioStream(); refreshAudioInput(); refreshLightingNetwork(); refreshMidiDevices(); refreshMidiMappings(); refreshProfile(); refreshDaw(); refreshLauncher(); });
    connectEvents();
    setInterval(refreshClockStatus, 1000);
    setInterval(refreshNodeStatus, 2000);
    setInterval(refreshTechnologyOpenness, 5000);
    setInterval(refreshCommunityGovernance, 5000);
    setInterval(()=>{if(midiMappingState?.learning)refreshMidiMappings();},250);
    setInterval(refreshLauncher,750);
    setInterval(refreshCompatibility, 5000);
    setInterval(refreshVenueAdaptations, 3000);
    setInterval(() => refreshVenueReconciliation(false), 3000);
  }).catch((error) => {
    q("#connection").textContent = "OFFLINE";
    q("#launcherStatus").textContent = error.message;
  });
  requestAnimationFrame(clockFrame);
})();
