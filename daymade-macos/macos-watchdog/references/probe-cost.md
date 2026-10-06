---
name: periodic-observation-cost
description: Check cold, warm and incremental work before deploying or integrating a periodic health observer.
---

# Periodic observation cost and acceptance

Apply when creating, changing or integrating a recurring health observer. Keep
business backfills and historical audits under their own execution contracts;
do not make them an implicit prerequisite of each short health observation.

## Choose frequency from the business window

Before choosing a cadence, name the captured state, tolerated staleness or
missed-change window, the lifetime of relevant changes, and each round's reads
and cost. Compare reasonable intervals by nominal capture delay and scheduled
checks over the same period; include collection, scheduling, sleep and failure
delays. Use probe cost to choose among cadences that meet the business window.

An explicit user interval or applicable domain SLA takes precedence. Without a
user SLO, state a reversible default, its basis and any unverified lifecycle or
coverage assumptions in the current task's plan or result. Existing authorization
governs the change; reversible parameters need no separate approval gate.
No workflow's default interval is a global minimum: short-lived states may require faster capture.

## Verify observation cost and delivery

1. Fix the business predicate before optimizing. Preserve owner intent, original
   event time, per-source failures and the distinction between observer failure
   and business failure. Compare old and new verdicts on the same sealed cohort.
2. Inspect every read and query, including reused helpers. Declare the data
   scope, frequency, completion deadline and how work grows with retained history.
   Cache parsed current state durably or use the owner's qualified projection;
   caching raw bytes while decoding all history each cycle still repeats the work.
   Do not use projection refresh time as proof of new business work.
3. Separate cold initialization/rebuild, unchanged warm reads, new-event reads
   and integrity audits. Verify required indexes for lookups and deletions during
   ingestion as well as current-state queries. Declare remaining filename
   enumeration, metadata audits and rebuild cost rather than claiming constant
   work for the whole observer. Preserve explicit invalidation/recovery behavior.
4. Bound external reads with a supervisor the scanned code cannot swallow.
   On timeout, partial input, lock contention or corrupt state, report observation
   failure/unknown; do not restart business work or clear prior failures from
   missing evidence. Judge event age at observation completion. Fit nested polls
   and waits inside the original recovery deadline.
5. Measure actual work with small and larger retained histories: JSON parses,
   bytes opened or SQL execution steps, not only wall-clock time or self-reported
   cache counters. Exercise cold, warm, delta and failure paths. Reintroduce full
   replay and an unindexed query while preserving verdicts: the cost regression
   must reject both. Bind automated checks to the exact source being committed;
   a healthy installed twin cannot certify a bad staged version.
6. Run the installed launchd job and independently read its completed report,
   business timestamp, error exit and duration. Interactive speed or launchctl
   registration alone does not pass. Respect other active workloads when a test
   would pause the host. Treat simulated interruption and real sleep/wake
   continuity as separate acceptance evidence.

Execute these checks as the deploying operator. Use workload-specific counters
and regression tests; this Skill supplies no universal scan detector. Keep
acceptance incomplete where the observations cannot be obtained.

Stop when equivalent business verdicts, growth/failure controls and the native
completed round are established. Keep power savings and improved delivery
reliability unknown until those outcomes have their own measurements.

Sources: Google's [monitoring guidance](https://sre.google/sre-book/monitoring-distributed-systems/)
separates simple critical monitoring from long-horizon analysis; SQLite's
[query planner](https://www.sqlite.org/queryplanner.html) explains indexed lookup
and full scans. Use executed workload evidence to set the local budget.
