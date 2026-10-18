(function () {
  "use strict";
  const q = selector => document.querySelector(selector);
  const main = q("#main-content");
  if (!main || !q("#setup")) return;
  const pages = new Map();
  const register = (key, node) => { node.dataset.workspacePage = key; pages.set(key, node); return node; };
  const page = (key, title) => {
    const node = document.createElement("section"); node.className = "panel workspacePage"; node.id = key;
    const heading = document.createElement("h1"); heading.textContent = title; heading.tabIndex = -1;
    node.appendChild(heading); main.appendChild(node); return register(key, node);
  };
  register("setup", q("#setup")); register("stage-editor", q("#stage-editor")); register("show-control", q("#show-control"));
  const studio = page("studio", "Studio");
  const studioLabel = document.createElement("label"); studioLabel.className = "deviceMenuLabel"; studioLabel.textContent = "Studio tools";
  const studioMenu = document.createElement("select"); studioMenu.setAttribute("aria-label", "Studio tools"); studioLabel.appendChild(studioMenu); studio.appendChild(studioLabel);
  const studioPanels = new Map();
  for (const [key, title] of [["arrangement", "Arrangement and clips"], ["automation", "Volume automation"], ["production", "Rendering and recording"], ["recovery", "Recording recovery"]]) {
    studioMenu.add(new Option(title, key));
    const node = document.createElement("section"); node.dataset.studioPanel = key; studio.appendChild(node); studioPanels.set(key, node);
  }
  studioPanels.get("automation").append(q("#dawAutomationStatus").closest(".subPanel"), q("#dawAutomationNew"));
  studioPanels.get("production").appendChild(q("#dawProductionStatus").closest(".subPanel"));
  studioPanels.get("recovery").appendChild(q("#recoveryStatus").closest(".subPanel"));
  const daw = q("#dawStatus").closest("details"); daw.open = true; studioPanels.get("arrangement").appendChild(daw);
  const selectStudio = () => { for (const [key, node] of studioPanels) node.hidden = key !== studioMenu.value; };
  studioMenu.addEventListener("change", selectStudio); studioMenu.value = "arrangement"; selectStudio();
  const devices = page("operations", "Devices");
  const label = document.createElement("label"); label.className = "deviceMenuLabel"; label.textContent = "Device controls";
  const menu = document.createElement("select"); menu.id = "deviceMenu"; menu.setAttribute("aria-label", "Device controls"); label.appendChild(menu); devices.appendChild(label);
  const groups = new Map();
  const group = (key, title) => {
    const option = new Option(title, key); menu.add(option);
    const node = document.createElement("section"); node.className = "workspaceDevicePanel"; node.dataset.devicePanel = key;
    const h = document.createElement("h2"); h.textContent = title; node.appendChild(h); devices.appendChild(node); groups.set(key, node); return node;
  };
  const input = group("input", "Audio input"), output = group("output", "Audio output");
  const audio = q("#audioBackend").closest("details");
  const inventory = document.createElement("div"); inventory.className = "audioInventory";
  inventory.append(q("#audioBackend").parentElement, q("#audioDevices"));
  const recovery = q("#audioReconnectStatus").closest(".subPanel");
  input.append(inventory, recovery, q("#audioInputStatus").closest(".subPanel"));
  output.appendChild(audio); audio.open = true;
  const moveDetails = (selector, key, title) => {
    const target = group(key, title), node = q(selector).closest("details");
    node.open = true; target.appendChild(node); return target;
  };
  moveDetails("#midiBackend", "midi", "MIDI controllers");
  // Keep optional learning controls out of the basic mapping screen.
  const learn = q(".midiLearnPanel"), learnDetails = document.createElement("details");
  const learnSummary = document.createElement("summary"); learnSummary.textContent = "Learn controller mappings";
  learn.before(learnDetails); learnDetails.append(learnSummary, learn);
  moveDetails("#lightingNetworkStatus", "lighting", "Lighting");
  moveDetails("#profileStatus", "preferences", "Preferences");
  moveDetails("#hardwareDiagnosisStatus", "compatibility", "Hardware and venue compatibility");
  const advanced = group("advanced", "Advanced system controls");
  for (const selector of ["#technologyOpenStatus", "#communityGovernanceStatus", "#nodeAuthorityDetail"]) advanced.appendChild(q(selector).closest("details"));
  const system = group("system", "System capacity");
  const systemPanel = q(".systemPanel");
  while (systemPanel.firstChild) system.appendChild(systemPanel.firstChild);
  const reports = page("activity-panel", "Reports and activity");
  reports.append(q(".readinessPanel"), q("#ai-advisor"));
  const events = q("#events").parentElement;
  // Keep the existing activity target unique; move its contents into the report page.
  while (events.firstChild) reports.appendChild(events.firstChild);
  events.remove();
  systemPanel.remove();
  // Remove the old all-in-one wrapper after all controls have moved intact.
  const legacy = Array.from(main.children).find(node => node.id === "operations" && node !== devices);
  legacy?.remove();
  let active = null;
  const selectDevices = key => {
    const value = groups.has(key) ? key : "input"; menu.value = value; devices.dataset.audioDirection = value;
    for (const [name, node] of groups) node.hidden = name !== value;
    if (value === "input" || value === "output") groups.get(value).insertBefore(inventory, groups.get(value).children[1] || null);
  };
  selectDevices("input"); menu.addEventListener("change", () => selectDevices(menu.value));
  const show = (key, {focus = true, device = null} = {}) => {
    if (!pages.has(key)) key = "setup";
    if (active !== key && active !== null) {
      const event = new CustomEvent("stagemesh:before-workspace-change", {cancelable:true, detail:{from:active, to:key}});
      if (!document.dispatchEvent(event)) return false;
    }
    active = key;
    for (const [name, node] of pages) { node.hidden = name !== key; node.inert = name !== key; }
    for (const link of document.querySelectorAll(".productNav a")) {
      const selected = link.hash === `#${key}`; link.classList.toggle("active", selected);
      if (selected) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    }
    if (device) selectDevices(device);
    if (focus) {
      const heading = pages.get(key).querySelector("h1, h2");
      if (heading) { heading.tabIndex = -1; heading.focus({preventScroll:true}); }
      window.scrollTo({top:0, behavior:"instant"});
    }
    document.dispatchEvent(new CustomEvent("stagemesh:workspace-change", {detail:{page:key}}));
    return true;
  };
  const navigate = (key, options = {}) => {
    if (!show(key, options)) return false;
    history.replaceState(null, "", `#${active}`); return true;
  };
  for (const link of document.querySelectorAll(".productNav a")) link.addEventListener("click", event => {
    event.preventDefault(); navigate(link.hash.slice(1));
  });
  window.addEventListener("hashchange", () => {
    const key = location.hash.slice(1); if (pages.has(key)) navigate(key);
  });
  let reviewed = false;
  try { reviewed = JSON.parse(localStorage.getItem("stagemesh.setup.review.v1"))?.reviewed === true; } catch { /* optional preference */ }
  const initial = location.hash.slice(1);
  show(pages.has(initial) ? initial : reviewed ? "stage-editor" : "setup", {focus:false});
  globalThis.StageMeshWorkspace = Object.freeze({navigate, isShowControl: () => active === "show-control"});
  const updateStatus = () => {
    const engine = q("#nativeReadinessTitle").textContent;
    const inputText = q("#audioReconnectStatus").textContent;
    const outputText = q("#audioStreamStatus").textContent.split(" · ")[0];
    const lighting = q("#lightingNetworkStatus").textContent;
    const text = `${engine} · ${inputText} · ${outputText} · ${/armed/i.test(lighting) && !/disarmed/i.test(lighting) ? "Lighting: review active output" : "Lighting: see Devices"}`;
    if (q("#workspaceStatus").textContent !== text) q("#workspaceStatus").textContent = text;
  };
  const observer = new MutationObserver(updateStatus);
  for (const selector of ["#nativeReadinessTitle", "#audioReconnectStatus", "#audioStreamStatus", "#lightingNetworkStatus"]) observer.observe(q(selector), {childList:true, subtree:true, characterData:true});
  updateStatus();
}());
