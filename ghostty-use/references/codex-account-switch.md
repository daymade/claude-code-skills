---
name: codex-account-switch
description: >-
  Save and reopen all Ghostty Codex sessions around a manual ChatGPT account
  switch. Read for quota exhaustion, pre-switch capture, post-switch restoration
  or interrupted batch recovery; exclude Claude Code.
---

# Manual Codex account switch

Keep ongoing Codex work available when account quota runs out. Save the open
session set before exit, let the user change accounts, then restore the same
session IDs, working directories and replay-safe options in one batch. Do not
require a reboot. Leave Claude Code outside capture, transcript reads and restore
actions. Keep the existing reboot and automatic-backup routes available.

## Save before switching

```bash
python3 <skill-dir>/scripts/ghostty_session.py switch-prepare
```

Expect `PREPARED N/N Codex sessions -> <fixed-manifest>` with each saved UUID and
cwd. Select Ghostty descendants only, deduplicate Node/vendor wrapper pairs,
resolve fresh main TUIs through the existing bounded identity helper and verify the
state-index selected rollout through `read-codex-history`. Include idle sessions
regardless of liveness. Return 1 with `INCOMPLETE` and unresolved rows when any
TUI lacks usable identity or replay-safe options; resolve these before exit and
take another complete snapshot.
Fresh candidate matching excludes explicit sub-agent metadata. An argv-anchored
sub-agent makes capture incomplete rather than becoming a standalone resume command.

Use the maintained `daymade-claude-code:read-codex-history` dependency resolution
from SKILL.md. If discovery cannot locate it, pass
`--history-reader <reader-skill-dir>`; a missing reader/index fails explicitly.
Pass `--codex-home <store>` for a nondefault store; retain it through manual login.
Require the observed set to resolve in that one store. Mixed-store TUIs are not
supported by this route; preserve an incomplete capture rather than assuming the
caller's CODEX_HOME establishes every process's environment.

Keep immutable snapshots under `~/.ghostty-session/switches/` (mode 0600).
`--out <new-file>` chooses another new path and refuses overwrite. Publish
`switches/current.json` only for a complete capture; partial captures preserve
the earlier complete pointer. Leave reboot `snapshots/latest.json` untouched,
so periodic backups cannot replace the chosen handoff. An empty inventory fails
and preserves the pointer. Prepare again before each new account switch.

Record stable account/subject hashes, PID/start time, UUID, cwd, verified rollout
and replay-safe argv; save no tokens or credential contents. Token refresh is
not a switch. Require ChatGPT file-auth identity in the selected store;
keyring-only, API-key and remote/local-provider sessions are outside this route.
Keep unavailable identity an explicit error.

## Manual handoff and readiness

Let work finish before exit. The user exits the saved Codex TUIs and changes
ChatGPT account in the saved CODEX_HOME. Do not log out, rewrite credentials,
terminate processes or close Ghostty wholesale: Claude Code may share the app.

```bash
python3 <skill-dir>/scripts/ghostty_session.py switch-restore --dry-run
```

Expect commands for missing IDs. An unchanged account exits 2. `WAIT EXIT` lists
old/unverified live processes and exits 1 without opening. Resolve unresolved live
TUIs before opening: their unknown IDs could produce duplicates. Check identity,
original process generation, saved cwd/rollout and CLI support for `--no-daemon`.
Dry-run changes no progress, window, clipboard or login.

## Restore and resume an interrupted batch

Obtain the user's authorized, bounded Ghostty input handoff; tell them to leave
keyboard and mouse untouched through reconciliation. Do not send global
keystrokes without that handoff or bypass a host denial.

```bash
# Reopen missing sessions as tabs in one window:
python3 <skill-dir>/scripts/ghostty_session.py switch-restore

# Open independent windows only when requested:
python3 <skill-dir>/scripts/ghostty_session.py switch-restore --layout windows

# Pin an earlier handoff after another preparation:
python3 <skill-dir>/scripts/ghostty_session.py switch-restore --snapshot <fixed-manifest>

# Reconcile without GUI actions:
python3 <skill-dir>/scripts/ghostty_session.py switch-restore --check
```

Reopen with saved CODEX_HOME, cwd, UUID, model/profile and permission options.
Add `--no-daemon` to avoid the shared background server. Do not replay initial
prompts, reattach startup images or create another managed worktree. Fail on
unknown/unsafe options rather than guessing them. Use Cmd+N for independent
windows or Cmd+T for tabs; original positions, splits and grouping remain unknown.
Verify shortcuts when Ghostty configuration remaps them. Clipboard delivery is
timing-sensitive; paste acknowledgement alone does not prove reopening.
For an older manifest containing a spawned agent, skip that row when its main
parent is also saved. If the main parent is absent, stop before opening and
report the parent ID; never independently resume the spawned agent.

Bind progress to the fixed manifest and new account outside the Skill bundle.
Serialize opening, re-probe account/process state before each send, stop on
explicit send failure, and reconcile within `--reconcile-seconds` (0–60,
default 10). Do not count processes predating the handoff or lacking independent
mode. Rerun using persisted progress to open only missing IDs. If the account
changes again mid-handoff, stop and prepare a new handoff.

Expect `reopened: N/M`, old/unverified processes and every missing ID. Exit 0
means the fixed set reopened in new process generations under the changed
file-auth context; exit 1 means missing/old processes or a further account change;
exit 2 means invalid input, unavailable evidence or failed prerequisites. Missing
rows print an exact retry limited to their UUIDs. Progress/result sidecars leave
the original manifest untouched. Read the report as well as the exit code.

## Accept actual continuation

Distinguish restoration from usability. Reopened original IDs under a changed
local account context prove restoration; live processes and credential hashes
do not prove that new-account requests succeeded. Observe the user's intended
work continuing in every restored session before claiming end-to-end success.

Send no test prompt through this workflow. Report authentication as `not_checked`
until real continuation is observed; keep unavailable GUI/authentication evidence
explicit. Run synthetic control-flow regressions with
`python3 -m unittest discover -s <skill-dir>/scripts -p 'test_ghostty*.py'`;
those tests do not replace the manual switch acceptance.
