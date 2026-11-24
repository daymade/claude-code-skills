# Background targeted `/compact`

Use this route for explicitly authorized Claude Code sessions in Ghostty when
long contexts strain a shared provider tokens-per-minute (TPM) limit. If the
provider counts cache reads toward TPM, a peer message can wake the receiving
session and spend another large cache read before it can compact. Send the local
`/compact` command directly to the bound surface. Compaction itself can still
require provider capacity.

## Set up and discover sessions

Use Ghostty 1.4 or later on macOS for the native AppleScript `tty`, `pid`,
`input text`, and `send key` interfaces. Keep `macos-applescript = true` in
Ghostty's configuration. Grant the invoking app macOS **Automation** permission
to control Ghostty. The foreground `restore` workflow uses System Events
**Accessibility** permission for keystrokes. [Ghostty AppleScript setup](https://ghostty.org/docs/features/applescript)

Run discovery from a separate terminal or controller outside the Claude target
set. This command reads live bindings without sending terminal input or writing a
plan.

```bash
python3 "<skill-dir>/scripts/ghostty_session.py" compact --all-claude --dry-run --json
```

If discovery exits 2 because an unrelated Claude TUI has unresolved identity
or the batch includes your own TTY, run this read-only inventory command.

```bash
python3 "<skill-dir>/scripts/ghostty_watch.py" probe
```

Read the resolved TTYs in `sessions` alongside `unresolved`. The probe can print
both lists and exit 1 when unresolved rows remain. Preview and freeze specific
resolved Claude targets with `--tty` or `--sid`, excluding your own TTY.

## Freeze, review, and send

Replace the illustrative TTY and prefix with the intended selections. Freeze
them in a new plan and inspect the target rows before executing that file.

```bash
python3 "<skill-dir>/scripts/ghostty_session.py" compact \
  --tty /dev/ttys012 --sid 00000000 --dry-run --write-plan compact-plan.json --json

python3 "<skill-dir>/scripts/ghostty_session.py" compact \
  --from-plan compact-plan.json --stagger 1.5 --verify-timeout 60 --json
```

- Review each target's tab index, terminal ID, TTY, SID, anchor, and title.
  An `argv` anchor identifies the launch SID. An in-place `/resume` can leave
  all six frozen binding fields unchanged, and a custom tab title override can
  hide the switch. `/compact` goes to whichever conversation is active in that
  surface at send time. If the conversation may have changed, re-establish its
  identity before sending. Transcript readback for the launch SID leaves the
  switched conversation unverified.
- Use `--write-plan` only with `--dry-run`. An existing plan file is preserved.
  Use `--from-plan` on its own with respect to selectors and dry-run flags.
  The script checks every frozen binding before the first send and again before
  each send. A vanished or replaced binding stops further input. Newly opened
  tabs are outside the plan.
- Supply one or more `--tty` values (with or without `/dev/`), one or more
  `--sid` prefixes, or explicit `--all-claude` for discovery, plan creation, or
  direct dispatch. When used directly without `--from-plan`, combined
  `--tty` and `--sid` selectors form a union and re-resolve live targets at send
  time.
- Use `--all-claude` from outside the target set. A selected self-TTY, unresolved
  or ambiguous binding, missing terminal ID, or Claude process outside the
  surface's foreground process group stops the batch before input.
- Use `--stagger` to space dispatches (default 1.5 seconds). Increase the spacing
  or send smaller batches when summarizations overlap. Timing spaces the sends
  and each compaction can continue in parallel.
- Target an idle Claude Code prompt with an empty input line. A busy TUI may
  queue the command until the turn finishes, and a draft or open prompt can
  consume the text or Enter keys. The script checks process ownership and
  leaves TUI readiness to the operator. It sends the text once and presses
  Enter twice for slash-command selection and submission.

## Read the result

Use `--json` to receive one object with `dry_run`, `targets`, and `error`.
Each target has a `status`. `dispatched_unverified` means native input returned
exit 0. `verified_compacted` means the bound session transcript contained a new
`compact_boundary` record timestamped at or after dispatch. Treat an automatic
compaction in that window as evidence of compaction in the session, with
`trigger` providing the reason when recorded.

With `--verify-timeout 0` (default), return after the sends and defer transcript
readback. With a positive timeout, poll the selected transcripts after dispatch.
Read up to 2 MiB per transcript tail per poll, plus one preceding byte to detect
a complete first record. Claude Code can append large attachments or metadata
after the boundary and push it outside that window.
Read `preTokens`, `postTokens`, `trigger`, and `durationMs` from the boundary's
`compactMetadata`. Absent values appear as JSON null. The script polls the
live resolver's anchored file or the exact SID file in the current project's
default Claude transcript bucket. A missing or unreadable transcript leaves the
send unverified.

Exit 0 means a valid dry run, all sends acknowledged when polling is off, or all
compactions verified when polling is requested. Exit 1 means a partial send,
a target that changed after preflight, or missing requested verification. Exit
2 means invalid selection, invalid or stale plan, or unavailable preflight
evidence. Read the per-target statuses after a partial batch. An input failure or
timeout can follow partial delivery, so check the target before sending again.

If Ghostty or the host denies scripting, stop input and report the reason. Use
the same route after the ordinary host authorization is available. Create and
review a fresh plan before retrying. Keep foreground input, clipboard automation,
and peer messaging out of this workflow.
