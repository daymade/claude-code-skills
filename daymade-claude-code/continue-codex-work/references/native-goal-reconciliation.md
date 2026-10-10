# Native Goal reconciliation

Use only when taking over a task that already has a native Goal. Ordinary tasks do
not need a Goal. Keep the user's latest stage, authorization and stop request as
the governing contract; a reminder or an unfinished objective adds no authority.

## Read status and discover the actual recovery control

1. Resolve the exact logical thread through the verified history receipt, then
   read its Goal with the current host's getter. Keep missing, null or unreadable
   Goal state explicit; never create a replacement to make the status look complete.
2. Separate unfinished business from automatic execution. `blocked`, `paused`,
   `complete`, `usageLimited` and `budgetLimited` do not establish an active run.
   Even `active` is a state, not evidence that a later automatic turn occurred.
3. Check current user authorization and budget boundaries before recovery. Do not
   revive a cancelled task, undo an explicit pause, reset usage or increase a budget.
   If only one route is blocked, continue the other necessary authorized work.
4. Inspect the installed host's official help, generated protocol schema and live
   connection contract. Prefer its purpose-built recovery control when available.
   If using an existing verified protocol transport, bind it to the exact target
   thread and endpoint; do not guess sockets or edit the runtime database.

### Recover through the host that owns the loaded thread

As the continuation executor, distinguish a successful read through an independent
stdio App Server from permission to update a thread another live host owns. If the
setter reports an active writer, discover the existing host's verified control
transport and confirm it has the exact target thread loaded before using its
recovery control. Do not kill the writer, restart its service, edit the database or
unregister it to obtain access. If that host cannot be bound, report the recovery
path unresolved and continue other authorized work.

Inspect the current setter schema for mutation provenance. When it defines an
explicit-user origin, supply it only for a verified user recovery instruction;
missing provenance does not supply authorization. Do not omit or change provenance
to bypass a rejected update. The runtime enforces its write guards; the executor
must verify the authorization and host binding before applying recovery.

Historical example: Codex 0.160.1's installed App Server schema exposed `thread/goal/get` and
`thread/goal/set` without requiring the experimental schema flag. Its live Unix
WebSocket transport accepted the following setter shape after initialization:

```json
{"method":"thread/goal/set","params":{"threadId":"<verified-thread-id>","status":"active"}}
```

This is a version-specific protocol shape, not a universal shell command or a
claim that every host exposes this endpoint. Discover support on the current host
first. Omitting `objective` and `tokenBudget` avoids requesting their replacement;
whether the runtime preserved them must still be read back.

## Recover and verify without resetting the task

Capture the existing objective, budget, creation identity and usage counters before
the authorized recovery. Apply the verified control once, then independently read
the same Goal again. Confirm `active`, unchanged objective and budget, preserved
creation identity and counters that have not been reset. Report mismatches and stop
dependent recovery actions; do not retry by rewriting fields or using another store.

Report runtime restoration separately from observed automatic continuation. Record
an automatic turn only when the host actually starts one and it advances or reports
the same authorized task. A queued status reminder does not prove business execution.
If the current host has no verified recovery path, state that bounded limitation
and complete the useful authorized work this turn can perform; do not mark the
business objective complete merely because that recovery path is unavailable.
