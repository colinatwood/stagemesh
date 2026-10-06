function mountRecordingRecovery(doc, request) {
  const scan = doc.querySelector('#recoveryScan');
  const select = doc.querySelector('#recoveryFile');
  const recover = doc.querySelector('#recoveryCreate');
  const status = doc.querySelector('#recoveryStatus');
  let busy = false;
  function controls() {
    scan.disabled = busy;
    select.disabled = busy || !select.options.length;
    recover.disabled = busy || !select.value;
  }
  select.addEventListener('change', controls);
  scan.addEventListener('click', async () => {
    if (busy) return;
    busy = true; select.replaceChildren(); controls();
    status.textContent = 'Looking for interrupted recordings…';
    try {
      const result = await request('/api/v1/daw/capture/recovery');
      if (!result.available) status.textContent = result.reason;
      else {
        for (const file of result.files) {
          const option = doc.createElement('option');
          option.value = file.fileName;
          option.textContent = `${file.fileName} (${file.bytes} bytes)`;
          select.appendChild(option);
        }
        status.textContent = result.files.length ? 'Choose a recording to recover. Its format will be checked before copying.' : 'No interrupted recordings found.';
        if (result.truncated) status.textContent += ' Scan limited to 1,000 directory entries; additional files may exist.';
      }
    } catch (error) { status.textContent = error.message; }
    finally { busy = false; controls(); }
  });
  recover.addEventListener('click', async () => {
    if (busy || !select.value) return;
    busy = true; controls(); status.textContent = 'Recovering a copy…';
    try {
      const result = await request('/api/v1/daw/capture', {method: 'POST', body: JSON.stringify({action: 'recover', fileName: select.value})});
      status.textContent = `Recovered ${result.frames} frames to ${result.path}. Original kept. ${result.discardedTrailingBytes} incomplete trailing bytes excluded. Audio continuity is unverified.`;
    } catch (error) { status.textContent = error.message; }
    finally { busy = false; controls(); }
  });
}
if (typeof module !== 'undefined') module.exports = {mountRecordingRecovery};
if (typeof document !== 'undefined') mountRecordingRecovery(document, globalThis.StageMeshUI.api);
