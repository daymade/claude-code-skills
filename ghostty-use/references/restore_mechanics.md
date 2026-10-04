# Restore mechanics: why paste-based reopen and how it stays honest

Verified on Ghostty 1.3.1, macOS 26 (Darwin 25/27), 2026-10-04.

## Why there is no clean restore path

| Attempted path | Result on Ghostty 1.3.1 macOS |
|---|---|
| `ghostty +new-window` CLI action | `+new-window is not supported on this platform` (verified) |
| AppleScript tab dictionary | none — System Events shows one window title only, no tab elements |
| AX tab→window mapping | absent — grouping is not recoverable, report this boundary up front |
| macOS window-state restore (Cmd+T…) | reopens empty shells only, never the sessions |

## The working protocol

1. Verify Accessibility first:
   `osascript -e 'tell application "System Events" to get UI elements enabled'` —
   `false` means keystrokes will silently do nothing useful; grant it before
   restoring 40 tabs.
2. Per session: activate Ghostty → Cmd+T → write reopen command to clipboard →
   Cmd+V → Return. Timing constants (0.8s activate / 1.2s tab / 0.4s paste)
   are in `scripts/ghostty_session.py::_paste_tab` — tune there, not in SKILL.md.
   During a restore run, keyboard/mouse interruption is the main failure mode:
   an interrupted step leaves an empty tab whose command was never delivered.
3. **Auto-reconciliation is the honesty mechanism.** Paste return codes only say
   osascript itself succeeded; they cannot say the command landed. After the
   loop, re-enumerate live sessions by UUID and print every missing session with
   its manual reopen command. Never declare success from paste receipts alone —
   measured 39/40 on a 40-tab restore where one paste was interrupted and the
   auto-check was the only thing that surfaced it.
4. Codex may drop sessions whose rollout left the default tree (`no-artifact`):
   the reopen command is still `codex resume <id>`; treat as best effort.
5. Window grouping is not recoverable (no AX tab→window mapping); all tabs
   reopen into one window. Tell the user this boundary before a large restore.

## Profile env mapping

Claude profiles that boot via environment (e.g. `CLAUDE_CONFIG_DIR`) cannot be
recovered from the process command line (env is invisible to `ps`). Restore
replays the captured `--settings` flag; if profile context beyond settings is
needed, record prefixes in the user-local `~/.ghostty-session/profile-env.json`:

```json
{"research": "CLAUDE_CONFIG_DIR=~/.claude-profiles/research", "profile-name": "ENV=k v"}
```

No default mapping ships; the file is user data outside the bundle.

## Snapshot schema (output contract)

`~/.ghostty-session/snapshots/snapshot-<ts>.json` + `latest.json` pointer:

```json
{
  "captured_at": "ISO-8601 local",
  "active_hours_threshold": 48,
  "sessions": [
    {"tty": "ttys001", "tool": "claude|codex", "sid": "<uuid>",
     "cwd": "<working dir>", "cmdline": "<captured argv>",
     "profile": "<settings-name or direct>",
     "last_interaction": "<UTC ISO or null>", "error": "ok|login-expired|api-error|no-file",
     "status": "active|stale|dead-channel|no-artifact|stale+api-error",
     "age_hours": 0.5}
  ]
}
```

Users may hand-edit a snapshot (drop rows, edit cwd) before restore — it is
user data, not a locked contract.
