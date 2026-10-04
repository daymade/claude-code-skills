---
name: ghostty-use
description: >-
  Snapshots, restores and reconciles Claude Code / Codex sessions inside Ghostty tabs
  across reboots. Use when quitting the Mac for an update (保存终端会话 / 重启前备份终端),
  after restart to reopen tabs with their original session IDs (恢复之前的窗口 / restore
  my ghostty tabs), or to audit which sessions survived. Not for resuming one conversation
  via its own --resume, terminal screenshots, or tmux state.
---

# ghostty-use

Seamlessly carry Claude Code and Codex terminal sessions across a reboot: capture every
live session with a liveness grade before shutdown, reopen all worthwhile tabs with their
original session IDs after restart, and prove nothing was silently dropped.

Ghostty on macOS has no session-restoration CLI or AppleScript tab dictionary (verified
on Ghostty 1.3.1, 2026-10-04), so this skill walks a practical loop around that limit:
`ps`-derived session inventory → liveness-graded snapshot → keystroke-paste restore →
automatic reconciliation that makes every paste failure visible.

## Entry decision tree

| You just said / want | Run |
|---|---|
| Quitting for an update / reboot ("重启前保存会话") | `snapshot` |
| Rebooted, want tabs back ("恢复之前的窗口") | `restore` (then read its auto-check) |
| "Was anything lost?" / suspicion after restore | `check` |
| One specific session to bring back | `restore --only <id-prefix>` |

## Quick start

```bash
# Before quitting (from any directory):
python3 <skill-dir>/scripts/ghostty_session.py snapshot

# After restart (from any directory; needs Accessibility permission for keystrokes):
python3 <skill-dir>/scripts/ghostty_session.py restore        # active sessions only
python3 <skill-dir>/scripts/ghostty_session.py restore --all  # include stale ones
```

The snapshot lands in `~/.ghostty-session/snapshots/` (home-relative, survives reboot).
`restore` finishes with an auto-check that prints `N/M present` plus a manual reopen
command for anything missing — read it before declaring success.

## What snapshot records per session

- **Anchor**: the session UUID from the process command line (never match on process
  names — argv[0] flips between bare `claude` and `/usr/local/bin/claude`, and name
  matching produced two false "all sessions gone" reports on 2026-10-04).
- **Liveness**: last real interaction time read from the *content* of the session file —
  not the file mtime (idle TUIs keep touching files; on 2026-10-04 an "active this
  afternoon" read was contradicted by in-file timestamps showing death at 03:21).
- **Channel health**: `dead-channel` when a Claude transcript's tail carries a
  structured `isApiErrorMessage` with "Login expired" — restoring such a tab reopens
  history but the session stops at `/login`; the snapshot marks it so you can skip it.
  Prose inside a conversation that merely *discusses* an error never counts (a healthy
  session that once talked about "Login expired" was misclassified before this rule).
- **Profile**: parsed from `--settings .../settings/<name>.json` when present, else
  `direct`.

## Restore mechanics and limits

- Reopen = activate Ghostty → Cmd+T → clipboard-paste the reopen command → Return, one
  tab per session, followed by mandatory auto-reconciliation. Keystroke paste is
  timing-sensitive: an interruption between Cmd+T and the paste leaves an empty tab
  whose command was silently lost (measured 2026-10-04). The auto-check exists to make
  that visible; never skip it, and never declare success from paste return codes alone.
- Requires **Accessibility permission** for `osascript` keystrokes (System Events).
- Window grouping is **not** restorable — Ghostty's macOS accessibility surface exposes
  no tab→window mapping. All tabs reopen into one window; reorder manually if needed.
- Rollout files that codex itself cannot find anymore print `no-artifact`; restoring
  them replays the same `codex resume <id>` and stays a best effort.

## Profile environment mapping (optional)

If your Claude profiles inject config via environment (e.g. `CLAUDE_CONFIG_DIR`), record
prefixes in `~/.ghostty-session/profile-env.json` so restored tabs boot the same profile
context:

```json
{"research": "CLAUDE_CONFIG_DIR=~/.claude-profiles/research", "family": "HTTP_PROXY=http://127.0.0.1:7890"}
```

Without it, restores replay the captured `--settings` flag only. The mapping is
user-local data outside the skill bundle; no default mapping ships.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `restore` reports `STILL MISSING` | paste raced an interruption; run the printed reopen command by hand in a new tab |
| `no-artifact` on a codex session | its rollout file is gone from `~/.codex/sessions`; `codex resume <id>` is best-effort |
| `dead-channel` sessions restored anyway | expected: history reopens, session stops at `/login`; re-auth or switch provider |
| `check` says present but tab looks empty | another live process already claimed that session id (e.g. resumed in another tab) |
| osascript refuses keystrokes | grant Accessibility (System Events) permission; verify with `osascript -e 'tell application "System Events" to get UI elements enabled'` |
| session list empty right after opening tabs | TUIs take a few seconds to write their argv UUID; re-run after a pause |

## Deeper details

- [references/session_liveness.md](references/session_liveness.md) — storage layouts
  (Claude projects / Codex sessions), transcript structures, resume-fork naming,
  liveness rules and the misclassification cases behind them. Read when a liveness
  result looks wrong or layouts changed after an app update.
- [references/restore_mechanics.md](references/restore_mechanics.md) — why Ghostty
  offers no CLI/AX restore path, the keystroke-paste protocol, reconciliation design,
  and the window-grouping boundary. Read before modifying the restore path.
