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
   revive a cancelled task, undo an explicit pause without a later explicit user
   continuation, reset usage or increase a budget.
   A current user continuation instruction may authorize resuming this same existing
   paused/blocked Goal; a scheduled status reminder or peer message does not.
   `usageLimited` and `budgetLimited` are not recovery-by-reset cases: do not change
   their counters/budget or create a substitute Goal. If only one route is blocked,
   continue the other necessary authorized work.
4. Read the latest failed/interrupted turn and unresolved tool outcome through the
   verified thread's owning reader/control. Record its exact error and time beside
   the Goal observation; a status label alone does not explain why execution stopped.
   Apply the following preflight before attempting a recovery write.
5. Inspect the installed host's official help, generated protocol schema and live
   connection contract. Prefer its purpose-built recovery control when available.
   If using an existing verified protocol transport, bind it to the exact target
   thread and endpoint; do not guess sockets or edit the runtime database.

### Classify the failure before recovery

| Observed cause | Next action |
|---|---|
| Transient capacity, network or service failure | Read whether the original turn/process later completed. Resume only unfinished work through an authorized supported control; do not duplicate an outcome-unknown write. |
| Explicit user pause/cancellation | Require a later human continuation covering the same task. A scheduled reminder or peer message cannot revoke the pause. |
| Usage/budget limit | Preserve counters and budget; use only an already-authorized available route. Do not reset or replace the Goal. |
| Safety/policy rejection | Report the rejected action and stated reason. Do not retry that same rejected action through another model, transport, rewording or state store to bypass the rejection. Continue independent permitted work; use a genuinely narrower permitted action only when it avoids the rejected operation. |
| Missing or ambiguous cause | Keep the cause unknown and obtain the missing bounded readback before a recovery mutation. Continue independent work that does not need that mutation. |

Keep the user's authorization separate from the host's execution decision: a
defensive task can be authorized and still have a rejected execution route.

### Recover through the host that owns the loaded thread

Identify the host that actually holds the verified thread before selecting a
control. A TUI running without a daemon can still expose its own Goal command;
an absent App Server socket does not establish that recovery is unavailable.

#### Existing TUI control

When the installed TUI's official help supports `/goal resume`, bind the existing
session's input surface to the exact target thread. After the authorization and
failure preflight above, capture the existing Goal fields as required by
[Recover and verify](#recover-and-verify-without-resetting-the-task), then submit
`/goal resume` once in that same Codex input composer. This is a TUI slash command,
not an OS shell command or a queued peer message. Do not open another resumed
process to manufacture a controllable session.

The continuation executor may perform this input only through an available,
permitted control of that verified session. If host policy rejects access to the
application or input surface, report the exact rejection and leave `/goal resume`
as the current user's action in that session; do not switch input APIs or terminal
transports to bypass the rejection. Continue independent permitted work without
claiming the Goal resumed.

Treat the command response as an attempt, then independently read the same Goal
and observe a later automatic turn under the shared verification procedure below.
Preserve the pause/cancellation and usage/budget boundaries above; command support
does not authorize a reset or revival.

The [official Goal guide](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)
documents `/goal resume`. In the version-pinned
[TUI dispatch](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/tui/src/chatwidget/slash_dispatch.rs#L991)
and [Goal action](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/tui/src/app/thread_goal_actions.rs#L233),
it requests `active` for the existing thread while omitting objective and budget
replacement. Verify support on the installed version and read back preservation;
these sources do not prove a command succeeded in the current session.

#### App Server control, when exposed

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

When the current generated schema exposes `thread/goal/get` and `thread/goal/set`,
an already-running owner's verified Unix WebSocket can supply the control even
when a model tool such as `update_goal` cannot request `active`. Resolve its endpoint
from the current `CODEX_HOME` and live host contract, verify the loaded thread,
and initialize that existing connection; do not start or restart a server. A
reusable transport's read-only RPC helper may be reused without changing its peer
sender's no-resume boundary. In a schema defining explicit-user provenance, the
minimal authorized setter shape is:

```json
{"method":"thread/goal/set","params":{"threadId":"<verified-thread-id>","status":"active","origin":"user"}}
```

This is a version-specific protocol shape, not a universal shell command or a
claim that every host exposes this endpoint. Discover support on the current host
first; confirm the getter/setter methods and accepted status/provenance values
from the installed CLI-generated schema. Try a newly verified route only when
new interface/connection evidence changes the prior failure diagnosis; do not
loop an unresponsive or uncertain request. Omitting `objective` and `tokenBudget` avoids requesting their replacement;
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

## Verify unattended work and reporting separately

When the user requests continued work and periodic updates, bind two outcomes in
the existing task record: a future business turn and a report delivered through an
authorized channel. Use only the host's supported execution/scheduling owner; this
Skill does not install a scheduler, create a replacement Goal or grant messaging
permission. A reporting reminder alone does not execute the business task.

For each outcome, record the exact task/target, executor, due time and timezone,
last observed result and any failure. Compare the due time with the current clock
after interruption; an overdue update needs delivery, not a timer in the past.
Read an actual later turn for execution and an actual delivered message for
reporting. Missing observations remain unverified. One successful report does not
prove the next report or continued work; registered timers and an active Goal do
not prove either outcome. Do not promise an unattended cadence before its supported
executor is established, or describe unobserved future rounds as working.
