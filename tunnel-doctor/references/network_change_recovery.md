# Recovery for disruptive network changes

Apply this contract only after the main Skill's target and task scope allows the maintenance.
It does not authorize a restart or a new background service. Keep ordinary probes read-only.

## Before interruption

1. Identify the exact VPN/service, application process if required, current connection state,
   configuration owner, and user path that must keep working. Record the original state.
   An originally disconnected VPN must not be connected as incidental cleanup.
2. Validate every known read-only prerequisite before stopping anything: tools and privileges,
   database/schema expectations, row selectors, writable backup destination, and the proposed
   configuration. Preserve a verified backup. If any prerequisite fails, leave the network as is.
   Do not defer an expected-row assertion until after killing the application.
3. Select an exact bounded restore action and a way to verify it. Restore connection state on
   failure; roll back changed configuration when required by the maintenance plan. A reconnect
   to broken configuration does not count as recovery. Do not overwrite concurrent user changes.
4. Arm recovery before attempting the first stop/change, since that operation may partly succeed
   before reporting an error. Keep the operation error visible even if restoration succeeds.

## Execute and recover

Use the existing execution framework's cleanup facility: Python `try/finally`, a shell cleanup
trap, or Ansible `block` with `rescue`/`always`. Put the first disruptive action inside the protected
region. Recover on an exception, assertion failure, command failure, or supported cancellation;
never use a successful final statement as the only restart path. Cleanup itself needs a timeout,
error reporting, and independent readback, rather than an unlimited retry loop.

For a change that can sever SSH, arrange a finite target-side restoration job before interruption
and confirm it was armed. Its execution must survive loss of the controlling SSH session. Use the
existing platform/framework mechanism; do not install a periodic watchdog for a one-off repair.
Python `finally` cannot handle process death or power loss, and Ansible rescue/always does not run
for an unreachable host. If no independent recovery path can be prepared, stop before the change.
This condition also applies when a script is launched with `nohup`; detachment is not rollback.

Exercise the operation's failure path with harmless substitutes on a designated test machine or
local fixture before a live interruption. Include these observations:

- A failed prerequisite produces zero stop/change calls.
- An interruption that partly succeeds and then raises still attempts bounded restoration.
- A failure after the stop preserves the original error and restores the prior connection state.
- A failed restoration produces a visible failure, not a success report or endless retry.
- Normal success leaves the intended final connection state and no armed restoration job that
  could later undo the accepted result. An originally disconnected service stays disconnected
  unless starting it was explicitly part of the maintenance.

Never exercise these failures on a colleague's working computer merely to test the recovery code.

## Verify and finish

Read actual service state and test the specific repaired path plus the user's original network
use, such as an existing proxy-dependent application connection. A URL-scheme command returning
zero proves only that the request was accepted. Keep an untested application path `not_checked`.
Retire only the exact task-owned recovery job after successful readback, within the original
maintenance scope. Stop when the requested result and necessary verification are complete.
If the user withdraws access, do not reconnect for cleanup or proof of stopping; disclose any
already-armed restoration action and use existing records to coordinate the stop.

## Source semantics

- [Python cleanup actions](https://docs.python.org/3/tutorial/errors.html#defining-clean-up-actions)
  describes `finally` execution while an exception propagates.
- [Ansible block error handling](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html#handling-errors-with-blocks)
  documents `rescue`/`always` and the unreachable-host boundary.
