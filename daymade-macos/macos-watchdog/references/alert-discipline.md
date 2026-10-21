# Alert Discipline for Watchdogs

When a watchdog *should* notify, and at what rate. Grounded in SRE alerting practice; scaled down to a single machine.

## Tier zero: the failure signal must exist before it can be throttled

Rate and content decisions only matter after a failure can surface at all. Four independent same-night cases (2026-10-21, one multi-machine automation fleet): a history-publishing pipeline stopped for ~16 days unnoticed — eventually even its error log went quiet, because the scheduler itself had been rewritten into a differently-shaped job that was healthy but doing other work; a retention feature printed `blocked` only into an install stdout nobody reads (`removed` stayed empty across many silent installs); a 45-second sync job wrote failures only to a local `last-failure.json` with no reader; a weekly-clean draft logged total retry failure with no notification exit. "The process is running" never proves "the work is succeeding" — a launchd label can even be repurposed under the same name.

Design rule: every periodic pipeline gets a designed failure exit — a state file plus a machine-readable event channel (ledger/error_events), escalating to one notification only per the two-tier rule — and something must actually read the exit. Acceptance question for any new or audited pipeline: "if this job starts failing tonight, what observable thing changes, and who or what reads it?" If the answer is "nothing", treat the pipeline as already failing silently; the only unknown is since when.

## The two-tier rule

| Tier | Meaning | Watchdog equivalent |
|---|---|---|
| **Page** | Immediate human action required | Send a notification |
| **Ticket** | Action needed but not now | Open a durable responsibility record with an owner or supervision path — not a log line only |

A personal watchdog almost never has a true page. Default everything to ticket (a durable responsibility record, not a bare log line); page only when *all* of these hold:

1. The failure **persists** beyond the self-recovery window (patient mode already filtered blips), and
2. The watchdog's **full remediation ladder failed** — the human is genuinely the next rung, and
3. This is the **first** time this failure sequence pages (cool-down suppresses repeats).

## Delivery stages, cooldown, and recovery

A ticket for a deferred actionable background failure is a **durable responsibility record** plus a consumable owner or an independent supervision path — not necessarily an urgent human page. Transient or log-only diagnostics remain allowed when no action is owed.

Distinguish delivery stages separately: **attempted** → **API or transport accepted** → **recipient consumed**. Recipient consumption needs its own receipt; an API acceptance does not establish that anyone saw or processed the message.

- **Failed attempts do not consume the successful-delivery cooldown** — the cool-down protects the channel after a delivered message; suppressing the retry because delivery failed turns a working watchdog into a silent one.
- **Unknown sends retain their identity and must not auto-replay** — an unacknowledged send is reconciled explicitly, not blindly re-sent, or one transport hiccup multiplies into repeat pages.
- **Recovery pairs to the prior accepted failure** — old or unknown successes do not clear a current incident; a recovery notice means nothing unless the failure notice it answers actually reached the channel.

## Notification throttling

The measurable harm is fatigue, not the notification itself: teams receiving >120 alerts/day showed 46% slower response and 23% lower resolution accuracy; an alert-to-actionable ratio below ~20% means you have a noise problem, and noise trains the human to ignore the channel that matters.

Rate pattern for repeated identical failures (from the published dynamic rate-limiting algorithm):

- **Critical**: notify immediately, then exponential backoff per identical failure — 5 min → capped at 30 min.
- **Lower severity**: initial 15-min delay, backoff capped at 2 h.
- **Entering cool-down**: exactly one notification saying "standing down for X, will retry then, silence until then" — this single message is what makes the silence trustworthy rather than indistinguishable from a dead watchdog.

## Message content

- State is read live when composing the message, never frozen at watchdog-authoring time (see `quiet-watchdog-patterns.md` Pattern 1 — a fixed "still broken" template kept lying for 2h after the system healed).
- Include the environment fingerprint that lets a human correlate later: for network watchdogs, gateway + local IP (SSIDs are unreadable on modern macOS); for thermal ones, the top process at that moment.
- End with the one action the human can take, or say explicitly "no action needed — auto-retry at HH:MM."
- For local `osascript` notifications, inspect a delivered card in Notification Center on the target Mac. Distinct watchdogs can appear under `Script Editor`; an `osascript` exit code does not establish the user-visible app name.
- When the displayed app name is generic, put the watcher or monitored service in the notification title so the reader can identify its log without opening the card.

## Anti-patterns

- **Notify on every cycle** — the "all failed" message re-sent every interval. This is the single most common way a watchdog burns its channel.
- **Notify on recovery only after having never notified the failure** — noise without information; recovery notices only pair with a prior failure notice.
- **Health-OK notifications** — a green cycle is the default state and produces log lines, never messages.
