# Alert Discipline for Watchdogs

When a watchdog *should* notify, and at what rate. Grounded in SRE alerting practice; scaled down to a single machine.

## Tier zero: the failure signal must exist before it can be throttled

Rate and content decisions only matter after a failure can surface at all. Four independent same-night cases (2026-10-21, one multi-machine automation fleet): a history-publishing pipeline stopped for ~16 days unnoticed — eventually even its error log went quiet, because the scheduler itself had been rewritten into a differently-shaped job that was healthy but doing other work; a retention feature printed `blocked` only into an install stdout nobody reads (`removed` stayed empty across many silent installs); a 45-second sync job wrote failures only to a local `last-failure.json` with no reader; a weekly-clean draft logged total retry failure with no notification exit. "The process is running" never proves "the work is succeeding" — a launchd label can even be repurposed under the same name.

Design rule: every periodic pipeline gets a designed failure exit — a state file plus a machine-readable event channel (ledger/error_events), escalating to one notification only per the two-tier rule — and something must actually read the exit. Acceptance question for any new or audited pipeline: "if this job starts failing tonight, what observable thing changes, and who or what reads it?" If the answer is "nothing", treat the pipeline as already failing silently; the only unknown is since when.

## Observation-failure timing

Before selecting a failure count, record the check interval, last successful observation and maximum acceptable observation gap for the user's task. A scheduled start or a failed request does not advance the successful-observation time. Failed collection means the business condition is unknown; it is not evidence that the watched event has not happened.

Choose the failure notification deadline separately from any disruptive repair delay. A low-frequency publication check can require notification on its first failure when waiting another interval would exceed the agreed gap. A fast repair watchdog may still wait through its measured self-recovery window. Do not turn either example into a universal failure-count default; respect the user's explicit timing and use an observable, reversible default when timing is unspecified.

The failure message identifies the affected task, what could not be checked, the last successful observation and a known reason or an explicit unknown. Deduplicate the incident and reconcile uncertain sends through the delivery rules below. Test a failed check followed by recovery, as well as an ordinary successful check with no watched event; the latter must not send an outage alert. A separate scheduler or reader is required to detect a job that never starts; an alert inside the job's own exception handler does not establish that coverage.

## The two-tier rule

| Tier | Meaning | Watchdog equivalent |
|---|---|---|
| **Page** | Immediate human action required | Send a notification |
| **Ticket** | Action needed but not now | Open a durable responsibility record with an owner or supervision path — not a log line only |

A personal watchdog almost never has a true page. Default everything to ticket (a durable responsibility record, not a bare log line). For a repairing watchdog, page only when *all* of these hold; a business observer uses the observation-gap deadline above rather than waiting for an inapplicable repair ladder:

1. The failure **persists** beyond the self-recovery window (patient mode already filtered blips), and
2. The watchdog's **full remediation ladder failed** — the human is genuinely the next rung, and
3. This is the **first** time this failure sequence pages (cool-down suppresses repeats).

## Delivery stages, cooldown, and recovery

A ticket for a deferred actionable background failure is a **durable responsibility record** plus a consumable owner or an independent supervision path — not necessarily an urgent human page. Transient or log-only diagnostics remain allowed when no action is owed.

Distinguish delivery stages separately: **attempted** → **API or transport accepted** → **recipient consumed**. Recipient consumption needs its own receipt; an API acceptance does not establish that anyone saw or processed the message.

- **Failed attempts do not consume the successful-delivery cooldown** — the cool-down protects the channel after a delivered message; suppressing the retry because delivery failed turns a working watchdog into a silent one.
- **Unknown sends retain their identity and must not auto-replay** — an unacknowledged send is reconciled explicitly, not blindly re-sent, or one transport hiccup multiplies into repeat pages.
- **Recovery pairs to the prior accepted failure** — old or unknown successes do not clear a current incident; a recovery notice means nothing unless the failure notice it answers actually reached the channel.

### Adaptive cadences, quiet windows, and startup delays

When a watched job uses adaptive backoff, quiet hours, or a delayed first run after restart, checking only downstream work-ledger timestamps guarantees false stall alerts (or, if widened naively, hides a dead scheduler for a full day).

- **Use dual-layer liveness.** Make the primary check verify scheduler heartbeats (idle, quiet-window, skipped, completed, and startup `started` lines) within a short window (e.g. `2.5×` the base heartbeat interval), and widen the downstream work-ledger idle floor to cover worst-case backoff plus the quiet window whenever the scheduler heartbeat is confirmed healthy.
- **Include startup heartbeats.** If the scheduler intentionally delays its first round by one full interval after container or process restart, include the startup event in the heartbeat pattern so deployments do not trigger a false missing-heartbeat page during the first interval.
- **Suppress during known standdown states.** Suppress missing-heartbeat and stall alerts when the job is intentionally paused or legitimately stopped by an expected daily budget cap.

### Primary-channel blackout and probe blindness

A watchdog whose primary notification transport or remote probe fails silently becomes indistinguishable from a healthy system.

- **Never swallow delivery failures silently.** When sending an alert or recovery notice fails, write a clear diagnostic line to `stderr` (never exit `0` with an empty error log) and, when authorized on the host, emit a bounded local fallback notification so outages in a remote messaging relay do not create a silent blackout.
- **Alert on consecutive probe blindness.** Persist a consecutive `unreachable_streak` counter across runs whenever a remote target (SSH/HTTP) cannot be reached; reset it on the next healthy probe, and raise an explicit unreachable alert once the streak crosses the configured threshold instead of silently skipping target log checks.

## Notification throttling

The measurable harm is fatigue, not the notification itself: teams receiving >120 alerts/day showed 46% slower response and 23% lower resolution accuracy; an alert-to-actionable ratio below ~20% means you have a noise problem, and noise trains the human to ignore the channel that matters.

Rate pattern for repeated identical failures (from the published dynamic rate-limiting algorithm):

- **Critical**: notify immediately, then exponential backoff per identical failure — 5 min → capped at 30 min.
- **Lower severity**: initial 15-min delay, backoff capped at 2 h.
- **Entering cool-down**: exactly one notification saying "standing down for X, will retry then, silence until then" — this single message is what makes the silence trustworthy rather than indistinguishable from a dead watchdog.

### Channel isolation and fingerprint stability

Two common causes of alert fatigue happen even when a cooldown or renotify timer exists:

- **Isolate single-operator ops alerts from shared business channels.** Infrastructure and scheduler health alerts that only one maintainer acts on belong in a dedicated **bot direct message (1:1 P2P)**, not a shared collaboration or document-update group. Mixing periodic ops cards into a business channel drowns out high-signal team updates. Prefer an app/bot identity over a personal user OAuth token for unattended senders (avoids periodic user-token refresh outages and separates alert threads from personal chat), pin the resolved P2P `chat_id` in config so misrouted sends fail closed, and after switching channels verify **both sides** via read-only recipient-side readback when available (new DM shows the delivered card and the retired group has zero new ops alerts after cutover — do not stop at sender-side API acceptance alone).
- **Exclude volatile metadata and transient `running` states from change fingerprints.** Incident fingerprints must capture the actionable failure class, never counters or totals that jitter across runs (for example, round counts, elapsed hours, or fluctuating `complete/total` tallies). Likewise, when a watched periodic job transiently overwrites its health file with a fresh `status="running"` (within its `running_stale_seconds` threshold) that omits terminal fields, suppress same-severity `changed_alert` transitions while `in_progress` is true; keep `new_alert`, severity escalations, stuck-running alerts (`age > running_stale_seconds`), and scheduled `renotify` active. Otherwise the fingerprint oscillates between in-progress and terminal shapes every poll interval and bypasses the renotify window.

## Queue throughput and issue cardinality

A notifier has a measurable drain rate. Before enabling per-issue notifications, compare the number of distinct active issues with `backlog_horizon / send_interval`. In a hypothetical 42-issue burst with a 6-second send interval and a 180-second horizon, only 30 messages can leave the queue; 12 remain. With continued arrivals, the oldest still-pending item will exceed the threshold even when every send succeeds.

When active issue cardinality exceeds drain capacity:

- aggregate issues that share one operator action or root cause into one message;
- keep per-issue detail in the durable state/event log, not the chat channel;
- treat a notification-backlog signal as a ticket about the notification system, not another page that re-enters the same unthrottled queue;
- suppress or coalesce the backlog alert itself until the queue is below the measured capacity.

**War story.** A capture inspector exposed more distinct active issues than the notifier could drain inside its backlog horizon. The queue therefore declared backlog even while sends were succeeding, and that alert became another queued message that amplified the condition it described.

## Message content

- State is read live when composing the message, never frozen at watchdog-authoring time (see `quiet-watchdog-patterns.md` Pattern 1 — a fixed "still broken" template kept lying for 2h after the system healed).
- Include the environment fingerprint that lets a human correlate later: for network watchdogs, gateway + local IP (SSIDs are unreadable on modern macOS); for thermal ones, the top process at that moment.
- End with the one action the human can take, or say explicitly "no action needed — auto-retry at HH:MM."
- For local `osascript` notifications, inspect a delivered card in Notification Center on the target Mac. Distinct watchdogs can appear under `Script Editor`; an `osascript` exit code does not establish the user-visible app name.
- When the displayed app name is generic, put the watcher or monitored service in the notification title so the reader can identify its log without opening the card.

## Local notifications are not visible

Use this path when a job emitted a notification but the user reports no banner or card.
Start with the installed job and the target Mac's notification UI; further code checks
do not resolve missing display evidence. Keep the original test's title and time so
an older card cannot be mistaken for the new result.

1. **Identify the sender.** Inspect an existing matching card or the application's
   notification settings. An `osascript` notification can appear under Script Editor;
   verify the actual sender before changing an application's permissions.
2. **Check the application's display options.** In System Settings → Notifications,
   inspect Allow Notifications, Desktop and the banner/alert style, and Notification
   Center. Match the requested surface: a card in Notification Center does not prove
   that a desktop banner appeared. Labels vary by macOS version.
3. **Check the active Focus.** Inspect whether the sender is allowed or silenced.
   Within the task's authorization, prefer the specific application's exception;
   do not disable Focus globally merely to make one job visible.
4. **Check sharing suppression.** Inspect “when mirroring or sharing the display”
   in Notifications, and whether sharing/mirroring is active. A virtual display's
   presence alone does not establish that suppression caused the failure. Changing
   this setting affects other applications too: explain that scope and obtain
   authorization if it is not already covered, then retain the original value for
   recovery. See [Apple's Notifications settings](https://support.apple.com/guide/mac-help/mchl205da693/mac).
5. **Read back the active setting.** Prefer the native settings UI. A successful
   preference-file write or a notification database entry is supporting evidence,
   not proof that the active setting changed or that a banner rendered. If the UI
   remains unchanged, keep the change unverified; do not use historical preference
   paths or guessed private APIs as a replacement for that observation. Respect
   host input/foreground refusals and do not restart shared notification services.
6. **Test the installed path once after a relevant change.** Use a safe event from
   the actual installed sender, then inspect a matching new banner or card on the
   target Mac. A standalone probe of another sender cannot accept the job. When
   only human observation can settle visibility, request that observation and keep
   the result pending; do not repeatedly send uncertain tests or report restoration
   from command success. Actual reading by the user remains separate from rendering.

Stop when the requested surface is observed, or state the exact remaining display
or host-permission gap and its next action. Preserve the original job's state and
notification deduplication; this diagnosis does not authorize re-running its
business action or changing delivery channels.

## Anti-patterns

- **Notify on every cycle** — the "all failed" message re-sent every interval. This is the single most common way a watchdog burns its channel.
- **Notify on recovery only after having never notified the failure** — noise without information; recovery notices only pair with a prior failure notice.
- **Health-OK notifications** — a green cycle is the default state and produces log lines, never messages.
