(() => {
  const token = new URLSearchParams(location.search).get('token') || '';
  const $ = id => document.getElementById(id);
  const status = $('status');
  const setStatus = (message, kind='') => { status.textContent = message; status.className = kind || 'muted'; };
  if (!token) { setStatus('This voting link is missing its credential.', 'error'); return; }

  async function load() {
    const response = await fetch('/api/v1/community/vote/context?token=' + encodeURIComponent(token), {cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to load vote');
    $('title').textContent = data.proposal.title;
    $('description').textContent = data.proposal.description || '';
    $('expires').textContent = data.invitation.expiresAt ? new Date(data.invitation.expiresAt).toLocaleString() : 'not issued';
    $('hype').textContent = Number(data.hype).toFixed(3);
    $('durable').textContent = Number(data.durableFraction).toFixed(3);
    setStatus(data.requiresAuthenticatedAccount ? 'This invitation must be used while signed into the matching StageMesh account.' : 'Development token-only voting is enabled.');
  }

  document.querySelectorAll('[data-choice]').forEach(button => button.addEventListener('click', async () => {
    document.querySelectorAll('[data-choice]').forEach(b => b.disabled = true);
    try {
      const response = await fetch('/api/v1/community/vote', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({token, choice: button.dataset.choice})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Vote failed');
      setStatus(`Vote recorded: ${data.choice}. Raw vote units: 1. Hype vote units: 0.`, 'ok');
    } catch (error) {
      setStatus(error.message, 'error');
      document.querySelectorAll('[data-choice]').forEach(b => b.disabled = false);
    }
  }));
  load().catch(error => setStatus(error.message, 'error'));
})();
