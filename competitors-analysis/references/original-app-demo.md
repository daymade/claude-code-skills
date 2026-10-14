# Isolated original-application demo

Use when source research requires an inspectable running application or the user
asks to assess reuse through actual behavior. Keep execution within the current
task authorization; a research demo does not authorize production transactions or
publication. Stop after the named journey and its evidence limits are clear.

## Preserve the application being evaluated

Bind the source revision, actual startup entry and runtime to the existing Source
Register. Keep an unchanged reference checkout, an isolated demo environment and
a separate repair worktree. Do not rewrite the UI or business engine into a new
prototype and present that as the source product. Record local adapters separately.

Read the executed path through payment, procurement, email, callbacks, background
jobs and cleanup before running it. Substitute external side-effect boundaries
with deterministic synthetic providers while retaining original validation,
state transitions, queue logic, persistence and user interface. If a production
boundary cannot be isolated, leave that journey unexecuted and identify the gap.

## Prepare a bounded local journey

Record a small manifest in the research project's existing run notes:

| Binding | Required observation |
|---|---|
| Source and runtime | Exact source revision, entry, dependency/runtime identity and local URL. |
| State | Test-owned database/schema, migrations, synthetic seed and isolation/cleanup ownership. |
| Adapters | External boundaries replaced, original application files changed, deterministic responses and recorded actions. |
| Egress | The actual enforcement layer and blocked/allowed destinations; include scheduled jobs and child processes in its coverage. |
| Journey | Original UI/API actions and expected durable states for the user's named scenario. |
| Resources | Processes/resources started by this run, their owners, handles and terminal readback. |

Apply original migrations and seed a usable catalog/test account through supported
test/admin paths. Exercise the actual original user journey: for a storefront,
show a populated item, create its order, submit a synthetic payment outcome and
inspect original fulfillment/receipt and persisted state. Component HTTP 200,
an empty catalog or a closed purchase entry proves startup only.

Calibrate egress before side-effecting cases: a known permitted local provider
receives its synthetic request, and a benign disallowed destination attempt is
blocked at the declared enforcement layer. A mocked fetch alone does not cover a
child process or separate runtime. If enforcement is unverified or incomplete,
stop dependent external-effect cases; continue independent source/read-only work.
Record unexpected attempts without sending real credentials or charges.

Run the actual application engine for the claimed path, including native database
transactions and background handlers where relevant. Invoking a scheduled handler
locally proves that invocation; a configured cron expression does not prove a
future cloud trigger. Synthetic payment/mail responses do not prove provider
acceptance, money movement or delivery to a real inbox.

## Deliver and preserve the result

Read back both the user-visible journey and persisted state, and attach the exact
startup/verification commands, source binding, adapter observations and remaining
limits to the existing research profile/run notes. Keep no credentials in exported
logs. Retain the accepted demo when starting repairs; do not stop unrelated processes.

If fixes are part of the authorized task, commit them in the repair worktree and
export patches from its exact base. Replay them against that same immutable base
in an isolated reconstruction without the shared index, and compare the resulting
Git tree to the delivered tree. A list of patches is not a reconstructible result.
Replayed source does not prove the unchanged reference demo has acquired the fixes;
label each runtime by the source it actually runs.
