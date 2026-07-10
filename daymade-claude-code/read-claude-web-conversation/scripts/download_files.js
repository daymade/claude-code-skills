// Download every file in the current claude.ai conversation, in-page.
// Auto-inventories from the conversation JSON: user uploads (blob), assistant
// images, and sandbox deliverables behind Download cards (present_files) —
// each via the endpoint family that actually serves it (uploads/outputs are
// path-keyed via wiggle/download-file; uuid-keyed guesses 404 for those).
//
// Fire-and-poll, same as export_conversation.js:
//   1. Run this file → 'downloading'.
//   2. Poll:   window.__dlStatus || 'pending'      (one line per file: name => bytes / FAIL)
//   3. Read files out one at a time as base64, e.g. AppleScript channel:
//        echo "window.__dl['report.xlsx']" > read_one.js
//        osascript scripts/runjs.applescript read_one.js <conv-id> 2>/dev/null | tr -d '\n' | base64 -d > report.xlsx
//   4. VERIFY each file: `file <name>` magic bytes + byte size == the size in __dlStatus
//      (uploads also carry size_bytes in the conversation JSON).

(async () => {
  const toB64 = (buf) => {
    const bytes = new Uint8Array(buf);
    let bin = '';
    for (let i = 0; i < bytes.length; i += 32768)  // chunked: one big apply() overflows the stack
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
    return btoa(bin);
  };

  try {
    const convId = location.pathname.split('/').pop();
    const orgResponse = await fetch('/api/organizations', {
      headers: { accept: 'application/json' }
    });
    if (!orgResponse.ok) throw new Error(`organization fetch failed: HTTP ${orgResponse.status}`);
    const orgs = await orgResponse.json();
    let conv = null, org = null;
    for (const o of orgs) {
      try {
        const r = await fetch(
          `/api/organizations/${o.uuid}/chat_conversations/${convId}?tree=True&rendering_mode=messages&render_all_tools=true`,
          { headers: { accept: 'application/json' } });
        if (r.ok) { conv = await r.json(); org = o.uuid; break; }
      } catch (_) {
        // Try the next organization; multi-org accounts do not guarantee that
        // every organization can read this conversation.
      }
    }
    if (!conv) { window.__dlStatus = 'FAIL: conversation fetch'; return; }

    // Follow only the active edit/regeneration branch; dead branches may carry
    // stale files that are no longer part of the visible conversation.
    const allMessages = conv.chat_messages || [];
    const byId = new Map(allMessages.map(m => [m.uuid, m]));
    const activeMessages = [];
    const seen = new Set();
    let messageId = conv.current_leaf_message_uuid;
    while (messageId && byId.has(messageId) && !seen.has(messageId)) {
      seen.add(messageId);
      const message = byId.get(messageId);
      activeMessages.unshift(message);
      messageId = message.parent_message_uuid;
    }
    const messages = activeMessages.length ? activeMessages : allMessages;

    // Inventory: {name, url, expect} — dedupe by sandbox path / uuid.
    const jobs = new Map();
    for (const m of messages) {
      for (const f of [...(m.files || []), ...(m.attachments || [])]) {
        if (f.file_kind === 'blob' && f.path) {          // user upload → path-keyed
          jobs.set(f.path, {
            name: f.file_name,
            url: `/api/organizations/${org}/conversations/${convId}/wiggle/download-file?path=${encodeURIComponent(f.path)}`,
            expect: f.size_bytes
          });
        } else if (f.file_kind === 'image' && (f.file_uuid || f.uuid)) {  // assistant image → uuid-keyed
          const fileUuid = f.file_uuid || f.uuid;
          jobs.set(fileUuid, {
            name: f.file_name,
            url: `/api/organizations/${org}/files/${fileUuid}/contents`
          });
        }
      }
      for (const b of m.content || []) {                 // deliverables behind Download cards
        if (b.type === 'tool_use' && b.name === 'present_files') {
          for (const p of (b.input || {}).filepaths || []) {
            jobs.set(p, {
              name: p.split('/').pop(),
              url: `/api/organizations/${org}/conversations/${convId}/wiggle/download-file?path=${encodeURIComponent(p)}`
            });
          }
        }
      }
    }

    window.__dl = Object.create(null);
    const status = [];
    const usedNames = new Map();
    for (const { name, url, expect } of jobs.values()) {
      try {
        const r = await fetch(url, { headers: { accept: '*/*' } });
        if (!r.ok) { status.push(`${name} => FAIL ${r.status}`); continue; }
        const buf = await r.arrayBuffer();
        const baseName = String(name || 'download').replace(/[\r\n]/g, '_');
        const count = (usedNames.get(baseName) || 0) + 1;
        usedNames.set(baseName, count);
        const dot = baseName.lastIndexOf('.');
        const exportName = count === 1 ? baseName
          : dot > 0
            ? `${baseName.slice(0, dot)} (${count})${baseName.slice(dot)}`
            : `${baseName} (${count})`;
        window.__dl[exportName] = toB64(buf);
        const sizeNote = expect != null && Number(expect) !== buf.byteLength
          ? ` SIZE-MISMATCH expected ${expect}` : '';
        status.push(`${exportName} => ${buf.byteLength}B${sizeNote}`);
      } catch (e) { status.push(`${name} => ERR ${String(e).slice(0, 60)}`); }
    }
    window.__dlStatus = status.join('\n') || 'no files found';
  } catch (e) {
    window.__dlStatus = 'FAIL: ' + String(e && e.stack || e);
  }
})();
'downloading'
