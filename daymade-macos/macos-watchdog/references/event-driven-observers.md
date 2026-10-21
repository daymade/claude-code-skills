---
name: event-driven-observers
description: >-
  Select, deploy and accept an event-driven observer when a usable event source
  exists for the source of truth; periodic polling is the audited fallback only.
---

# Event-driven observers

Apply this SOP to configuration convergence triggered by changes to canonical
inputs or managed outputs. Use [native readback](native-job-readback.md) for
loaded configuration and [probe cost](probe-cost.md) for periodic fallback.
The deploying agent executes these steps; the readback helper checks native
configuration only. It does not enforce the distributed workflow described here.

## Select event vs periodic

1. Inventory the event sources that exist for the source of truth: macOS
   FSEvents, launchd `WatchPaths`, Linux per-directory watchers
   (inotify-style), or change notifications from the owning application.
2. Choose event-driven when at least one usable event source exists for that
   source of truth. A usable source fires on the change you care about, can be
   verified with a real write, and can be read back after installation.
3. Fall back to periodic ONLY when no usable event source exists, or when an
   explicit bounded audit requires a sweep. The probe-cost contract in
   [probe-cost contract](probe-cost.md) still applies to that fallback in full.
4. Never assert a periodic interval as the default event transport, and never
   let a timer masquerade as event transport. A job that wakes on
   `StartInterval` to re-read the source is polling; name it polling.

## Source events vs worker drift

An event on the SOURCE of truth is a different signal from the worker's own
drift. Design the observer to tell them apart:

- Source event → converge the managed output to the source's current content.
- Worker drift (managed output diverges from the source with no corresponding
  source event) → compare and repair only managed output; retain the same
  source generation and leave unrelated fields alone.
- Observe the managed destinations as well as source inputs. After writing an
  output, compare its managed content before acting on its echo event; an
  already-correct output requires no further write or acknowledgement.
- Exercise both paths separately in acceptance (§ Acceptance SOP); a worker
  that only handles source events will silently leave its own drift in place.

## Declare the source SSOT and managed scope

Before installing any watch, declare in the owning configuration:

1. The authoritative host/repository or service and its exact input scope.
   Reuse its existing manifest; resolve each managed field to one canonical
   input rather than letting workers become competing writers.
2. Managed scope: the exact downstream paths and fields the worker may write.
3. Machine-local exclusions: the paths and state the worker must never manage
   (user-owned files, other jobs' outputs, local caches, machine-specific
   overrides). An observer without a declared SSOT, scope and exclusion list
   cannot pass acceptance.

## Native filesystem notifications

### macOS: FSEvents and launchd WatchPaths

- For a short-lived launchd worker, consider `WatchPaths` only within its
  loss/race limits below; read [plist keys](launchd-plist-reference.md).
- For a resident observer, use a documented FSEvents or filesystem-watcher API.
  Establish subscriptions before the initial reconcile, retain events arriving
  during that reconcile, then drain the dirty state before becoming idle.
  Handle invalidation, dropped-event/overflow signals and directory replacement
  by restoring the affected subscriptions and reconciling their managed scope.

### Linux: per-directory watchers (inotify-style)

- Install one watch per directory that can carry a relevant change; inotify
  watches inodes, so a per-file watch silently dies when the file is replaced.
- Preserve each valid subscription; do not tear it down after every ordinary
  event. Re-arm when the API reports invalidation or the watched directory is
  replaced. On overflow or an incomplete watch set, mark the affected scope
  dirty, restore coverage and reconcile before reporting healthy.

### Atomic replacement and repeated-write verification (both platforms)

- ATOMIC REPLACEMENT: well-behaved writers replace files (write temp, then
  rename). A replace breaks naive per-file watches — the watched inode is
  gone. Watch the PARENT DIRECTORY, filter relevant entries, and restore the
  subscription if that parent is itself replaced. Cover managed output parents
  too; a source-only watch does not detect destination drift.
- Repeated-write verification: after installing the watch, write the source
  twice in a row and confirm both writes produce events. A watch that catches
  only the first write is silently disarmed; treat that as a failed install.

## Event-handling discipline

Implement in the observer and convergence worker:

1. Debounce: collapse a burst of events on the same source into one
   convergence run after a short quiet window.
2. Coalescing: expect the OS to coalesce events. Treat every event as "re-read
   the source", never as a complete delta of what changed.
3. Single-flight execution: at most one convergence run in flight. An event
   arriving mid-run marks a newer generation and triggers exactly one
   follow-up run, not a parallel one.
4. Last-generation ACK: acknowledge only the generation actually converged. An
   older run's completion must never ACK a newer observed state.
5. Durable offline catch-up: persist the latest desired generation and each
   target's acknowledgement; keep an unacknowledged target pending across
   failure or downtime. Reconcile canonical content at startup even if the
   producer was also offline and could not queue the original event.
6. Reconnect/startup reconcile WITHOUT recurring scans: on (re)start or
   (re)connect, reconcile the managed scope and acknowledge only the state
   actually delivered. Keep newer or failed work pending. Use the transport's
   real reconnect notification or a bounded retry for pending failures; do not
   keep scanning unchanged sources while healthy and idle.

## Events invalidate knowledge; they do not deliver truth

- On a source event, read canonical content/fingerprint; create a new source
  generation only for an effective source change. On a destination event,
  compare managed output with that canonical state even when the source
  fingerprint is unchanged. Suppress echoes only after proving output agrees.
- Avoid idle full scans: the read-on-event is a targeted read of the declared
  source, not a tree sweep.
- Do not promise that every file event carries a complete delta, or that
  startup/reconnect reconciliation detects a silent loss during an otherwise
  uninterrupted session. Where that would violate the delivery requirement,
  use the producer's durable change feed/IPC, or an API with detectable
  loss/replay plus recovery. Mark an unobservable loss boundary explicitly;
  do not claim lossless delivery from filesystem notifications alone.

## WatchPaths caveats (launchd)

- Treat `WatchPaths` as a launch hint. It can start a short-lived job when a
  path changes; it supplies neither an exactly-once queue nor an event payload. The
  job must still read the source on each start to learn what changed.
- Do not assume a change during execution guarantees another run. Keep work
  short, and select durable demand signalling or a resident observer when
  concurrent changes must survive the exit boundary.
- Parent-directory watching, atomic-replacement, coalescing/missed-event and
  business-reconcile caveats all apply (§ Native filesystem notifications,
  § Events invalidate knowledge).
- A persistent watcher process needs its own supervision policy (an explicit
  `KeepAlive` policy and crash handling). `WatchPaths` alone supervises
  nothing; do not describe a WatchPaths-triggered job as a resident watcher.

## Failure and unknown paths

- Every event-transport claim needs evidence: an installed watch, an observed
  event from a real write, and a verified convergence. Absence of evidence is
  unknown, not healthy.
- Unknown stays unknown: when the watch cannot be verified (unsupported
  platform API, unreadable native scheduling state, ambiguous readback),
  report unknown — never infer event delivery from the job merely being
  loaded.
- Loaded scheduling state is read back through the bundled helper; its
  scheduling-flag contract (including the rule that unknown or unsupported
  native format is never success) is defined in
  [native readback](native-job-readback.md).

## Deployment SOP

1. Validate the plist with `plutil -lint <plist>`, then read the effective
   contents back with `plutil -p <plist>` to catch type errors before loading.
2. Before replacing an existing job, verify EXACT ownership: both the label
   and the plist path belong to the job you intend to replace.
3. Inspect the exact service with `launchctl print gui/$(id -u)/<label>` and
   the worker's own task/queue state. A missing PID alone does not prove there
   is no pending work. Coordinate or defer replacement if ownership, active
   work or pending intent is unknown; preserve pending intent for recovery.
4. Verify a recovery path: keep the previous plist and be able to
   `bootout`/`bootstrap` back to it.
5. Never automatically kill other jobs or sessions.
6. For an idle owned job, use `launchctl kickstart gui/$(id -u)/<label>`
   WITHOUT `-k` to request one run. There is no universal restart mandate;
   `bootout`/`bootstrap` re-loads after a plist edit, it is not an event test.

### Wait for an authorized unload before replacement

The deploying operator or owning installer performs this sequence after the
ownership, idle-work, pending-intent and rollback checks above:

1. Issue one `bootout` for the exact inspected service. Preserve the previous
   plist, frozen inputs and pending state. A successful command return alone
   does not establish that the registration has disappeared.
2. Use the owner's read-only unload waiter when available. Otherwise observe
   `/bin/launchctl print <exact-domain/service>` with an explicit finite deadline
   and bounded command timeouts. Exit zero means the job remains loaded; wait
   within that deadline. Accept absence only from a successful observation of
   the command's recognized service-not-found result for that exact target.
3. Stop on timeout, an unrecognized error or an incomplete observation; report
   unload pending or unknown and retain recovery inputs. Do not issue another
   `bootout`, signal a process, use `kickstart -k`, or bootstrap to force progress.
   Resume from a fresh read of the same target when the missing evidence exists.
4. Recheck the owning service's old-process/listener exit requirements, then
   install the already inspected inputs. Registration absence proves neither
   process exit nor successful replacement. Follow native readback and the
   completed business-round acceptance below for the new job.

Keep the installer's loaded-job refusal. This sequence observes an already
authorized transition; it grants no authority to stop a busy or unrelated job.

## Acceptance SOP

Use authorized, reversible inputs or task-owned fixtures. Preserve the original
content and restore it with downstream readback after the acceptance change.

Require ALL of the following before declaring done:

1. For a macOS GUI launchd job, follow [native readback](native-job-readback.md)
   against the exact expected plist. For Linux or another supervisor, inspect
   its actual loaded trigger and arguments through that supervisor's native
   interface; the bundled helper covers only the current user's GUI domain.
2. Effective-change path: make the SOURCE actually change, then read back the
   downstream CONTENT (not the event, not log freshness) and confirm it
   converged to the source.
3. Atomic-replacement path: replace the source atomically a second time
   (write temp, rename); confirm the watch survived and convergence happened
   again.
4. Worker-drift path: introduce local managed drift (edit the managed output
   without touching the source); confirm the worker corrects the drift.
5. Non-interference: confirm unaffected local fields and every declared
   machine-local exclusion stay untouched through all of the above.
6. Offline/reconnect catch-up: make a change while the worker is down, then
   start or reconnect it; confirm the queued change is delivered by the
   startup reconcile.
7. Quiet idle: record the observed idle window and confirm no generation/ACK
   churn, no recurring convergence runs and no notifications. This proves
   only the observed window, not every future idle period.
8. Failure-path evidence: force a failing convergence and capture stderr/exit
   status. Do not accept success-side freshness (log mtime, last-success
   timestamp) as health.

Sources: `man launchd.plist` and `man launchctl` for key and command semantics;
Apple's [Creating Launchd Jobs](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
for `WatchPaths` trigger behavior.
