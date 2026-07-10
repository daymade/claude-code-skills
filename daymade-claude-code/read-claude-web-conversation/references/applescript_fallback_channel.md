# AppleScript Fallback Channel (macOS) — when the Chrome extension can't connect

The claude-in-chrome extension only pairs when the claude.ai account signed in
**inside the extension** matches the account running Claude Code. When they
differ (e.g. the conversation lives in a teammate's or a second account that the
user's Chrome is signed into), the extension route is structurally unavailable —
no amount of retrying fixes an account mismatch.

This channel replaces the extension with macOS AppleScript: Chrome can execute
JavaScript in an open tab via Apple Events, and that JS runs in the page's
context, so `fetch` carries the page's login cookie exactly like the
`javascript_tool` path. Same API method, different injection channel.

**Recognize the situation** (any of these, with the extension installed and enabled):

- `list_connected_browsers` returns `[]`
- `switch_browser` answers "No other browsers available to switch to"
- The user says the extension is signed into a different account than Claude Code

Requirements: macOS + Google Chrome + one manual menu toggle by the user. Not
available on Windows/Linux (no Apple Events) — there, the options are signing
the extension into the matching account, or exporting from a browser profile
that is signed in correctly.

## Table of contents

- [One-time setup (the user does this, not you)](#one-time-setup-the-user-does-this-not-you)
- [The execution pattern](#the-execution-pattern)
- [Why the JS must live in a file](#why-the-js-must-live-in-a-file)
- [Async results: the two-step window-variable pattern](#async-results-the-two-step-window-variable-pattern)
- [Large outputs: redirect stdout to a file](#large-outputs-redirect-stdout-to-a-file)
- [Binary file transfer (base64 bridge)](#binary-file-transfer-base64-bridge)
- [Cleanup etiquette](#cleanup-etiquette)
- [Troubleshooting](#troubleshooting)

## One-time setup (the user does this, not you)

Chrome ships with AppleScript-JS execution **disabled**. The user must enable:

> **View → Developer → Allow JavaScript from Apple Events**

Ask the user to click it themselves — it is a browser security toggle, and
flipping security settings on the user's behalf (via UI automation or plist
edits) is the wrong side of the line. The first `osascript` attempt tells you
whether it's on: if off, the error message itself contains the exact menu path,
so you can just relay it.

Two more one-time prompts may appear, both fine to let the user approve:

- macOS Automation permission (your terminal controlling Chrome) — appears on
  the first `osascript ... tell application "Google Chrome"` call.
- Nothing else. No extension, no restart, no profile changes.

When the export is done, remind the user they can toggle the menu item back off.

## The execution pattern

Never target tabs by index — indexes shift as the user opens/closes tabs
mid-session. Find the tab by URL substring every time. The executor is bundled
— don't rewrite it: [scripts/runjs.applescript](../scripts/runjs.applescript)
takes the JS file and the URL substring as arguments.

Every call is:

```bash
osascript scripts/runjs.applescript step1.js <conversation-id>             # small result: stdout
osascript scripts/runjs.applescript step2.js <conversation-id> > out.txt   # large result: redirect
```

where `<conversation-id>` is the id from the conversation URL the user gave
you (any unique URL substring works). Call the bundled runner with that exact
ID; it returns `TAB_NOT_FOUND` without exposing the URLs or titles of unrelated
tabs. If it does, ask the user to open the target conversation. The page must
be loaded and signed in for its cookies to be live.

## Why the JS must live in a file

Passing JS inline inside an AppleScript string is an escaping trap: AppleScript
interprets `\n` inside double-quoted strings as a real newline, which tears
multi-line-unsafe JS apart mid-string-literal, and every `"` needs doubling.
The `read POSIX file` pattern sidesteps all of it — the JS file is passed
byte-for-byte. Inside the JS itself, prefer `String.fromCharCode(10)` over
`'\n'` literals if you ever do inline a snippet.

## Async results: the two-step window-variable pattern

`execute ... javascript` evaluates synchronously — it does **not** await
promises. An `async` fetch returns `missing value` immediately. Split every
async operation into fire-and-poll:

**Step 1 — fire.** The script stores its result on `window` and returns a
plain string immediately:

```js
(async () => {
  try {
    const r = await fetch('/api/...', { headers: { accept: 'application/json' } });
    window.__export = { ok: r.ok, data: await r.json() };
  } catch (e) {
    window.__export = { ok: false, error: String(e) };
  }
})();
'started'
```

**Step 2 — poll.** A second call (after `sleep 3`, longer for many requests)
reads it back:

```js
window.__export ? JSON.stringify({ok: window.__export.ok, error: window.__export.error || ''}) : 'pending'
```

Two reliability notes learned the hard way:

- End every script with a **bare expression** (`window.__x` or a string
  literal). Returning the value of an IIFE directly sometimes yields
  `missing value` even when the code ran — store on `window`, then read the
  variable as the last expression.
- `'pending'` means poll again, not failure. Budget polling delay by request
  count and keep polling bounded.

## Large outputs: redirect stdout to a file

This channel's key advantage over `javascript_tool`: return values arrive on
stdout, so `osascript scripts/runjs.applescript read.js <conversation-id> > transcript.md` captures them
whole — multi-megabyte base64 output was verified in practice. No 14–18k
paging windows needed. Strip the stray CR/LF
with `tr -d '\n'` before base64-decoding if you emitted one long line.

`osascript` may print a `CFURLGetFSRef was passed a URL which has no scheme`
warning on stderr — it's noise from the file-read syntax; suppress with
`2>/dev/null` when redirecting.

## Binary file transfer (base64 bridge)

To pull binary files (images, xlsx, anything the download endpoints serve — see
the endpoints reference), bridge bytes as base64 through the string channel:

**In-page (step 1):** fetch each file, encode in 32 KB chunks (a single
`String.fromCharCode.apply(null, wholeArray)` overflows the call stack on
larger files):

```js
const toB64 = (buf) => {
  const bytes = new Uint8Array(buf);
  let bin = '';
  for (let i = 0; i < bytes.length; i += 32768)
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
  return btoa(bin);
};
// window.__dl[name] = toB64(await (await fetch(url)).arrayBuffer());
```

**On the shell side (step 2), one file per call:**

```bash
osascript scripts/runjs.applescript read_one.js <conversation-id> 2>/dev/null | tr -d '\n' | base64 -d > "file.xlsx"
```

**Always verify after decoding:** `file <name>` for magic-bytes (should say
`Microsoft Excel 2007+`, `PNG image data`, etc. — not `ASCII text`), and byte
size against the metadata the conversation payload carries (each entry in a
message's `files[]` has `size_bytes`). A size match to the byte is strong
evidence of an uncorrupted transfer.

## Cleanup etiquette

The page belongs to the user — leave it as found:

- Delete the temporary globals at the end:
  `delete window.__export; delete window.__dl; 'cleaned'`
- Remind the user to toggle **Allow JavaScript from Apple Events** back off.
- Don't navigate, click, or mutate the DOM beyond what the export needs; if
  you clicked a Download button (native downloads land in `~/Downloads`,
  duplicates get ` (1)` suffixes), tell the user which files appeared there.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Executing JavaScript through AppleScript is turned off` | The menu toggle is off | Relay the menu path from the error to the user; wait for them to enable it |
| `osascript` hangs then times out on first use | macOS Automation permission dialog is waiting | Ask the user to click Allow in the system dialog |
| `TAB_NOT_FOUND` | Conversation not open in any tab, or URL substring wrong | Recheck only the target conversation ID; ask the user to open that conversation |
| `missing value` from a script that should return data | Returned an IIFE result directly, or promise not settled | Store on `window`, end with a bare expression; poll again after a sleep |
| `'pending'` forever | The async step threw before writing the variable | Wrap the IIFE body in try/catch that writes `{ok:false, error}` (as in the template), re-fire, read the error |
| Decoded file is garbage / `ASCII text` | Truncated or newline-polluted base64 | Redirect stdout to file, `tr -d '\n'`, compare against `size_bytes` |
| Chrome dialog blocks everything | Injected JS triggered `alert`/`confirm` | Don't call dialog APIs in injected code; user must dismiss manually |
