function mountDawProduction(doc, request, confirmAction = (message) => globalThis.confirm(message)) {
  const get = (id) => doc.querySelector(`#${id}`);
  const controls = ['dawPlaybackStart','dawPlaybackLoop','dawPlaybackStop','dawCaptureStart','dawCaptureFinish','dawCaptureAbort','dawProductionRefresh','dawTempCleanup'].map(get);
  const status = get('dawProductionStatus');
  let busy = false;

  function setBusy(value) {
    busy = value;
    for (const control of controls) control.disabled = value;
    status.setAttribute?.('aria-busy', String(value));
  }
  function range() {
    const beginFrame = Math.round(Number(get('dawPlaybackBegin').value) * 192000);
    const endFrame = Math.round(Number(get('dawPlaybackEnd').value) * 192000);
    if (!Number.isSafeInteger(beginFrame) || !Number.isSafeInteger(endFrame) || beginFrame < 0 || endFrame <= beginFrame) throw new Error('Playback end must be after start.');
    return {beginFrame, endFrame};
  }
  async function run(work) {
    if (busy) return;
    setBusy(true);
    try { await work(); } catch (error) { status.textContent = error.message; }
    finally { setBusy(false); }
  }
  async function refresh() {
    const state = await request('/api/v1/daw/production');
    const playing = state.playback.producer?.running ? 'playing' : 'stopped';
    const temporary=state.temporaryResources||{};
    status.textContent = `${state.canonicalSampleRate / 1000} kHz · ${playing} · capture ${state.capture.state || 'idle'} · ${state.recovery.files?.length || 0} interrupted take(s) · ${temporary.resourceCount||0} temporary resource(s), ${temporary.reclaimableCount||0} reclaimable · outputs disarmed`;
  }

  get('dawPlaybackStart').addEventListener('click', () => run(async () => {
    const {beginFrame: startFrame, endFrame} = range();
    await request('/api/v1/daw/playback', {method:'POST', body:JSON.stringify({action:'start', startFrame, endFrame})});
    await refresh();
  }));
  get('dawPlaybackLoop').addEventListener('click', () => run(async () => {
    const {beginFrame, endFrame} = range();
    if ((endFrame - beginFrame) % 256) throw new Error('Loop length must align to 256 canonical frames.');
    await request('/api/v1/daw/playback', {method:'POST', body:JSON.stringify({action:'loop', beginFrame, endFrame})});
    await refresh();
  }));
  get('dawPlaybackStop').addEventListener('click', () => run(async () => {
    await request('/api/v1/daw/playback', {method:'POST', body:JSON.stringify({action:'stop'})});
    await refresh();
  }));
  get('dawCaptureStart').addEventListener('click', () => run(async () => {
    const takeId = `take-${Date.now()}`;
    await request('/api/v1/daw/capture', {method:'POST', body:JSON.stringify({action:'start', track:0, takeId, fileName:`${takeId}.wav`, acknowledgePhysicalInput:true})});
    await refresh();
  }));
  get('dawCaptureFinish').addEventListener('click', () => run(async () => {
    const fileName = get('captureFinishName').value.trim();
    const result = await request('/api/v1/daw/capture', {method:'POST', body:JSON.stringify({action:'finish', ...(fileName ? {fileName} : {})})});
    status.textContent = `Capture finalized at ${result.path} · ${result.frames} frames · ${result.dropoutBlocks} queue gaps.${result.partialCleanupPending ? ' Partial-file cleanup remains pending.' : ''}`;
  }));
  get('dawCaptureAbort').addEventListener('click', () => {
    if (!confirmAction('Abort this capture and discard its partial take?')) return;
    return run(async () => { await request('/api/v1/daw/capture', {method:'POST', body:JSON.stringify({action:'abort'})}); await refresh(); });
  });
  get('dawProductionRefresh').addEventListener('click', () => run(refresh));
  get('dawTempCleanup').addEventListener('click', () => {
    if (!confirmAction('Clean only DAW snapshots and staging files whose exact owning process is proven dead?')) return;
    return run(async () => { const result=await request('/api/v1/daw/temp-resources/cleanup',{method:'POST',body:JSON.stringify({acknowledgeCleanup:true})});status.textContent=`Reclaimed ${result.reclaimedCount} abandoned snapshot(s). ${result.unknownOwnerCount} unknown owner(s) retained. Outputs disarmed.`; });
  });
  const ready = run(refresh);
  return {ready, refresh};
}

if (typeof module !== 'undefined') module.exports = {mountDawProduction};
if (typeof document !== 'undefined') mountDawProduction(document, globalThis.StageMeshUI.api);
