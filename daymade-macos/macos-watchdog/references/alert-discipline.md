# Alert Discipline for Watchdogs

When a watchdog *should* notify, and at what rate. Grounded in SRE alerting practice; scaled down to a single machine.

## The two-tier rule

| Tier | Meaning | Watchdog equivalent |
|---|---|---|
| **Page** | Immediate human action required | Send a notification |
| **Ticket** | Action needed but not now | Log line only |

A personal watchdog almost never has a true page. Default everything to ticket (log); page only when *all* of these hold:

1. The failure **persists** beyond the self-recovery window (patient mode already filtered blips), and
2. The watchdog's **full remediation ladder failed** — the human is genuinely the next rung, and
3. This is the **first** time this failure sequence pages (cool-down suppresses repeats).

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

## Anti-patterns

- **Notify on every cycle** — the "all failed" message re-sent every interval. This is the single most common way a watchdog burns its channel.
- **Notify on recovery only after having never notified the failure** — noise without information; recovery notices only pair with a prior failure notice.
- **Health-OK notifications** — a green cycle is the default state and produces log lines, never messages.
