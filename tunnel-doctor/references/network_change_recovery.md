# Recovery for disruptive network changes

Apply this contract only after the main Skill's target and task scope allows the maintenance.
It does not authorize a restart or a new background service. Keep ordinary probes read-only.

## Before interruption

Re-read the latest human queued/interrupt correction immediately before applying a previously planned action. Restate the latest goal, exclusions, original state and next required observation; older candidates become invalid when the correction changes scope. Do not quietly restore an optional requirement the user removed, and do not replace a rejected root-cause repair with a relay, alternate port or other bypass.

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

## Network Extension state and stale-listener recovery

Use this section when a proxy/VPN app flaps rapidly, its extension cannot start, or an old listener survives the apparent process exit. For suspected watchdog involvement, first apply `macos-watchdog`'s actor-alignment rule: compare each candidate's actual action log with the same time window's system transitions. A registered job, a running process, or the capability to connect/disconnect does not prove that it is the actor.

### Startup-assertion loop

When Shadowrocket flaps faster than the watchdog cadence, inspect a bounded system-log window before restarting anything:

```bash
/usr/bin/log show --last 2m --style compact \
  --predicate 'process == "neagent" AND eventMessage CONTAINS "Failed to start extension"'
```

`Failed to start extension … could not acquire startup assertion` or `Specified target process … does not exist` identifies a Network Extension/PlugInKit startup retry path. It is not evidence that a watchdog issued a connect/disconnect action. Read the suspected watchdog's own cooldown and action records before assigning blame or restarting neighboring daemons.

### Control state, listener and business path are separate

For an HTTP proxy, preserve these as independent observations:

```bash
scutil --nc list
lsof -nP -iTCP:<port> -sTCP:LISTEN
curl -x http://127.0.0.1:<port> --connect-timeout 5 --max-time 12 \
  -sS -o /dev/null -w 'loopback proxy: %{http_code}\n' https://www.google.com/generate_204
```

- A URL-scheme exit 0 or `scutil` Connected proves only that a request/configuration transition was accepted.
- The listener must exist at the **exact address the consumer uses**. A LAN listener or a successful LAN proxy request does not satisfy `127.0.0.1`.
- Test the DIRECT plane and the user's original application separately; one proxy success does not certify every forwarded plane.
- Do not generalize one Proxy Share observation into a permanent rule such as “on means LAN-only” or “off means no listener”. Record the current app version, setting, listener and request result without claiming causation from the setting alone.

Tailscale has two independent acceptance surfaces: `scutil --nc` describes the network configuration, while `tailscale status` describes its backend. If the configuration is Connected but the CLI reports `Tailscale is stopped`, the backend is not recovered. Use the existing authorized backend restoration action, then require both a running status and a real `tailscale ping`; do not treat Connected as that evidence.

### Exiting process and stale-socket boundary

If `ps` reports the process as exiting (for example `E`/`?Es`) and independent probes find no inspectable threads or Mach/launchd ownership, a successful `kill` return only reports signal delivery. XNU drops signals after `P_LEXIT`; `proc_prepareexit()` places the process on `zombproc` before `proc_exit()` completes reference draining and file-table invalidation. Repeating SIGKILL cannot force that cleanup to finish. `netstat -anv`'s PID field is backed by `so_last_pid`; treat it as the last-accessor clue, not proof of a live FD owner.

Stop same-shape SIGKILL and generic restarts of `pkd`, `neagent`, `nesessionmanager` or other neighboring daemons when their readback shows no effect. **That is not permission to stop investigating.** Change the evidence plane: inventory every socket/reference rather than only the familiar port, inspect current kernel/source semantics, and use an independent diagnostic when needed. Only after those checks may you report that no verified, supported user-space same-port reclamation method remains for the observed state. A reboot is a separately authorized recovery action, not proof that the preceding kill or daemon restart worked.

Do not turn raw RST injection, a loopback relay, `SO_REUSEPORT` rebinding, or deleting/recreating the VPN service into a routine stale-listener repair. Clearing established connections does not prove that a LISTEN socket was released; a bypass is not the rejected root-cause repair.

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
- [XNU `proc_prepareexit()`](https://github.com/apple-oss-distributions/xnu/blob/ac9718fb1af618d5ce8678d0dc6e8a58f252216f/bsd/kern/kern_exit.c#L2267-L2269)
  places the process on `zombproc` and sets `P_REF_DEAD`.
- [XNU `proc_exit()` cleanup](https://github.com/apple-oss-distributions/xnu/blob/ac9718fb1af618d5ce8678d0dc6e8a58f252216f/bsd/kern/kern_exit.c#L2366-L2384)
  later performs reference draining, AIO exit and `fdt_invalidate()`.
- [XNU signal handling after `P_LEXIT`](https://github.com/apple-oss-distributions/xnu/blob/ac9718fb1af618d5ce8678d0dc6e8a58f252216f/bsd/kern/kern_sig.c#L2149-L2156)
  discards the signal with the comment “Don't send signals to a process which has already exited”.
- [Apple `netstat` socket display](https://github.com/apple-oss-distributions/network_cmds/blob/97e27e6244c16d399bfeb254315ddc5828711c56/netstat.tproj/main.c#L867-L889)
  passes `so->so_last_pid` to `proc_name()` and prints that field as the PID.
- [Ansible block error handling](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html#handling-errors-with-blocks)
  documents `rescue`/`always` and the unreachable-host boundary.
