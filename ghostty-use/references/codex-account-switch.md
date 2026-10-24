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
send process-termination signals or close Ghostty wholesale: Claude Code may share the app.
For the login or credential-recovery step, follow
[local-codex's OAuth guide](https://github.com/daymade/claude-code-skills/blob/main/daymade-codex/local-codex/references/oauth-guide.md);
this script owns session preservation and restoration.

```bash
python3 <skill-dir>/scripts/ghostty_session.py switch-restore --dry-run
```

Expect commands for missing IDs. An unchanged account exits 2. `WAIT EXIT` lists
old/unverified live processes and exits 1 without opening. Resolve unresolved live
TUIs before opening: their unknown IDs could produce duplicates. Check identity,
original process generation, saved cwd/rollout and CLI support for `--no-daemon`.
Dry-run changes no progress, window, clipboard or login.

## Login already changed before capture

Keep a complete snapshot of the still-open Codex set under the target login.
Use the same fixed manifest, with an explicit mode on every retry:

```bash
python3 <skill-dir>/scripts/ghostty_session.py switch-restore \
  --snapshot <fixed-manifest> --after-login --check
python3 <skill-dir>/scripts/ghostty_session.py switch-restore \
  --snapshot <fixed-manifest> --after-login --only <missing-id> --dry-run
```

`--after-login` binds the target to the account captured in the snapshot. It does
not invent a previous account or prove that it changed. Original PID/birth pairs
remain old/unverified even when the credential file is already correct. New
independent processes must start at or after capture. In this mode, `--only`
may reopen missing selected IDs while other known original sessions stay open;
selected old processes and unresolved live identities still block opening.
The final report and exit 1 cover the entire fixed set, including deferred rows.
Progress binds both account and mode; do not remove it to force a different mode.

## Exit controls and the executing session

An authorized account switch may include normal exits through a currently allowed
host UI channel. It does not authorize signals, closing the whole app or touching
Claude windows. Snapshot and preserve work first. Plan the fixed set read-only:

```bash
python3 <skill-dir>/scripts/ghostty_session.py switch-plan \
  --snapshot <fixed-manifest> --current-session <full-uuid>
# Supply only a verified independent controller, outside the target process trees:
python3 <skill-dir>/scripts/ghostty_session.py switch-plan \
  --snapshot <fixed-manifest> --current-session <full-uuid> --executor-pid <pid>
```

Exit 1 without an executor defers the executing session; exit 0 records the
executor's current PID/birth and prints that session last. This verifies process
independence, not its account, quota or authority. Before the final exit, the
independent executor must possess the fixed manifest, original cwd/resume command,
authorized channel and sufficient target-account quota for the intended work.
It must remain alive outside the exiting agent's process tree. Recheck its birth
immediately before handoff. Preserve the original recovery command outside the
exiting terminal. Save an executor handoff at a new private path:

```bash
python3 <skill-dir>/scripts/ghostty_session.py switch-handoff \
  --snapshot <fixed-manifest> --current-session <full-uuid> \
  --executor-pid <pid> --out <private-handoff.json>
python3 <skill-dir>/scripts/ghostty_session.py switch-handoff-check \
  --handoff <private-handoff.json>
```

Keep `--after-login` on `switch-handoff` when the fixed snapshot was captured after
the target login. The handoff binds the original manifest bytes, restore mode,
target file-auth identity and executor PID/birth. It stores no second inventory or
credentials. The check reads the original manifest and prints the exact current
session reopen command and batch recovery command. Run that check from the
independent executor before taking over; a PID reused by another process, changed
manifest or account, unresolved identity, or executor inside a target process tree
exits 2. Creation refuses an existing output.

Exit 1 with `CURRENT EXIT BLOCKED` means the recovery inputs were checked but
host permission, exact surface/draft binding and usable account quota remain
unverified. It is deliberately not an exit-ready signal. No bundled script
implements a permitted GUI adapter or exits/restarts the executing session.
Do not launch another executor merely to make the PID check pass. A genuinely
independent controller must already own the allowed host context and the original
task continuation; a saved handoff cannot confer that context.

For each exit, bind the actual visible Ghostty surface to the exact Codex UUID,
TTY and live PID/birth using the host's current observations. A window title or
process argv alone does not establish which input surface will receive text.
Require a known empty draft, idle task state, foreground focus and exclusive
ownership. Preserve nonempty drafts and wait for work; never clear them to make
the precondition pass. Use one clipboard paste of the literal `/quit` or `/exit`,
then read the input back before Return. Missing slash, partial input, changed
focus or human takeover stops input immediately. Do not send a test prompt.

The existing `ghostty_switch.guarded_control(expected, control, controller)` helper
implements that two-observation sequence for an **authorized host adapter**. Its
`observe()` returns `app`, `tool`, `surface`, `sid`, `pid`, `started`, `tty`,
`allowed`, `foreground`, `exclusive`, `idle`, `draft`, `observed_at`; `expected`
binds the surface/session/process/TTY fields. Observations must be fresh (within
5 seconds); readiness booleans must be exactly true. `paste(text)` must paste the
complete literal and raise on failure; `submit()` sends Return once and raises
on failure or unknown delivery. The helper returns `submitted_unverified` only.
Reconcile process disappearance before restore; never retry an unknown submit.
Pass `receipt=<private-handoff-dir>/controls/<session-uuid>.json` to
`guarded_control` for each original target. Its write-ahead receipt is saved before
paste and before Return; any existing receipt blocks another delivery, including
after a process interruption. An initial denied/stale observation sends nothing
and creates no attempt. A failure after reserving input leaves `input_uncertain`;
a hard interruption may leave `paste_started` or `submit_started`. All require
read-only reconciliation of the original PID/birth and visible draft. Never
delete the receipt or choose a new path to replay the attempt. A terminal process
disappearance can establish normal exit; receipt success alone cannot.
The helper supplies no surface-binding GUI adapter: the host must obtain and
verify those observations through its permitted channel. It cannot turn supplied
metadata into permission. In particular, a terminal screen's title or text is
insufficient when it exposes no exact SID/TTY or independently observable draft.
A host denial stops GUI operation; do not fall back to
AppleScript or another channel to bypass it. Read-only plans/checks remain usable.
If a graceful exit cannot complete through the allowed channel, killing the
process is a separate, per-target authorization — follow
`~/.claude/references/irreversible-gates.md` §终止进程 (SIGTERM first,
post-kill terminal reset via `~/scripts/pty-tui-reset/pty-tui-reset.sh`);
a killed TUI leaves mouse-mode residue that floods the window.

## Reopen the original recorded set, not a blank session

Classify the request before opening anything. "Restore my sessions" around a
switch targets the fixed manifest's original set: the same SIDs, working
directories and replay-safe argv captured by `switch-prepare`. A new blank
`codex` tab is a different request — never substitute one for the set, never
count one as recovery, and never narrow the set to what is convenient to open.
An explicit request for a fresh blank session needs no manifest and is outside
this route.

When opening is blocked or delegated — the user keeps old processes and clears
session locks themselves, or the current host denies Ghostty UI automation —
deliver the complete exact command set with per-item status, not a demand that
old processes exit first and not blank terminals:

```bash
# Read-only, no account precondition: exact reopen command per fixed-set SID,
# executing session last. Exit 1 without an executor is the deferral signal;
# the printed REOPEN set is still the deliverable.
python3 <skill-dir>/scripts/ghostty_session.py switch-plan \
  --snapshot <fixed-manifest> --current-session <executing-session-full-uuid>

# Mode-bound reconciliation; retain --after-login for post-login capture:
python3 <skill-dir>/scripts/ghostty_session.py switch-restore \
  --snapshot <fixed-manifest> --check
```

Pass `--current-session` only the executing session's true full UUID when it
belongs to the fixed set; never substitute another target's SID. Unresolved
live identity or duplicate SIDs can block this plan. If the coordinator is
outside the set, or live reconciliation is blocked, prepare the complete
commands through the same bundled helpers without probing accounts or processes:

```bash
python3 -B - '<skill-dir>/scripts' '<fixed-manifest>' <<'PY'
import sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import ghostty_session as gs
import ghostty_switch as sw
_, saved = sw.current_manifest(gs, SimpleNamespace(snapshot=sys.argv[2]))
targets = sw.main_sessions(saved, gs)
for row in targets['sessions']:
    print('UNVERIFIED ' + row['sid'])
    print('  REOPEN ' + sw.command(row, saved['codex_home']))
PY
```

This reads the fixed manifest and each saved rollout's identity metadata. It
retains the existing legacy-subagent filter: report each `SKIP SUBAGENT` with
its saved parent; an unavailable/mismatched rollout or absent parent fails.
It does not authorize opening any command or establish live status. Keep each
target unverified until reconciliation. The mode-bound check reports reopened,
old/unverified and missing once its account precondition holds; plan `live_pid`
columns show presence only. Old-PID and duplicate-SID refusals remain unchanged;
the helpers cannot certify successful restoration while duplicate copies remain.

Printing commands is preparation, not recovery. Any actual reopen requires the
current host's permission; a host denial stops GUI input and is not bypassed
through a CLI, AppleScript or another UI channel — deliver the command set and
reconcile after permitted execution. Whoever runs a delivered command later
acts under their own authorization; the command preserves identity and options
and confers no permission. Account adoption, authenticated continuation and
billing stay layered as defined in [the acceptance section](#accept-actual-continuation).

Accept the delivered command set only by independent comparison against the
original fixed manifest: every independently resumable `sessions[]` row needs
its exact SID, cwd, CODEX_HOME and full argv, with every legacy subagent
explicitly accounted for by its saved parent rather than resumed separately.
A blank or new session, an omitted row, a wrong cwd or an altered flag fails.
Matching the delivery's prose or keywords is not acceptance.

## Restore and resume an interrupted batch

Apply the Skill entry's foreground check: use an authorized bounded Ghostty handoff
or an existing explicit idle-desktop grant plus current exclusive ownership. Notify
the user to leave keyboard and mouse untouched through reconciliation; do not ask
again when the standing grant covers this action. Busy/unknown occupancy or takeover
stops global input, while dry-run/check work continues. Do not bypass a host denial.

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

Keep `--after-login` on each restore/check/retry when using
[post-login capture](#login-already-changed-before-capture). The examples above
show the normal pre-login snapshot route. Generic reboot `check` establishes
presence only and cannot replace this account/process reconciliation.

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
means the fixed set reopened in eligible independent process generations under
the mode-bound file-auth context: changed identity for the normal route, captured
target identity for `--after-login`. Neither mode proves authenticated continuation.
Exit 1 means missing/old processes or a further account change;
exit 2 means invalid input, unavailable evidence or failed prerequisites. Missing
rows print an exact retry limited to their UUIDs. Progress/result sidecars leave
the original manifest untouched. Read the report as well as the exit code.

## Accept actual continuation

Distinguish restoration from usability. Reopened original IDs under the selected
mode's account/process checks prove restoration; live processes and credential hashes
do not prove that new-account requests succeeded. Observe the user's intended
work continuing in every restored session before claiming end-to-end success.

Send no test prompt through this workflow. Report authentication as `not_checked`
until real continuation is observed; keep unavailable GUI/authentication evidence
explicit. Local identity, successful authentication, remaining quota, process
adoption and billing policy are separate facts. Neither reopening nor OAuth
authentication proves that paid Credit is disabled. Run synthetic control-flow regressions with
`python3 -m unittest discover -s <skill-dir>/scripts -p 'test_ghostty*.py'`;
those tests do not replace the manual switch acceptance.
