# Recover an interrupted batch without inventing completion

Use when an existing collector's parent or host exits before persisting its
terminal record. Inspect the collector's current writer, lock and archive code;
launchd restarting a PID does not establish that collection resumed.

## Separate writer closure from capture completeness

Establish these independently:

- **Writer closed:** the exact batch can no longer receive writes under the
  collector's verified ownership protocol.
- **Capture complete:** retained terminal metadata and payload validation prove
  the batch completed. Missing, malformed or still-collecting metadata stays
  incomplete even after its writer is gone.

PID absence alone is insufficient. For a collector whose every writer inherits
the same singleton-lock descriptor, a new supervisor acquiring that same lock
through a new file description can prove old cooperating writers have exited.
Verify the lock inode and inheritance contract first; [advisory locking](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/flock.2.html) does not
exclude uncooperative writers. Never delete or replace the lock to obtain proof.
If the protocol cannot establish closure, preserve the batch and report unknown.

Freeze startup closure proof to batches present before launching any new worker.
Do not reuse it for a new batch: the parent and its live child may share the held
lock. For a batch launched by this supervisor, require the exact owned child to
exit and close its diagnostic writers before adopting that batch.

## Preserve, reconcile and resume

Bind adoption to a stable source inventory and content hashes. Refuse aliased
paths, changed payloads or mismatched closing records without releasing evidence.
Preserve every existing byte, including an invalid terminal file; do not replace
it with a successful finish. If an empty batch requires a payload for sealing,
record an explicit empty interrupted-batch witness, not a fabricated sample.

Seal interrupted evidence as incomplete, retain historical gap accounting, and
resume a fresh batch once ownership and storage/archive guards permit it. Recheck
transient reconciliation failures in the same supervisor; a cleared blocker must
not remain latched in memory. Preserve the original failure until later evidence
actually proves recovery; do not manually clear its health state.

## Accept the installed recovery path

Use retained incident artifacts and authorized controlled exits of only the exact
owned job. Cover normal stop, a surviving child retaining the lock, all old writers
gone without a terminal record, malformed/empty batches, changed or aliased bytes,
and a blocker released while the supervisor remains alive. Unknown ownership
stops destructive testing. A process-crash test does not establish cold-boot or
FileVault-unlock behavior.

Require automatic new work after the fault, preserved old bytes at the actual
archive destination, and a later valid batch through the real consumer. When
health publishing is part of the deployment, observe failure and recovery there
too. Reuse the end-to-end custody and monitoring checks in the collector's owning
procedure; PID, registration and local success markers alone are insufficient.
