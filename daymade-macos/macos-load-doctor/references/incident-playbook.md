# Incident playbook — worked macOS load cases

Historical probe observations and their evidence limits. For current intervention
authorization and recovery acceptance, follow the
[owning Skill's boundary](../SKILL.md#5-act-within-the-boundary).

## Case 1 — historical MCP fan-out with unverified lifecycle attribution

**Symptom (2026-10-07):** hooks on three independent agent fleets start
timing out simultaneously — PreToolUse guards blowing 60-second budgets, a
SessionStart health check exceeding its 8-second deadline, a third-party
hook reporting "protection check deadline exceeded".

**Probe chain:**

```
$ sysctl -n vm.loadavg
{ 243.88 268.10 231.08 }
$ ps -Ao pid,ppid,command         # aggregated by PPID:
  304 children of one pid — an agent runtime's app-server daemon:
  141 copies of an stdio↔SSE MCP proxy, 123 copies of a GUI
  desktop-automation app, 23 computer-use helpers
$ lsof -p <daemon-pid> | grep -c unix
  24                              # matching unix lines, not a live-client census
```

**Evidence boundary:** the recorded probes establish many children and high
load. They do not establish the number of live clients, ended-thread cleanup,
or children retained beyond their intended lifecycle. Do not infer an excess
child count by subtracting socket matches from children, or reuse this case
as a confirmed leak. Lifecycle attribution remains unverified by these probes.

**Remediation (owner-authorized):** the daemon's official
`daemon restart` command. The recorded post-restart load was 22; every
"failing" hook passed untouched. Independent CLI processes and state on disk
do not establish that every task or non-target helper was unaffected. Whether
any desktop-app thread was mid-stream could not be determined: the recorded
client-side log directory was empty. Reduced load supports mitigation;
capability restoration and side effects require their own consumer evidence.

## Case 2 — unthrottled replay loop: a correct test that looks like a fork bomb

**Symptom (2026-07-26):** machine reports "burning hot" mid-test.

**Probe chain:** die temperature 83.1°C; fork rate measured at 1041
processes/second; the security-scan subsystem became the day's top CPU
consumer — because it scans every new binary the loop execs.

**Reasoning:** the test logic was completely correct. To the rest of the
machine, an unthrottled loop and a runaway process are the same thing:
same rate, same heat, same cascading security-scan load. "The load is
deliberate" is not "the load is bounded."

**Remediation:** throttle is a default parameter of any loop that generates
work (batch size, interval, concurrency cap), designed in at writing time,
not retrofitted after the incident. When diagnosing "high rate but owned"
load, ask first "is some test/batch running unthrottled" before treating it
as a runaway.

## Case 3 — a fleet of guards: the irrelevant path's per-call cost

**Symptom:** all-day elevated CPU with no runaway process anywhere; the
security-scan subsystem tops the CPU ranking.

**Reasoning:** repeated irrelevant hook paths paid process-startup overhead.
The fleet was fine; the *irrelevant path's* per-call cost was the bug —
each guard paid full process-startup price even for calls it had nothing to
say about. The fix was structural (zero-fork fast paths before paying for
process startup), not a faster machine.

**Lesson for the census:** when no single process looks guilty, aggregate
*rate*, not just occupancy — a hundred short-lived processes per second
never show up in a single instantaneous snapshot with any weight. Sample
twice a few seconds apart and compare, or sort by etime ascending.

## Case 4 — GUI busy loop: one core for days, invisible to %CPU

**Symptom (2026-10):** persistent warmth; nothing in the instantaneous
top-CPU view looks wrong.

**Probe chain:** cumulative-time census — a settings/menu-bar app with
272 CPU-hours, running at ~96% of one core continuously.

**Reasoning:** a busy loop at 100% of a single core barely moves the load
average on a many-core machine and never spikes %CPU rankings long enough
to be noticed. Only the cumulative-TIME reading finds it. The app's own
periodic-scan feature was the loop; disabling that feature (owner's call)
ended the burn without touching the app.

## Writing the report

Hand the owner a self-contained bundle:

1. The load reading (`vm.loadavg`, all three numbers).
2. The census excerpt that indicts (children-per-parent, cumulative time,
   or instantaneous — whichever fired), with the suspect's full parent
   chain up to something ownable.
3. The classified shape (fan-out / pool / leak candidate / confirmed leak /
   storm / busy loop / cascade) and the
   one-line mechanism.
4. The proposed remediation and its authorized executor.
5. What you could not verify (probe blind spots, like Case 1's empty
   client-side log) — named, not smoothed over.
