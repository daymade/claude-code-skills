---
name: automatic-ghostty-snapshots
description: >-
  Install, stop and verify calendar-based Ghostty recovery snapshots that save
  only changed inventories. Read for periodic backups, launchd status, partial
  UUID coverage, unchanged-write behavior or observation failures.
---

# Periodic snapshots that save only changes

Use `scripts/ghostty_watch.py` for scheduled observation. It never launches
Ghostty, opens tabs, restores sessions or reads conversation history. Manual
`snapshot` remains available for content-based liveness grading.

## Install and verify

Run the ordinary installer from the selected Skill source:

```bash
# Read-only deployment plan:
python3 <skill-dir>/scripts/ghostty_watch.py install

# Install the owned runtime and enable the job:
python3 <skill-dir>/scripts/ghostty_watch.py install --apply

# Inspect registration, latest coverage and launchd completion state:
python3 <skill-dir>/scripts/ghostty_watch.py status

# Inspect current inventory and cost without saving a snapshot:
python3 <skill-dir>/scripts/ghostty_watch.py probe

# Stop now and keep stopped across login; all backups remain:
python3 <skill-dir>/scripts/ghostty_watch.py stop
```

Expected install result: `installed: true`, label `io.ghostty.session-snapshot`,
and an owned runtime path. The installer creates a Python 3.12 environment once
with `uv`, then registers its fixed `~/.ghostty-session/watcher/venv/bin/python`.
There is no package-manager dispatcher in launchd. Reinstall updates the owned
script copies and enables the same job; it does not create another label.

The LaunchAgent uses `RunAtLoad` and `StartCalendarInterval` every 10 minutes, with
no `KeepAlive`. The shared default is 10 minutes; `install --every-minutes 5 --apply`
changes the interval if asked. Install independently compares the loaded
calendarinterval minutes with the requested definition and disk plist. `status`
shows `schedule.active_minutes`, `disk_minutes` and `match`; missing or unfamiliar
calendar formats remain `unknown`. Unrelated event-trigger Minute fields are not
calendar evidence.

While the Mac is awake and observations succeed, the nominal backup delay is
0–10 minutes plus collection and scheduling delay. Sleep or failed observations
can delay it further. Save a manual snapshot before a planned reboot when that
window is too long.
A supervisor kills the observation process group after 15 seconds. OS reads and
process counts are bounded; a failed or timed-out observation exits nonzero.
If Ghostty is not running, stand down quietly and retain the backup; do not
resurrect the app or write a repeated error. If Ghostty is running but observation
is empty or failed, report unknown instead of replacing the backup.
The job uses one `ps` parent graph and one batch `lsof` cwd query for at most
256 candidate CLI processes. It does not enumerate history trees or refresh an
index, whether the inventory changed or stayed the same.

After install, the deploying agent verifies a completed native round, not only
registration. Read `status` before and after a scheduled round: the launchd run
count must advance and the last exit must be zero. Read a newly changed snapshot
independently when one is expected. An unchanged successful round intentionally
creates no report, snapshot, heartbeat or routine log entry; its evidence is
launchd completion state. Snapshot time is the last saved change, not proof that
the observer is currently running. A foreground `probe` alone does not certify
background permissions, sleep/wake continuity or power savings.

## What counts as a change

Compare the complete restore inventory by tool, session UUID, cwd, profile and
actual shell-quoted reopen command, including the relevant profile-env prefix.
Ignore PID, TTY, process order, activity timestamps and age. Automatic snapshots
freeze their reopen command so a later profile-map edit cannot silently change
that backup's restoration context. The next observation detects the new mapping
and saves a new version when it affects a covered session.

Save a small complete manifest on change, not a transcript copy or a chain of
deltas. Atomic private files and a shared nonblocking writer lock protect manual
and scheduled snapshots. Old archives are never deleted or pruned. A shrinking
nonempty complete inventory records removals; an empty inventory after reboot,
an OS-query failure, corrupt prior state, lock contention or timeout retains the
last useful backup. Failure detail goes to bounded stderr/error logs only.

The first scheduled observation upgrades a matching manual latest snapshot to
an automatic manifest once. Later equal observations write nothing. The default
`latest.json` route points at the newest saved manifest; manual snapshot archives
remain available. Automatic snapshots declare liveness `not-observed`, with
`unknown` session status. `restore` selects their whole recorded set by default,
including waiting/quota sessions, while manual snapshots retain the existing
active-only default. `--all`, `--only` and duplicate-free retries still work.

## Partial UUID coverage

Only Ghostty descendants are observed; unrelated Terminal sessions are excluded.
Some native Codex TUIs do not expose a session UUID in argv. Record those as
`unresolved`, with their captured flags, profile and cwd; never guess an ID from
the newest rollout or an unrelated history row. A Node wrapper and its native
vendor child count as one TUI. Noninteractive CLI workers are excluded.

Identity parsing consumes known option values before recognizing selectors.
Unknown option arity, Claude positional prompts, forked IDs, and prompts following
a Codex resume ID remain unresolved. `ps` flattens argv and loses quoting: a quoted
Codex prompt beginning `resume <UUID>` is indistinguishable from a real resume
subcommand. This recognition assumes a prompt-free selector invocation; use
explicit indexed identity verification when that boundary is uncertain.

A nonempty known set can still produce a useful partial backup. While unresolved
TUIs exist, preserve previously recorded IDs that are now absent as
`retained-unverified`; do not interpret an ambiguous observation as a removal.
Repeated identical known/unresolved inventories ignore PID and TTY changes and
save nothing. A later complete, nonempty observation can record genuine removals.
`status` shows recorded total, identified-at-capture count, unresolved count and
retained count from the saved
manifest. These are backup coverage, not proof that every recorded tab is live.

After reboot, restore recorded IDs using the ordinary route. Unresolved rows are
not resumable sessions; use explicit indexed reconstruction and identity
verification if their session IDs must be recovered. Partial snapshots may retain
already-closed sessions conservatively; inspect the manifest or use `--only` when
that distinction matters. Window grouping and UUID-less tab identity remain
unavailable. Calendar observation also cannot capture a change that occurs and
vanishes between scheduled rounds.

## Recover observation failures

For a corrupt latest manifest, or a missing latest pointer while archives remain,
the observer refuses to start a fresh chain over the existing backups. Stop the
job and inspect a known archive. Use `restore --snapshot <archive>` explicitly;
after intended sessions are live again, a new manual snapshot can establish a
valid latest manifest before reinstalling/enabling the observer.

The shared atomic writer is `scripts/ghostty_storage.py`; both snapshot paths use
it. Synthetic tests in `scripts/test_ghostty_watch.py` exercise cold, unchanged,
changed, partial and failed observations without GUI actions, including 1- and
1,000-file history trees with transcript-read rejection.
