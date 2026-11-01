# Shared daemon maintenance and conversation recovery

Use this for an already-authorized replacement or restart of a shared Codex
backend. Routine inspection stays read-only. Reuse passed observations while
their inputs remain unchanged; do not restart a busy service to test this guide.
Account adoption remains in [the OAuth guide](oauth-guide.md#existing-native-owner-recovery).

## Bind the service and preserve affected work

1. Resolve the ordinary CLI through its owning shell. Inspect that exact
   executable's `app-server daemon version`, `update --help` and `restart --help`.
   Bind the selected `CODEX_HOME`, control endpoint, daemon PID/birth, actual
   executable/hash and selected package. CLI and backend versions can differ.
   An explicit managed launcher may select a third package; do not silently
   replace it or infer its adoption from the ordinary entry.
2. Discover the affected sessions through the current host's native tools.
   Preserve SID, cwd, latest turn, pending input, in-flight command handles and
   work/recovery locations. Check discovery pagination and truncation; report
   uncovered sessions instead of claiming the inventory is complete.
3. Coordinate a maintenance window with affected writers. Use native messaging
   where it covers the target, with the installed coordination protocol when
   required. Wait for critical commits, installs and publications to finish
   naturally; verify their terminal state or preserved recovery path. A peer
   acknowledgement is coordination, not permission to terminate its processes.
   Keep services and publishers outside the selected backend untouched.
4. Confirm the current user's authorization covers this exact service and
   possible task interruption. An already-authorized version switch does not
   require another ceremonial approval. A refusal or an unsafe in-flight write
   stops the dependent switch; continue independent authorized preparation.
5. Retain the previous complete package and its supported recovery command.
   Keep credentials, hooks, config and conversation history in their existing
   owner. Preserve an operation record with source/target identities and output
   paths before changing the backend.

## Execute through the supported lifecycle

For the inspected 0.165/0.166 CLI, these commands have different effects:

| Command | Effect |
|---|---|
| `codex app-server daemon update` | Select the official production package, remove a local package pin and restore the production update route; a running backend may restart. |
| `codex app-server daemon update --from-cli` | Copy and pin the invoking CLI package; this may select a local build and restart the backend. |
| `codex app-server daemon restart` | Restart the selected backend; this alone does not return a patched package to official bytes. |

Recheck help and implementation when versions differ. A graceful shutdown can
force termination after its grace period; the command does not prove a busy
backend is safe to replace. Never hand-edit the `current` package link, kill
other sessions, or change account/home to make the operation pass.

Run the chosen command once through the bound entry and context. Persist
stdout, stderr and terminal exit status outside the backend being replaced.
When the caller itself uses that backend, use a task-owned detached process
with a durable result file so its receipt survives disconnection. Preserve
the authorized execution context; detachment does not transfer permissions.
On timeout, disconnect or missing result, reconcile this same operation,
selection and process before retrying. Do not launch a second update to find
out whether the first one succeeded.

## Verify adoption, then each requested continuation

Read back the selected package, provenance/hash, actual replacement process and
backend version through the original endpoint. Check the ordinary login-shell
entry separately. For a return to official updates, verify the production
selection marker and updater state as well as the version; equal version text
can hide different local bytes. Retained source branches do not activate them.

For each session whose continuation is claimed, inspect its original SID/cwd
and turn boundary. Require a new message or completed tool execution after the
replacement; `active`, a loaded thread or an unchanged SID alone is not enough.
If the host already restored that same conversation into the current context,
continue from it and reconcile current state before repeating a write. Do not
send another "continue" to a running, completed or user-paused task.

When automatic recovery is missing, keep it unverified and use the separately
authorized [original-session continuation route](oauth-guide.md#continue-the-bound-original-sessions).
Do not edit rollout/database records or create replacement Goals. Check Goal
status separately: a recovered turn does not establish that a previously
blocked Goal regained automatic continuation.

The observed 0.165-to-official-0.166 replacement restored interrupted
conversations through the native `daemon_recovery` path and produced new
messages/tools under their original SIDs. This is a verified build-specific
result, not a guarantee of uninterrupted shell commands, universal recovery,
or completion of those sessions' business tasks. Keep exact incident receipts
and source branches in the operator's private archive; this guide carries
the reusable procedure.
