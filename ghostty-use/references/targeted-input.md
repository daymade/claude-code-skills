# Background targeted `/compact`

Use this route for explicitly authorized Claude Code sessions in Ghostty when
long contexts strain a shared provider tokens-per-minute (TPM) limit. If the
provider counts cache reads toward TPM, a peer message can wake the receiving
session and spend another large cache read before it can compact. Send the local
`/compact` command directly to the bound surface. Compaction itself can still
require provider capacity.

## Preview and send

Use a running Ghostty on macOS with scripting enabled and with `tty`, `pid`,
`input text`, and `send key` available in its native AppleScript dictionary.
Run from a separate terminal or controller. Confirm the selection with a dry run,
then repeat the same selectors without `--dry-run`. Replace the illustrative TTY
and prefix below with the intended values.

```bash
python3 "<skill-dir>/scripts/ghostty_session.py" compact \
  --tty /dev/ttys012 --sid 00000000 --dry-run --json

python3 "<skill-dir>/scripts/ghostty_session.py" compact \
  --tty /dev/ttys012 --sid 00000000 --stagger 1.5 --verify-timeout 60 --json
```

- Supply one or more `--tty` values (with or without `/dev/`), one or more
  `--sid` prefixes, or explicit `--all-claude`. Combined selectors form a union.
  Review each dry-run row's tab index, terminal ID, TTY, SID, and current title.
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
Read up to 2 MiB per transcript tail per poll. Claude Code can append large
attachments or metadata after the boundary and push it outside that window.
Read `preTokens`, `postTokens`, `trigger`, and `durationMs` from the boundary's
`compactMetadata`. Absent values appear as JSON null. The script polls the
live resolver's anchored file or the exact SID file in the current project's
default Claude transcript bucket. A missing or unreadable transcript leaves the
send unverified.

Exit 0 means a valid dry run, all sends acknowledged when polling is off, or all
compactions verified when polling is requested. Exit 1 means a partial send,
a changed target, or missing requested verification. Exit 2 means invalid
selection or unavailable preflight evidence. Read the per-target statuses after
a partial batch. An input failure or timeout can follow partial delivery, so
check the target before sending again.

If Ghostty or the host denies scripting, stop input and report the reason. Use
the same route only after the ordinary host authorization is available and a
fresh dry run resolves the intended targets. Keep foreground input, clipboard
automation, and peer messaging out of this workflow.
