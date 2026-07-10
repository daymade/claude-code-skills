// Export the full conversation JSON from inside a claude.ai conversation page.
// Channel-agnostic: paste into claude-in-chrome's javascript_tool, or run via
// scripts/runjs.applescript on the AppleScript fallback channel.
//
// Fire-and-poll (execute-JS channels don't await promises):
//   1. Run this file. It returns 'started' immediately.
//   2. Poll (after ~3s) with:   window.__claudeExport ? JSON.stringify({ok: window.__claudeExport.ok, title: window.__claudeExport.title, messages: window.__claudeExport.messages, chars: window.__claudeExport.chars, error: window.__claudeExport.error || ''}) : 'pending'
//   3. Read the payload:
//      - AppleScript channel:  echo 'window.__claudeExport.rawJson' > read.js
//                              osascript scripts/runjs.applescript read.js <conv-id> > conversation.json
//      - javascript_tool:      window.__claudeExport.rawJson.slice(0, 16000)  → page in ~16k windows
//   4. Render with scripts/render_transcript.py.
//
// Uses rendering_mode=messages&render_all_tools=true — the only variant that
// returns real tool_use/tool_result blocks instead of "This block is not
// supported..." placeholders (verified superset of rendering_mode=raw).

(async () => {
  try {
    const convId = location.pathname.split('/').pop(); // from the open URL; never hard-code
    const orgs = await fetch('/api/organizations', { headers: { accept: 'application/json' } })
      .then(r => r.json());

    let conv = null, usedOrg = null, lastErr = null;
    for (const o of orgs) { // multi-org accounts: try each until one 200s
      try {
        const r = await fetch(
          `/api/organizations/${o.uuid}/chat_conversations/${convId}?tree=True&rendering_mode=messages&render_all_tools=true`,
          { headers: { accept: 'application/json' } }
        );
        if (r.ok) { conv = await r.json(); usedOrg = o.uuid; break; }
        lastErr = 'HTTP ' + r.status + ' org=' + o.uuid;
      } catch (e) { lastErr = String(e); }
    }
    if (!conv) {
      window.__claudeExport = { ok: false, error: 'no org worked: ' + lastErr };
      return;
    }

    const rawJson = JSON.stringify(conv);
    window.__claudeExport = {
      ok: true,
      org: usedOrg,
      title: conv.name,
      created: conv.created_at || '',
      updated: conv.updated_at || '',
      messages: (conv.chat_messages || []).length, // whole tree; active path resolved at render time
      chars: rawJson.length,
      rawJson: rawJson
    };
  } catch (e) {
    window.__claudeExport = { ok: false, error: String(e && e.stack || e) };
  }
})();
'started'
