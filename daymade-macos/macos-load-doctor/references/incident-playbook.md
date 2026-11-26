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

## Stateful agent and MCP children

Use this section when retained agent/MCP children could contain live state or
when an inventory probe may have created them.

1. **Preserve live state.** Name the state that must survive—REPL variables or
   browser handles—before treating retained processes as waste. Trace tool
   startup, catalog-cache age, and thread residency/unload predicates separately.
   A completed response, inactivity number, or persisted conversation does not
   prove that heap can be discarded or reconstructed.
2. **Compare equivalent paths.** On an owned isolated host, compare genuine
   no-tool work with actually-used tools. Record the exact server identity/key,
   runtime version, and PID birth identity. When cache age could explain a
   difference, distinguish fresh from actually expired behavior; do not turn one
   version's cache interval into a fixed wait for every diagnosis. Fresh success
   does not establish every age or path. Do not change stateful eviction or
   unsubscribe semantics to make process counts drop.
3. **Separate probe births.** Determine whether an inventory/status API reads an
   existing runtime or creates a temporary discovery connection. Attribute
   probe-created processes separately from workload-retained processes. Report
   actual exit evidence or `unknown`; a transient birth alone is not a leak.
   Keep workflow/collector completion distinct from product outcomes.

### Manual cleanup of an owned temporary REPL

For a temporary `node_repl` context owned by the current task, collect required
outputs and confirm its remaining heap is disposable before using the official
context-reset tool. Close self-created handles in that same context first; never
close an old context's bare file-descriptor number from a new context. Preserve
valuable state or uncertain ownership. Do not create a context merely for routine
cleanup, reset another task's context, or terminate its supervisor.

When checking kernel retirement, record the kernel PID and birth identity before
reset and require independent OS readback before reporting its exit. Check parent
and supervisor survival separately. Treat a reset receipt, cleared bindings, or
`Transport closed` as insufficient process-exit evidence. If reset is unavailable,
preserve the unknown outcome and stop without a kill or rebuild fallback.

When independently testing reset and reuse, require a new kernel to execute
successfully with the prior bindings absent, then close its own handles and reset
that test context too. Keep this extra context out of routine cleanup. Scope the
result to the exercised manual `node_repl` path; do not infer CUA behavior,
automatic idle cleanup, whole-tree retirement, or RAM savings. Apply these
ownership and disposal decisions as operator judgments; no automatic policy
enforces them.

### Worked case — Codex 0.163.0 CUA

Scope this observation to a global Codex 0.163.0 runtime with one unchanged CUA
catalog key. A fresh pure-text child created no new CUA pair. After the
version's unchanged default catalog-cache age interval, a zero-tool child
created an unused CUA pair while the original same-generation pair remained.
This establishes extra creation for this version, key, and server, not unbounded
growth or attribution of all Node processes. The ordinary configured REPL was
tested only fresh; ordinary-expiry behavior remains unknown.

Investigate the creation path while preserving live state. Before calling a
repair successful, require a red→green reproduction on the owned isolated host,
an actually-used consumer check, and state and non-target preservation. Exclude
inventory-created births from the workload leak count without assuming those
processes exited.

Read the fixed upstream mechanisms rather than generalizing the case:

- [Catalog-cache TTL](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/codex-mcp/src/tool_catalog_cache.rs#L33-L35)
  and [`published_at` age eligibility](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/codex-mcp/src/tool_catalog_cache.rs#L125-L135).
- [`unloading_target` subscriber/activity predicates](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L59-L65).
- [Session runtime shutdown](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/core/src/session/handlers.rs#L290-L337).
- [Thread+server runtime status versus configuration discovery](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/app-server/src/request_processors/mcp_processor.rs#L400-L451).

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

For a Git-heavy test or validation chain, identify the exact suite and repeated
operation before rerunning it. Reuse unchanged checks through the repository's
CI owner and cover only changed inputs. Reduce repeated repository setup or
proof work at its owning layer: an immutable seed with independent fixture copies
can preserve isolation, while a cache needs explicit content/policy identity.
Verify verdicts and isolation as well as invocation cost; fewer Git calls alone
does not establish a correct or usable result.

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

## Measurement controls

For a confirmed hot preservation or verification script, scope inspection to
the path and operation attributed to its PID. Measure source reads, potential
retained-copy reads and final verification separately. First test whether an
expensive comparison runs after type, mode or size already rules out a match.
A controlled replay can prove wasted work and show its cost on that input.
Attribute the original process's CPU to that work only if a runtime trace or
equivalent evidence from the original run supports it.

Use these controls when snapshot counts or computed CPU rates could change the
diagnosis. Stop measuring once the mechanism and the next authorized action are
decided; these controls do not require a new monitor or a fleet-wide replay.

- **Calibrate CPU units before reporting percentages.** Record the API/version,
  field layout, counter units and time conversion. Compare an owned short CPU
  workload against an independent CPU-time source such as `getrusage`, or compare
  a stable PID's interval with `ps` cumulative `TIME`. In one Apple Silicon probe,
  treating the observed Mach ticks as nanoseconds underestimated CPU by about
  41.7 times. Obtain the current `mach_timebase_info` ratio when the counter is
  Mach time; do not reuse that factor on another API or machine. A disagreement
  invalidates the rate until explained. Retain the original result and label its
  corrected derivative; withdraw dependent claims at their actual consumers.
- **Bind an interval to a process identity.** Check PID and birth identity before
  subtracting counters; exits, permission failures and PID reuse are unknown,
  not zero. Divide by measured monotonic elapsed time. Name the denominator:
  100% of one core differs from 100% of the whole machine. Keep own CPU, live
  child CPU and reaped-child accounting separate to avoid double-counting.
- **Sample short-lived work before it disappears.** When two snapshots leave a
  coverage gap, use a short bounded process-list sample through the native API
  in one already-running observer, rather than spawning `ps` in a tight loop.
  Capture a new PID's parent identity and executable immediately, including its
  parent chain while available. Keep unavailable ownership unknown. Exclude the
  observer's own work, record the actual interval/cadence, and report distinct
  observed births per elapsed second as a lower bound. Even rapid polling misses
  lifetimes shorter than its cadence; only a complete, appropriately authorized
  event trace can support a complete event count. Do not dump argv or environment
  contents to attribute a process.

### A profiler's cleanup must preserve the application

Use this when a diagnostic signal, inspector or injected callback changes a live
process. Prefer an owned isolated process with the same runtime version; exercise
both probe entry and cleanup there before applying an authorized live probe.
Retain the target's PID/birth identity, original business health and recovery
entry. Do not evaluate an untested cleanup callback inside the live service.

A closed debugging port is not proof of successful cleanup: the application may
have crashed. Read the process identity and business endpoint independently after
cleanup, then verify the original activity (for example, a natural collection
round) advances. If the application exited, label the probe failed, preserve the
error and restore the authorized version through its existing service owner.
Report the interruption and verify recovery before continuing performance work.
Peer agreement alone does not authorize interrupting another session's work.

## Duplicate scheduled work

When a scheduled job repeatedly conflicts, retries, or times out, trace who
starts each round and who consumes its result. Use the loaded service
configuration and the receiver's results to match input identity, destination,
and observation times across routes. Two different schedulers, possibly on
different machines, can repeat the same expensive work. A shared executable,
similar inputs, or one conflict response is insufficient to establish that.
Stop taking more resource samples when the next decision can be made from
this evidence.

For example, a hub polls a machine while its timer sends snapshots to the
same source identity. The hub advances the shared sequence between pushes,
and the sender re-collects on conflicts. After an authorized cutover, check
that the redundant timer is inactive and that the receiver publishes a new
snapshot from the retained route with the task coverage users depend on.
Two jobs publishing separate candidates or destinations can both be necessary.

One necessary job can still repeat expensive work internally. First establish
which inputs, outputs, and checks its consumer requires. Attribute the cost of
full exports, Git LFS object hydration, content identity verification, and
scanning separately. Before reusing work, prove that the materialized bytes and
the applicable scan scope, rules, and scanner version still match. Reuse prior
verified byte evidence when it still binds the current input identities and
export settings. Re-export only when that identity cannot otherwise be proved.

Compare a cold run, an unchanged rerun, and a run with one changed input. Use
the same job and scope. Record per-stage time and which inputs were exported,
hydrated, verified, or scanned. Compare reused and fresh scanner outcomes on
small synthetic cases for clean input, a known finding, and a scanner error.
Require the same verdicts and ensure that an error never admits reuse. Verify
that the changed input gets checked and that the consumer still receives the
required result. Keep the verdict comparison off the production tree.

Record desktop recovery separately. Verify the original typing, scrolling,
or window-switching symptom in actual use when available. A fresh snapshot
proves the collection still works. Resource measurements describe the host
at their sample time. Leave desktop recovery unverified without an actual
interaction observation.

For a slow round still in progress, capture the job label, run start time and
target PID with its start time and parent. Read the existing stage timestamps
for lock acquisition, expensive input work and output generation. If they
leave the current stage ambiguous, take one bounded stack or progress sample
of the active worker or child while it still belongs to that run. Use the
receiving artifact and exit status to confirm completion.

For example, a usage-report job can spend time waiting for its shared lock,
refreshing the index or rendering the report. An index child with CPU activity
establishes its stage at the sample time. Only matching stage boundaries
establish the duration. If the run has exited and only total elapsed time was
recorded, keep the stage split unknown and use the existing run records.

## Writing the report

Explain the work in terms the owner can act on. For a process question, use a
compact table such as:

| Process / PID or task group | Product/task and actual operation | Evidence, current state and unknowns |
|---|---|---|

Name the concrete test, scan, export or collection job. A runtime such as Node,
Python or a shared app-server is a host, not the final business attribution.
Use parent/child links to group one operation; keep independent jobs and distinct
repository refs separate. Where deployed code matters, read the effective
executable/source path and version rather than substituting the checkout's HEAD.

Capture PID and birth identity with the targeted command/parent evidence while
the process is alive. For an exited process, consult an already-recorded,
time-matched dossier or process snapshot, checking its capture status and identity.
If none covers it, leave the work unknown; a reused PID or current parent does
not identify the old process. Do not repeat a costly business job merely to
recreate an attribution record. Keep credentials and full environment contents
out of the report.

Mark each row active, observed exited, or unknown at the stated observation
time. For example, a migration-contract test can be sustained compute; an export
launcher, Git and LFS helper can be one task; a collector can run after its page
closes. Those observations establish what ran, not whether it was redundant,
faulty or responsible for lag. When progress is unclear, name the bounded
stack/progress observation needed to decide it.

For a diagnosis or repair report, additionally include the original user-visible
symptom, the relevant load/census window (retain all three `vm.loadavg` values),
the supported workload shape and mechanism (or the exact remaining causal gap),
and the proposed intervention, its authorized executor and recovery path.
Read the actual consumer after intervention: usability and retained
business capability decide recovery; a lower count, merged patch or green test
alone does not. A snapshot-only explanation can end with the table and its
evidence limits; it does not require inventing a fault or remediation.
