---
name: ghostty-use
description: >-
  Snapshots, restores and reconciles Claude Code / Codex sessions inside Ghostty tabs
  across reboots. Use when quitting the Mac for an update (保存终端会话 / 重启前备份终端),
  after restart to reopen tabs with their original session IDs (恢复之前的窗口 / restore
  my ghostty tabs), or to audit which sessions survived. Not for resuming one conversation
  via its own --resume, terminal screenshots, or tmux state. Also use for periodic
  change-only snapshots (定期增量快照 / 没变化不记录).
  Also use before or after a manual Codex account switch (额度耗尽换号 / 换号后恢复全部 Codex).
---

# ghostty-use

Capture identifiable Claude Code and Codex terminal sessions before a reboot and
reopen recorded IDs afterwards. Manual snapshots grade liveness; automatic backups
store recovery metadata with explicit partial coverage and unknown liveness.

Snapshot, reconstruction, dry-run and reconciliation can proceed without taking
the desktop. Actual restore uses global keyboard/clipboard input and is foreground
work even when launched as a background shell job. Before restore, use a concrete
Ghostty handoff or existing explicit idle-desktop permission; check current activity
and coordinate exclusive agent ownership. Under that standing grant, notify and
execute without asking again. Idle input alone is not ownership. If busy/unknown,
continue preparation and read-only checks; stop input on human takeover and never
restore your old focus. Host denials remain binding.

## Entry decision tree

| You just said / want | Run |
|---|---|
| Quitting for an update / reboot ("重启前保存会话") | `snapshot` |
| Periodic backup, save only changes ("定期增量快照") | Read automatic-snapshots.md, then `ghostty_watch.py install --apply` |
| Rebooted, want tabs back ("恢复之前的窗口") | Use a suitable snapshot; if absent or outdated, `reconstruct`, then `restore --all` on the selected manifest |
| "Was anything lost?" / suspicion after restore | `check` |
| One specific session to bring back | `restore --only <id-prefix>` |
| Codex quota running out; manually switching account, keeping all Codex work | Read codex-account-switch.md; `switch-prepare` → manual exit/login → `switch-restore` |

## Codex account switch

Preserve all Ghostty Codex sessions before the user manually switches ChatGPT
accounts, then reopen the original session IDs in one batch. Exclude Claude Code.
Read [codex-account-switch.md](references/codex-account-switch.md) before this route.
Use `scripts/ghostty_session.py switch-prepare` and `switch-restore`; the bundled
`scripts/ghostty_switch.py` owns fixed-manifest selection, account/process checks,
duplicate-safe retries and separate authentication reporting.
If login already changed before capture, use the explicit `switch-restore
--after-login` branch. For a controlled exit sequence including the executing
session, use `switch-plan --current-session <full-uuid>` first; it defers that
session until an independent executor exists. Save its recovery inputs outside the
exiting terminal with `switch-handoff`, then recheck them with
`switch-handoff-check`; these commands preserve the host-adapter gap rather than
authorize an exit. The reference specifies the exact commands and durable
literal-control receipt.

```bash
python3 <skill-dir>/scripts/ghostty_session.py switch-prepare
# User: finish work, exit the saved Codex TUIs and manually switch account.
python3 <skill-dir>/scripts/ghostty_session.py switch-restore
```

Default to tabs in one window; use `--layout windows` only when independent windows are requested.
Keep the printed fixed manifest through the handoff. Treat unresolved capture,
unverified original processes and missing sessions as incomplete. Mode selection,
account preconditions and partial-restore readiness belong to
[the switch SOP](references/codex-account-switch.md). Never send process-termination
signals or switch credentials through this route; normal local exit controls use
that SOP's authorized-host protocol. Apply the foreground
conditions above before actual opening; ask only when that handoff is missing. `--dry-run` and `--check`
remain read-only. Distinguish reopened IDs from new-account requests that worked:
the script reports authentication as `not_checked` and sends no test prompt.

## Quick start

```bash
# Before quitting (from any directory):
python3 <skill-dir>/scripts/ghostty_session.py snapshot

# After restart (from any directory; needs Accessibility permission for keystrokes):
python3 <skill-dir>/scripts/ghostty_session.py restore        # manual: active only; automatic: full recorded set
python3 <skill-dir>/scripts/ghostty_session.py restore --all  # include waiting/quota/dead/stale/unknown records
```

The snapshot lands in `~/.ghostty-session/snapshots/` (home-relative, survives reboot).
The report accounts for every live TUI: captured sessions plus an `unresolved`
section for fresh tabs that have no transcript yet — a session count lower than
the tab count is explained there, not silently lost.
`restore` skips already-live IDs by default. It finishes with a bounded auto-check
that prints `N/M present`, a manual reopen command and a retry command containing only
missing IDs. Read that result before declaring success; per-tab `SENT (unverified)`
is a paste acknowledgement, not proof that a session reopened. Re-running the same
manifest opens only the IDs still missing. `--dry-run` prints commands without GUI actions.

## Automatic change-only backups

Read [automatic-snapshots.md](references/automatic-snapshots.md) before installing
or operating `scripts/ghostty_watch.py`. It saves only changed restore state and
keeps all prior versions. Unchanged
rounds write no snapshot or routine log. Automatic manifests cover Ghostty
process descendants without transcript reads; their liveness is explicitly unknown
and `restore` selects the whole recorded set. UUID-less TUIs remain unresolved in
automatic manifests — the watcher's bounded scan deliberately reads no transcripts;
manual snapshot/check/restore resolve them (see the anchor bullet below).
Partial observations preserve prior missing IDs conservatively. The watcher never
opens apps or tabs. Manual snapshots keep their active-only restore default.

## No suitable snapshot: reconstruct the recovery manifest

For Codex identity and indexed recovery, use the maintained
`daymade-claude-code:read-codex-history` dependency. Resolve that Skill's directory
from the current host; install its `daymade-claude-code` plugin through the host's
ordinary marketplace flow when authorized and absent. The script discovers a source
checkout or a separately installed sibling `read-codex-history`; other layouts use
`--history-reader <reader-skill-dir>` or `GHOSTTY_CODEX_HISTORY_READER`. Missing reader
or state index fails explicitly; do not replace it with a rollout corpus scan.

```bash
# Review candidates without writing state or opening tabs:
python3 <skill-dir>/scripts/ghostty_session.py reconstruct \
  --history-reader <reader-skill-dir> --recent-hours 72 --limit 100 --dry-run

# Build one chosen set in a NEW file; --only accepts unambiguous ID prefixes:
python3 <skill-dir>/scripts/ghostty_session.py reconstruct \
  --history-reader <reader-skill-dir> --since <YYYY-MM-DD> \
  --only <id-prefix-1> <id-prefix-2> --out <recovery-manifest.json>

# Restore the full selected set in one invocation, including waiting/quota rows:
python3 <skill-dir>/scripts/ghostty_session.py restore \
  --snapshot <recovery-manifest.json> --all
```

Reconstruction merges the optional `--snapshot` (otherwise latest, if present) with
bounded recent indexed Codex candidates. It verifies internal rollout identity using
the owning reader and marks each row `past-snapshot` or `indexed-terminal-candidate`.
Terminal evidence is `source=cli` or `originator=codex-tui`; actual TUIs can report
`source=vscode`. `--terminal-source` and `--terminal-originator` customize those
accepted metadata values. Subagents are excluded by the owning inventory's metadata,
not by underscores in filenames. `--codex-home` selects a nondefault Codex store.

Past membership proves only that a session appeared in that snapshot. Indexed
terminal candidates prove terminal origin, not that the tab was live at shutdown.
Review timestamps/titles and select the intended set before restore. `--limit` is a
hard cap on indexed candidates inspected; widen discovery bounds only when needed.
No snapshot means Claude membership remains unknown;
reconstruction does not discover Claude sessions. Preserve explicit Claude records
from a known snapshot rather than claiming an exhaustive recovery.

The new manifest never changes `snapshots/latest.json` and refuses to overwrite an
existing output. Exit 0 means the selected evidence was verified; exit 1 means the
manifest lists rejected candidates requiring attention; exit 2 means invalid input
or unavailable evidence. Dry-run output is JSON for inspection.

## What manual snapshot records per session

- **Anchor**: the session UUID from the process command line when present (never
  match on process names — argv[0] flips between bare `claude` and
  `/usr/local/bin/claude`). Fresh TUIs carry no UUID on argv (only
  resume/fork writes one), so they are anchored from transcript storage instead:
  the session file born at or after the process started, in the project bucket
  of the same cwd, internal identity verified. When several
  fresh TUIs share one bucket, transcripts are assigned disjointly — one file
  per TUI; an undecidable race (equidistant claims) refuses to the unresolved
  section rather than guessing. Live TUIs matching neither way are printed as
  unresolved rows in the snapshot report — visible, never silently dropped.
- **Liveness**: last real interaction time read from the *content* of the session file —
  not the file mtime, which can change without real interaction.
- **Channel health**: `dead-channel` when a Claude transcript's tail carries a
  structured `isApiErrorMessage` with "Login expired" — restoring such a tab reopens
  history but the session stops at `/login`; the snapshot marks it so you can skip it.
  Prose inside a conversation that merely *discusses* an error never counts.
- **Profile**: parsed from `--settings .../settings/<name>.json` when present, else
  `direct`.

## Restore mechanics and limits

- Reopen = activate Ghostty → Cmd+T → clipboard-paste the reopen command → Return, one
  tab per missing session, followed by mandatory auto-reconciliation. Keystroke paste is
  timing-sensitive: an interruption between Cmd+T and the paste leaves an empty tab
  whose command was silently lost. The auto-check exists to make
  that visible; never skip it, and never declare success from paste return codes alone.
- Before any paste, tell the user to leave keyboard and mouse untouched through
  reconciliation. The script repeats this notice before its first GUI action.
- Requires **Accessibility permission** for `osascript` keystrokes (System Events).
  If the current host denies Ghostty UI automation, do not switch channels to
  bypass it: prepare the selected manifest and exact user-run restore command,
  then reconcile after permitted execution. Reboot recovery uses read-only
  `check --snapshot <manifest> --strict`; account switching uses
  [the mode-bound switch check](references/codex-account-switch.md#restore-and-resume-an-interrupted-batch).
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

Without it, restores replay captured settings, profile and permission/model flags;
process environment beyond argv remains unknown. The mapping is
user-local data outside the skill bundle; no default mapping ships.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `restore` reports `STILL MISSING` | run the printed missing-only retry, or the exact reopen command by hand in a new tab |
| `no-artifact` on a Codex session | the verified indexed session has no usable rollout; resume remains best-effort |
| `unknown` Codex liveness | reader/index unavailable or identity ambiguous; resolve the dependency/store instead of choosing the first filename match |
| `dead-channel` sessions restored anyway | expected: history reopens, session stops at `/login`; re-auth or switch provider |
| `check` says present but tab looks empty | another live process already claimed that session id (e.g. resumed in another tab) |
| osascript refuses keystrokes | grant Accessibility (System Events) permission; verify with `osascript -e 'tell application "System Events" to get UI elements enabled'` |
| a brand-new tab is missing from the session list | a fresh TUI has no argv UUID and its transcript file appears with its first message; until then it shows under unresolved live TUIs. If the first message came >20 minutes after the tab opened, the birth window has passed and the tab stays unresolved by design |

## Deeper details

- [references/session_liveness.md](references/session_liveness.md) — storage layouts
  (Claude projects / Codex sessions), transcript structures, resume-fork naming,
  liveness rules and the misclassification cases behind them. Read when a liveness
  result looks wrong or layouts changed after an app update.
- [references/restore_mechanics.md](references/restore_mechanics.md) — why Ghostty
  offers no CLI/AX restore path, the keystroke-paste protocol, reconciliation design,
  and the window-grouping boundary. Read before modifying the restore path.
