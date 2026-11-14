# Shared daemon maintenance and conversation recovery

Use this for an already-authorized replacement or restart of a shared Codex
backend. Routine inspection stays read-only. Reuse passed observations while
their inputs remain unchanged; do not restart a busy service to test this guide.
Account adoption remains in [the OAuth guide](oauth-guide.md#existing-native-owner-recovery).

## Select native updating per component

For an update or automatic-update request, identify each requested component:
desktop application, ordinary CLI, and shared App Server. Bind its actual
installation owner, selected release channel, pin and native updater eligibility
separately. Updating the App Server does not update the invoking CLI or desktop
application. Use each component's supported updater and accept them separately.

An official signed package can still be explicitly pinned. An enabled preference
alone does not prove automatic updating: inspect channel-selection evidence,
updater support, the native updater's process and latest result when available.
Keep a missing result unverified; do not force an upgrade of a busy backend just
to manufacture a successful automatic-update observation.

For [the inspected 0.171.0-alpha.5 daemon](https://github.com/openai/codex/blob/rust-v0.171.0-alpha.5/codex-rs/app-server-daemon/README.md#managed-packages),
the native updater requires the stable `latest` selection, an enabled preference
and managed-binary support. An explicit release or `--from-cli` package remains
pinned, including official prereleases. This is an installation/channel limit,
not evidence that official Codex lacks automatic updates. Recheck the selected
version's implementation before applying this conclusion to another release.

If native eligibility conflicts with the user's selected channel, explain the
specific tradeoff and preserve that channel until the user chooses otherwise.
Acceptance of interruptions authorizes the covered restart, not a new recurring
poller. Enabling an application's own updates uses its native owner; a separate
scheduled updater requires an explicit request or an accepted fallback proposal.

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
3. Confirm the current user's authorization covers this exact service and
   possible task interruption. For an official upgrade whose interruption the
   user accepts, notify affected writers and retain available recovery locations;
   do not wait for every root, child or Goal to become idle or acknowledge a
   global checkpoint. Client reconnection and server recovery are separate
   mechanisms: inspect the selected versions' behavior, then verify the actual
   result rather than assuming either universal recovery or inevitable loss.
4. If interruption is forbidden or not covered by existing authorization,
   coordinate a bounded window through the host's native messaging and installed
   coordination protocol. A concrete unrecoverable external write or explicit
   user exclusion still stops its dependent action; an active turn, child or
   peer request to wait alone does not override the user's accepted interruption.
   Preserve work and keep services and publishers outside the selected backend
   untouched. Do not independently kill their processes or reset/pause Goals.
   Custom enhanced-generation migrations retain their owner's drain and snapshot
   contract; do not import that contract into ordinary official upgrades.
5. Retain the previous complete package and its supported recovery command.
   Keep credentials, hooks, config and conversation history in their existing
   owner. Preserve an operation record with source/target identities and output
   paths before changing the backend.

## Execute through the supported lifecycle

### Assess the target package before requiring patches

Record the invoking client's version/provenance separately from the running
App Server's executable and package provenance. An official backend can serve
a locally patched client; neither component's version or signature establishes
the other's identity. A version mismatch is a compatibility question, not by
itself an upgrade failure.

Judge package provenance from its actual executable, official signature and
complete package manifest, not its directory name. The official installer can
copy signed release bytes into a `local-<digest>-<target>` directory for
`update --from-cli`; that name does not establish a custom build. A standalone
CLI package may omit companions needed by the daemon: verify the complete
official package closure before using it as the update source.

For the requested release channel, inspect the target official package and the
controller's actual compatibility checks against the capabilities the user needs.
Existing support pinned to an older version proves an adapter coverage gap;
it does not prove that the new official backend lacks the required APIs.
Separate same-owner browser OAuth from optional per-request account admission
and preserved-recovery extensions. Verify each requested capability before
requiring a custom build or proposing a port. Missing custom lifecycle flags
alone do not establish that every supported official upgrade route is unsafe;
apply the affected-work and recovery checks in this guide to the chosen route.

Scope each local patch to its demonstrated defect. A patch keeping ordinary
MCP OAuth File-mode logout away from Keyring does not establish a prerequisite
for primary-account switching or quota inspection. Retain it when that storage
contract is required and the target upstream still fails it; otherwise assess
the official package without importing that patch as an Account Manager need.
Do not change the user's release-channel preference as a side effect of this
assessment. Keep an untested target's compatibility explicitly unverified.

For the inspected 0.165/0.166 and 0.169.0-alpha.3 CLI, these commands have different effects:

| Command | Effect |
|---|---|
| `codex app-server daemon update` | Select the official production package, remove a local package pin and restore the production update route; a running backend may restart. |
| `codex app-server daemon update --from-cli` | Copy and pin the invoking complete package, whether official signed release or local build, and restart the backend. Verify provenance separately. |
| `codex app-server daemon restart` | Restart the selected backend; this alone does not return a patched package to official bytes. |

Recheck help and implementation when versions differ. A graceful shutdown can
force termination after its grace period; the command does not prove a busy
backend recovered successfully. Use the authorized official lifecycle for its
accepted interruption; never hand-edit the `current` package link, independently
kill other sessions, or change account/home to make the operation pass.

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
entry separately. Distinguish official release bytes from the production update
route: an explicitly selected official prerelease can remain pinned by
`--from-cli`. Verify production selection/updater state only when returning to
that route is requested; do not remove a prerelease pin merely to make this check
pass. Equal version text can hide different local bytes. Retained source branches
do not activate them.

When an account controller pins the daemon's executable or PID/birth, prepare
its supported replacement binding and reload the actual consumer after the new
owner is available. Verify the original session-bound candidates and account;
writing configuration alone does not establish controller adoption. A controller
version allowlist gap is not proof that the official native API needs a patch.

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

Keep exact operation receipts and retained source branches in the operator's
private archive; this guide carries the reusable procedure.
