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
bash scripts/load_census.sh
```

It prints three readings, each answering a different question:

- **By parent (PPID aggregation)** — *who is accumulating children?* One parent
  holding hundreds of children is a leak, and it is self-sustaining: no
  automatic mechanism ever terminates a live process somebody else spawned
  (launchd reaps zombies; it never kills live adoptees), so unless the
  spawner or the user kills them, they accumulate for days. This is the
  signature of per-session/per-thread spawners (MCP servers, per-tab
  helpers) that never reap.
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

Attribution answers three questions: which product/session owns it, is it
supposed to be long-lived (a daemon) or short-lived (a helper that forgot to
die), and who is allowed to stop it.

### 4. Classify the shape before proposing a fix

| Shape | Signature | Typical cause |
|---|---|---|
| **Leak** | child count of one parent grows monotonically over hours | spawner never reaps (per-thread MCP servers, per-session helpers) |
| **Storm** | many processes with seconds-short etimes, high fork rate | unthrottled loop (test replay, batch scan, retry without backoff) |
| **Busy loop** | one process at ~100% with days of cumulative time | app polling without sleep |
| **Cascade** | load high but suspects scattered | a system service amplifying each new process (security scans, file-sync, Spotlight) |

The fix is different for each: a leak wants the spawner fixed or restarted, a
storm wants throttling at the loop, a busy loop wants the app relaunched or its
scan disabled, a cascade wants fewer new processes, not faster ones.

### 5. Act within the boundary

On a shared machine, **diagnosis is read-only; remediation has an owner**.

- Never terminate another session's, agent's or user's processes. A "service
  restart" whose side effect is killing the daemon's children is the same
  action in a nicer wrapper — it counts as terminating them.
- What you may do yourself: throttle your own loops, renice your own
  processes, stop your own background jobs.
- Everything else is a report: load reading, census output, the attributed
  parent chain, the classified shape, and the proposed remediation — handed to
  the owner (the user, or the session that owns the parent). **Once the owner
  explicitly authorizes the remediation, execute it** — an authorized action
  handed back as another report is the opposite boundary violation. Verify
  afterward as below.
- After any remediation (yours or the owner's), **read back**: re-run
  `sysctl -n vm.loadavg` and the census. A command receipt is not recovery;
  the load and the child count are.

## Common leak patterns

Short table in this file for the shapes seen repeatedly; worked cases with
real probe outputs and the reasoning chain live in
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
