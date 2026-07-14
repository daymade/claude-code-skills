// CDP-ready conversation fetch. Returns the raw conversation JSON directly as a
// Promise, so `cdp_channel.py eval --js fetch_cdp.js --out conversation.json`
// resolves it in one call (no fire-and-poll, no window.__claudeExport).
//
// Works for both /chat/<conversation-id> and /share/<snapshot-id> URLs.

(async () => {
  try {
    const pathParts = location.pathname.split('/').filter(Boolean);
    const last = pathParts[pathParts.length - 1];
    const isShare = pathParts[0] === 'share' || location.pathname.startsWith('/share/');

    let conv = null;
    let lastErr = null;

    if (isShare) {
      const r = await fetch(
        `/api/chat_snapshots/${last}?rendering_mode=messages&render_all_tools=true`,
        { headers: { accept: 'application/json' } }
      );
      if (!r.ok) {
        lastErr = 'share fetch HTTP ' + r.status + ' for snapshot ' + last;
      } else {
        conv = await r.json();
      }
    } else {
      const orgs = await fetch('/api/organizations', {
        headers: { accept: 'application/json' }
      }).then(r => r.json());

      if (!Array.isArray(orgs) || orgs.length === 0) {
        throw new Error('/api/organizations returned no organizations (not signed in?)');
      }

      for (const o of orgs) {
        try {
          const r = await fetch(
            `/api/organizations/${o.uuid}/chat_conversations/${last}?tree=True&rendering_mode=messages&render_all_tools=true`,
            { headers: { accept: 'application/json' } }
          );
          if (r.ok) { conv = await r.json(); break; }
          lastErr = 'chat fetch HTTP ' + r.status + ' org=' + o.uuid;
        } catch (e) {
          lastErr = String(e);
        }
      }
    }

    if (!conv) {
      throw new Error('Failed to fetch conversation: ' + (lastErr || 'unknown'));
    }

    return JSON.stringify(conv);
  } catch (e) {
    throw new Error(String(e && e.stack || e));
  }
})();
