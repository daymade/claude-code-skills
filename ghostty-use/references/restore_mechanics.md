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
   restoring sessions.
2. Apply the entry's [foreground authorization](../SKILL.md#ghostty-interaction-channel).
   Tell the user to avoid keyboard/mouse input until reconciliation finishes.
   Per missing session: activate Ghostty → Cmd+T → write reopen command to clipboard →
   Cmd+V → Return. Tune paste timing only in
   [`ghostty_session.py::_paste_tab`](../scripts/ghostty_session.py).
   During a restore run, keyboard/mouse interruption is the main failure mode:
   an interrupted step leaves an empty tab whose command was never delivered.
   Stop input on takeover and reconcile read-only; do not restore the previous focus
   or continue the remaining paste sequence while ownership is lost. The script's
   notification and paste return values do not implement an ownership lock.
3. **Auto-reconciliation is the honesty mechanism.** Paste return codes only say
   osascript itself succeeded; they cannot say the command landed. After the
   loop, re-enumerate live sessions by UUID and print every missing session with
   its manual reopen command. Never declare success from paste receipts alone —
   an interrupted paste can leave a recorded ID absent. Per-tab `SENT (unverified)` is
   delivery acknowledgement only. Poll live UUIDs for a bounded interval using
   `--reconcile-seconds`; its default is defined in `main()` and its bounds in
   `bounded_seconds()` in the linked script above. Exit 1
   prints unobserved IDs, exact shell-quoted reopen commands, and an invocation
   restricted to those IDs. Review current retention intent before using it;
   absence does not establish a failed launch. A rerun skips already-present IDs.
4. Codex may drop sessions whose rollout left the default tree (`no-artifact`):
   the reopen command is still `codex resume <id>`; treat as best effort.
5. A host denial of Ghostty UI automation is a boundary, not a transport fault.
   Prepare the manifest and a user-run command; after the user runs it, reconcile
   read-only. Do not use osascript as an alternative to a denied UI tool.
6. Window grouping is not recoverable (no AX tab→window mapping); all tabs
   reopen into one window. Tell the user this boundary before a large restore.

## Reconcile the current wanted set

Keep the pre-update manifest as capture evidence. Bind the requested restore set
to the user's latest selection, rather than requiring its count to equal the old
snapshot. After a user-run restore, recheck with the same explicit manifest.
`PRESENT` proves a live recorded ID; `MISSING` means not observed running, with
cause unknown. Neither a matching count nor a matching cwd proves the visible
window, tab order or successful model requests.

Exclude an intentionally closed session only when its ID is explicitly identified
or a user-selected manifest supplies that exact set. A general statement that a
few tabs were closed does not identify which missing rows they were. Withdraw an
unsupported retry recommendation instead of diagnosing a crash from absence.
Keep an unidentified selection unknown; do not reopen it to satisfy a total.

```bash
# Apply the same explicitly identified exclusions to verification and restore:
python3 <skill-dir>/scripts/ghostty_session.py check --snapshot <manifest.json> --strict --exclude <closed-id>
python3 <skill-dir>/scripts/ghostty_session.py restore --snapshot <manifest.json> --all --exclude <closed-id> --dry-run
# After confirming the preview and foreground prerequisites, omit --dry-run.
```

`--exclude` accepts full IDs or unique prefixes. Unknown or ambiguous prefixes
fail before GUI input. Exclusions are invocation-local and never modify the
saved snapshot. Exit 1 from strict verification means a requested ID is not
observed, not that the user must restore it. Exit 0 covers only the selected AI
set; report captured ordinary terminals and unresolved TUIs separately. Their
recorded cwd and raw process evidence are not automatically replayed.

## Profile env mapping

Claude profiles that boot via environment (e.g. `CLAUDE_CONFIG_DIR`) cannot be
recovered from the process command line (env is invisible to `ps`). Restore
replays captured settings, model/profile and permission flags; if profile context beyond settings is
needed, record prefixes in the user-local `~/.ghostty-session/profile-env.json`:

```json
{"research": "CLAUDE_CONFIG_DIR=~/.claude-profiles/research", "profile-name": "ENV=k v"}
```

No default mapping ships; the file is user data outside the bundle.

## Snapshot schema (output contract)

`~/.ghostty-session/snapshots/snapshot-<ts>.json` + `latest.json` pointer.
Manual manifest excerpt; the [writer](../scripts/ghostty_session.py) defines the
complete output, including classification settings and generated coverage fields:

```json
{
  "captured_at": "ISO-8601 local",
  "scope": "Ghostty process descendants",
  "window_tab_mapping": "unknown",
  "terminal_inventory": [{"tty": "ttys001", "pid": 123, "cwd": "<working dir>", "cmdline": "<process evidence>", "kind": "ai"}],
  "other_terminals": [],
  "unresolved": [],
  "sessions": [
    {"tty": "ttys001", "tool": "claude|codex", "sid": "<uuid>",
     "cwd": "<working dir>", "cmdline": "<captured argv>",
     "profile": "<settings-name or direct>",
     "last_interaction": "<UTC ISO or null>", "error": "ok|login-expired|api-error|no-file|identity-unavailable",
     "status": "active|stale|dead-channel|no-artifact|unknown|active+api-error|stale+api-error",
     "age_hours": 0.5}
  ]
}
```

Users may hand-edit a snapshot (drop rows, edit cwd) before restore — it is
user data, not a locked contract.

Prefer invocation-local `--only`/`--exclude` for a changed restore selection so
the original evidence survives. `--expected-tabs <N>` adds `expected_tab_count`
from the user's observation; it is not a derived TTY/session count or proof of
window mapping. Unresolved TUIs and ordinary terminals are persisted even when
`sessions` is empty. Failed or empty process observations do not replace a useful backup.
Older manifests without these additive fields remain readable; their omitted
capture scope and ordinary-terminal coverage remain unknown. Reconstruction
preserves supplied capture metadata without treating it as newly observed.

Reconstructed manifests retain this sessions format and add `kind`, `coverage`,
`source_snapshot`, bounded `discovery` metadata, and per-row `membership`.
Old snapshots need no migration. Reconstruction writes a separate new file,
leaving the latest pre-reboot snapshot intact; use `restore --snapshot <file> --all`
to open the full chosen set, rather than letting active-only selection omit
waiting/quota/dead/stale records. See the ordinary reconstruction route in SKILL.md
for dependency resolution and candidate-selection commands.
