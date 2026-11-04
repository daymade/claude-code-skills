# Integrate the legacy Account Manager terminal port

Use this interface only when an existing account manager explicitly selects a
legacy Ghostty Codex terminal. Keep account selection, provider credentials,
scheduling and the operation journal with that caller. Keep `native_runtime`
and shared-owner adoption with their existing owners. Keep manual batch recovery
in [the manual switch SOP](codex-account-switch.md).

## Resolve readiness through the caller

Read the caller's current description/status and configured terminal command.
Do not treat an aggregate `enabled` flag as proof that legacy-terminal locations,
credential sources and targets are configured. Retain the original operation ID,
target, credential root and checkpoint throughout recovery; do not start another
switch after unknown delivery.

Check the shipped entries without operating a terminal:

```bash
python3 <skill-dir>/scripts/ghostty_session_port.py --help
python3 <skill-dir>/scripts/ghostty_native_host.py --help
```

Require Python 3.10+ and a caller-supplied, explicitly permitted host adapter.
For the bundled macOS host, require Ghostty's native terminal-ID commands, Swift
and existing AX permission. Supply `--runtime-module` as the caller's maintained
kernel-identity module exporting `process_identity(pid)`. Supply its read-only
credential-root consumer inventory through `--consumer-command-json`, the actual
Swift executable through `--swift-executable`, and an anchored actual idle-shell
prompt pattern through `--shell-prompt-regex` when a plain shell is involved.
Do not substitute another installation's credentials, fabricate empty consumer
coverage or loosen a prompt pattern to make readiness pass.

When the checkpoint or adapter is missing, use the owning caller's checkpoint or
configuration step and retry the same operation after independent readback.
An unavailable or denied host channel remains unavailable; do not activate a
window, request permission or select another input channel as a fallback.

## Bind one request and one response

Configure `ghostty_session_port.py --host-command-json '<absolute host argv JSON>'`
as the caller's terminal command. Pass one bounded JSON object on stdin; consume
one JSON object on stdout. Supply the host argv through configuration, never the
operation request. Protocol version 1 accepts `capture`, `exit`, `resume`,
`inspect` and `status`.

Require the original `operation_id`, absolute `state_dir` and `credential_root`,
and `target` fields `sid`, `cwd`, `pid`, `started`, `tty` and `terminal_id`.
Only initial `capture` may discover an unknown terminal ID. Supply its private
`checkpoint_path` under the operation state directory. Require the live owner and
checkpoint producer's kernel identities, ancestry, original TTY/cwd, nonce-bound
window marker, saved work, read-only waiting and absence of in-flight writers.
Reject missing, ambiguous, stale or changed proof with `needs_checkpoint`.

Retain capture's actual bound target, replay-safe `resume_argv`, `manifest_path`
and `manifest_sha256` on later actions. Keep `after_login` fixed to the original
capture mode. Persist the host-binding proof with the fixed manifest rather than
creating another account ledger. Require complete independently verified coverage
of the selected credential root before capture and exit; an unselected consumer
blocks exit.

Use the bundled `ghostty_native_host.py` only under its explicit
`ghostty_targeted_background_v1` permission. Bind initial AX observation through
the unique checkpoint marker, then retain the numeric window ID and selected
surface. Read `ghostty_ax_read.swift` results only for that window. Reject changed
selection, truncation, unknown layouts, multiline drafts and unreadable input.
Keep this targeted channel separate from the manual foreground/idle contract.

## Reconcile input and actual continuation

Insert the complete `/quit`, saved resume command or explicit `/status` control;
read the actual draft back exactly before submitting once. Persist attempts
before input. Treat every existing receipt, partial literal or unknown submit as
reconcile-only; never delete receipts or change their paths to resend. Wait for
independent original-process disappearance before resuming in the same terminal.

Consume `status`, `target`, `evidence` and `reason`, not only process exit.
Distinguish `captured`, `needs_checkpoint`, `blocked`, `input_uncertain`,
`submitted_unverified`, `exited`, `restored_unverified` and `adopted`.
Require `exited` before the provider releases credentials; keep uncertain input
from advancing. Require adoption evidence from the same resumed native
SID/PID/birth/cwd/TTY and actual account card. Do not substitute a credential file
or a separate observer. Leave an unobserved account ID unknown and reject
ambiguous email mappings in the caller.

Require a fresh, physical, independently reread business-result witness under the
original cwd before reporting continuation. Reopening or adoption alone does not
prove that the user's work continued. Send no test prompt, change no Goal state,
and preserve the same operation when that witness is unavailable.

## Run source-maintainer checks

Use the synthetic protocol and native-host regressions from the source checkout:
[port cases](../scripts/test_ghostty_session_port.py) and
[host cases](../scripts/test_ghostty_native_host.py). Run
`python3 -m unittest discover -s <skill-dir>/scripts -p 'test_ghostty*.py'`.
These checks exercise control flow and refusal/recovery boundaries; they do not
prove an operator's live account switch, OS permission or business continuation.
