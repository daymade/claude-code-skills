---
name: macos-load-doctor
description: >-
  Diagnoses macOS system-level slowness, heat and fleet-wide timeouts: high load
  average, leaked per-session child processes (MCP servers, helpers), fork
  storms, busy loops. Use when the Mac feels slow or hot, fans spin up, or
  everything times out at once (电脑发烫/卡顿/负载高/全部超时). Not for single-app
  bugs, network slowness (use tunnel-doctor), launchd watchdog design (use
  macos-watchdog), or disk-full (use macos-cleaner).
---

# macOS Load Doctor

Find what is making the Mac slow or hot, attribute it to an owner, and act
within the shared-machine boundary. The skill's job is a correct, evidence-backed
attribution — not process cleanup.

## The one rule that orders everything else

**A fleet-wide symptom is an environment problem until proven otherwise.** When
independent apps, hooks or agents all start timing out or crawling at the same
time, none of them is the suspect — something is starving them all. Check the
machine first; debug individuals only after the machine reads clean.

## Triage (READ-DO, in order)

### 1. Load first, always

```bash
sysctl -n vm.loadavg; uptime
```

Expected: three numbers, e.g. `{ 3.12 4.01 5.20 }`. Read against the core
count, not an absolute: single digits are calm on a modern Mac; tens are busy;
**hundreds mean the run queue is many times oversubscribed and everything on
the machine is a victim** — hooks time out, keystrokes lag, pushes stall. A
load in the hundreds with no obvious culprit in the CPU column usually means
hundreds of small processes, not one big one.

### 2. Process census — run the bundled script

```bash
LOAD_DOCTOR_DIR='<absolute directory containing this SKILL.md>'
bash "$LOAD_DOCTOR_DIR/scripts/load_census.sh"
```

Resolve that directory from the loaded Skill entry; the caller's project directory
is not the Skill directory. The census readings answer different questions:

- **By parent (PPID aggregation)** — *who owns many children?* A large count
  identifies fan-out and resource overhead, not a proven leak. Compare births,
  exits and counts across a bounded window with the owner's active workload and
  intended lifecycle. A stable pool or helpers for active sessions can be valid;
  a leak claim needs evidence that children outlive the work they serve or that
  retained counts grow after equivalent work completes. Do not terminate sessions
  to manufacture that evidence; use existing lifecycle records or your own test.
- **By cumulative CPU time** — *who has been burning for hours?* A GUI app or
  helper with days of CPU time at ~100% is a busy loop, not a spike.
- **By instantaneous %CPU** — *who is burning right now?* Catches the active
  storm that the cumulative view dilutes.

### 3. Attribute the owner

Trace the parent chain of the suspect until it ends at something ownable:

```bash
ps -o pid,ppid,etime,command -p <pid>     # then repeat on its PPID
launchctl list | awk '$2 != "-" && $2 != "0"'   # jobs with abnormal last-exit codes
```

The `launchctl` filter also prints its header line, and many system daemons
sit at status `-9` (SIGKILL) permanently — that is routine noise, not a crash
loop. The respawn-loop signal is a job whose PID keeps *changing* between
runs, not any single status value.

Attribution determines which product/session owns it, whether it is
supposed to be long-lived (a daemon) or short-lived (a helper that forgot to
die), and who is allowed to stop it.

### 4. Classify the shape before proposing a fix

| Shape | Signature | Typical cause |
|---|---|---|
| **Leak candidate** | retained child count grows after comparable work finishes, or helpers outlive their documented lifecycle | missing cleanup; confirm workload and lifecycle before calling it a leak |
| **Fan-out / pool** | many children correlate with active sessions or a stable configured pool | per-thread ownership can be expensive without being a leak |
| **Storm** | many processes with seconds-short etimes, high fork rate | unthrottled loop (test replay, batch scan, retry without backoff) |
| **Busy loop** | one process at ~100% with days of cumulative time | app polling without sleep |
| **Cascade** | load high but suspects scattered | a system service amplifying each new process (security scans, file-sync, Spotlight) |

The fix is different for each: a confirmed leak wants the spawner fixed or restarted, a
storm wants throttling at the loop, a busy loop wants the app relaunched or its
scan disabled, a cascade wants fewer new processes, not faster ones.

### 5. Act within the boundary

On a shared machine, **diagnosis is read-only; remediation has an owner**.

- Never terminate another session's, agent's or user's processes. A "service
  restart" whose side effect is killing the daemon's children is the same
  action in a nicer wrapper — it counts as terminating them.
- What you may do yourself: throttle your own loops, renice your own
  processes, stop your own background jobs.
- Terminating or restarting another session's, agent's, service's or user's
  process requires the **current user's explicit authorization**. Coordinate
  ownership with peers, but their agreement does not grant that authorization.
  Pause only the intervention that needs approval; continue the authorized
  read-only investigation that does not depend on it.
- For a named alert, reconstruct its recorded window, measurement units and
  trigger calculation before attributing the cause. Another process being
  hotter does not explain why this alert fired. Keep alert validity and the
  machine's actual workload as separate conclusions.
- For a diagnosis or remediation request, progress reports do not end the task.
  Do not send a closing answer with the cause unknown while an authorized probe
  can still distinguish the competing explanations. Diagnosis completes when a
  specific mechanism explains the requested symptom or alert and has evidence
  that discriminates those explanations; an approved repair continues through
  independent readback. A standalone snapshot-only request can end after that
  snapshot; a status question during active diagnosis gets a progress update
  while investigation continues. An explicit pause is honored. If an
  external condition blocks all remaining probes, name it and the missing
  evidence as unfinished, rather than claiming completion.
- Once the current user authorizes an intervention, execute and verify it;
  handing an already authorized action back as another report is not completion.
- After any remediation (yours or the owner's), **read back**: re-run
  `sysctl -n vm.loadavg` and the census, then exercise the user's original
  capability through its actual consumer. Disabling a service can relieve load
  while removing that capability: report mitigation until it works again.
  Before a configuration reload, establish whether its scope includes other
  threads/services. Compare target and non-target helpers before/after; an
  unchanged master PID does not prove that other helpers were unaffected.

## Memory evidence

For a memory complaint, measure pressure and activity alongside process counts:

```bash
sysctl vm.swapusage
vm_stat -c 4 2
ps -axo pid,ppid,rss,command
```

Read the page size printed by `vm_stat`; its first row is cumulative and later
rows show interval activity. Existing swap allocation does not establish current
thrashing: inspect swap-in/out activity over the sampled window and report that
window. RSS totals can count shared resident pages repeatedly and are not unique
physical memory. For a suspect, use `vmmap -summary <pid>` to distinguish its
reported physical footprint from RSS; retain separately reported GPU/IOKit
allocations instead of silently adding unlike counters. A large allocation or
compressed-memory snapshot alone does not identify retained objects or a leak.

[Apple's memory guide](https://support.apple.com/guide/activity-monitor/view-memory-usage-actmntr1004/mac)
defines memory pressure using free memory, swap rate, wired memory and cached
files. The executing agent interprets those signals and the observed workload;
the census does not mechanically classify a leak.

## Common leak patterns

Worked cases with real probe outputs live in
[references/incident-playbook.md](references/incident-playbook.md) — read it
when the census shows something you have not seen before, or when you need a
precedent for the report you are about to write.

- **Per-thread MCP spawners**: an agent runtime starts the full configured MCP
  set per conversation thread and never reaps them; hundreds of proxy/helper
  processes accumulate under one daemon over days. GUI-flavored MCP servers
  additionally hammer WindowServer.
- **Unthrottled batch loops**: a replay/fuzz/migration loop with no rate limit
  is indistinguishable from a fork bomb to the rest of the machine — same
  rate, same heat, same cascading security-scan load.
- **GUI busy loops**: a menu-bar or settings app polling without sleep — one
  core at 100% for days, invisible until cumulative-time census.
- **Respawn loops**: a launchd job crashing and restarting every few seconds —
  `launchctl list` shows a non-zero last-exit code and a PID that keeps
  changing.

## Troubleshooting

- **Load is high but every reading looks normal**: the suspects are short-lived
  — measure the fork rate directly: two `ps -Ao pid=` snapshots a few seconds
  apart, count the PIDs that appear only in the second
  (`comm -13 <(sort old.txt) <(sort new.txt) | wc -l`, divided by the interval).
  Dozens per second is a storm; a few is normal churn.
- **The obvious big-CPU process is innocent**: WindowServer, a terminal, or a
  screen-sharing client at high CPU is often *downstream* of the real cause
  (hundreds of GUI app copies each needing window service). Keep tracing.
- **Everything points at a system service**: that is the cascade shape — the
  fix is reducing the rate of new work reaching it, not the service itself.
