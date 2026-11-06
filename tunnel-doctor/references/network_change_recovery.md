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

## Task-owned temporary host-route cleanup

Use this only for a temporary **host route created and recorded by the current task**, within the
maintenance authorization above. This synthetic recipe does not authorize a route change. Do not
apply it to a default route or a network route such as `100.64.0.0/10`.

At creation, record the address family, exact destination/prefix, gateway, interface, the raw
pre-change route table, and the original business request. The example below deliberately uses
only synthetic values: IPv4 host `192.0.2.10/32`, gateway `192.0.2.1`, and interface `en99`.

Before cleanup, capture unedited stdout, stderr and exit status for each read. Keep
both address-family tables, even when the task-owned host route is IPv4:

```bash
route -n get -inet 192.0.2.10
netstat -rn -f inet
netstat -rn -f inet6
```

Require every read to exit 0, produce the expected route output, and have no route failure on
stderr. A nonzero exit, empty output, missing parsed field, or route error means the cleanup state
is unknown: issue no deletion. Treat the route as this task's deletion candidate only when the
selection output and route table agree with the creation record on **all** of:

- family `inet` and exact destination/prefix `192.0.2.10/32`;
- the `HOST` route flag, not a default or broader network route;
- gateway `192.0.2.1` and interface `en99`.

If the exact host route is absent, `route get` selects a fallback/default or broader route, any
identity field is missing, or gateway/interface/family/destination changed, **do not delete**.
A fallback answer describes the route currently selected; it is not the task-owned host route.
Recheck the complete identity immediately before invoking the already-authorized platform route
mechanism. The harmless synthetic form is:

```bash
sudo route -n delete -inet -host 192.0.2.10 192.0.2.1
```

Afterward, save the same unedited route-get/table stdout, stderr and exit status as the exact post
snapshot. Confirm that `192.0.2.10/32` with the recorded gateway and interface is absent, and that
the pre-existing default and network routes in **both IPv4 and IPv6** remain present with their
original family, destination/prefix, gateway and interface. Missing or unreadable family snapshots
leave preservation unverified. If only an IPv6 default disappears while the IPv4 table remains
unchanged, verification still fails; do not report cleanup as successful. If
`route get` now selects a default or another fallback, do not claim that the kernel fallback
deleted the default route; verify the default separately against the pre/post snapshots.

Finish by replaying the exact original business request on its normal path with its original
success/completeness contract. Route absence alone does not prove business recovery. A failed or
ambiguous post-read leaves cleanup unverified; preserve the failure and use the already-armed
bounded restoration path rather than deleting another route.

## Verify and finish

Read actual service state and test the specific repaired path plus the user's original network
use, such as an existing proxy-dependent application connection. A URL-scheme command returning
zero proves only that the request was accepted. Keep an untested application path `not_checked`.
An OnDemand VPN can reconnect before a polling loop observes `Disconnected`. A wait timeout does not prove the disruptive request had no effect. Preserve that timeout as the operation result, then inspect connection lifecycle counters/timestamps or logs and repeat the original failing request on its normal domain path. `Connected` alone cannot prove a reconnect occurred; a successful `--resolve` workaround alone cannot prove the repaired domain path works. Do not issue another reconnect just to make the status waiter green when lifecycle evidence and the requested path already show recovery.

Include a harmless recovery fixture where the observed state stays `Connected` while the connection lifecycle advances, and another where it stays `Connected` without lifecycle change and the business request still fails. The former must not cause a blind extra disconnect; the latter must remain unverified. Keep the existing bounded restoration path for genuinely disconnected or failed states.

Retire only the exact task-owned recovery job after successful readback, within the original
maintenance scope. Stop when the requested result and necessary verification are complete.
If the user withdraws access, do not reconnect for cleanup or proof of stopping; disclose any
already-armed restoration action and use existing records to coordinate the stop.

## Source semantics

- [Python cleanup actions](https://docs.python.org/3/tutorial/errors.html#defining-clean-up-actions)
  describes `finally` execution while an exception propagates.
- [Ansible block error handling](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html#handling-errors-with-blocks)
  documents `rescue`/`always` and the unreachable-host boundary.
