---
name: macos-watchdog
description: >-
  Design, deploy, and discipline macOS launchd watchdogs — LaunchAgents/LaunchDaemons that detect a recurring problem and auto-remediate it. Use whenever creating or editing a persistent background monitor / daemon / agent on macOS, writing a launchd plist, scheduling a self-healing script, or when a watchdog has become a disturbance itself: re-launching apps the user quit, firing repeated notifications, re-running its full repair ladder every few minutes on an unfixable network, or hammering the system (crash loops, fork storms, runaway restarts). Also use for stop/disable semantics (bootout vs bootstrap vs disable vs unload), adding cooldown / backoff / notification throttling to a self-healer, binding a monitor's lifecycle to its premise state, or auditing existing LaunchAgents. 中文触发：launchd 守护进程、常驻任务、开机自启、后台监控、定时自愈脚本。 Covers KeepAlive/ThrottleInterval/domains/logging, premise self-checks, auto-cooldown, alert layering, batch throttling.
---

# macOS Watchdog

A watchdog is a launchd job that periodically detects a recurring problem and remediates it without a human. The craft is not "how to install a plist" — it is **how to keep the watchdog from becoming a new disturbance**: every watchdog on this machine was born from an incident, and the recurring failure mode afterward is the watchdog itself (false "all good" reports, notification floods, re-launching apps the user quit, fork-bomb replays).

The governing principle, learned the expensive way: **a watchdog's lifecycle is bound to its premise state**. When the condition it exists to fix cannot be fixed by it (broken WiFi, user quit the target app, prerequisite state gone), the watchdog must stand down *by itself* — not wait for a human to disable it.

## Entry decision tree

| The situation is… | Go to |
|---|---|
| Installing a NEW watchdog from scratch | § Deploy, then § The quiet-watchdog contract |
| An existing watchdog misbehaves (spam, re-launches apps, hammers) | § The quiet-watchdog contract, diagnose which clause it violates |
| Stopping / disabling / restarting a job | § Stop semantics |
| plist key details (KeepAlive forms, domains, logging, resource limits) | `references/launchd-plist-reference.md` |
| Cooldown/backoff/notification-throttle patterns + sanitized war stories | `references/quiet-watchdog-patterns.md` |
| SRE alert layering (page vs ticket, fatigue numbers) | `references/alert-discipline.md` |

## The quiet-watchdog contract (the four clauses)

Before shipping or blessing any watchdog, all four must hold. Each clause exists because a real watchdog violated it.

### 1. Premise-state self-check — it knows when it has no job

The script's first act on every run: verify the state that justifies its existence still holds. If not, exit silently — no remediation, no notification, no side effects.

- A proxy-repair watchdog checks the proxy app is running first; user quit it → skip the cycle.
- A "did the config switch back" watcher checks the config state it watches; already switched → self-stop, not another round of misleading notifications. (Real case: a recovery watcher kept firing for 2h after its premise resolved, sending 3 spurious notices, because nothing told it to stop.)

### 2. Remediate first, page only on sustained failure

Detection stays honest on every cycle, but the *disruptive action* defers until the failure persists across N consecutive cycles (patient mode). Rationale: oscillating chains self-recover in minutes; a force-reconnect on a self-limiting blip is net-harmful. Measure your system's real self-recovery window before choosing N (one chain's 94-min observatory run showed ≤3 min self-recovery → N=2 cycles at 5-min interval).

Escalation ladder (cheap → disruptive): refresh state → restart connection → remote repair. Each rung verifies before climbing.

### 3. Escalating auto-cooldown — an unfixable environment means silence

When the full repair ladder fails, the environment is unfixable by the watchdog (broken WiFi, captive portal, dead upstream). The naive behavior — re-run the entire ladder + notification every interval forever — is exactly "the watchdog keeps re-launching the app every 10 minutes."

`ThrottleInterval` does **not** fix this: it throttles process respawn, is a fixed delay with no backoff, and does nothing for a job that exits 0 after spamming. Cool-down must live in the application layer:

- Record consecutive exhausted rounds in a state file.
- After each exhausted round, stand down for an escalating tier (e.g. 30 min → 2 h → 6 h, last tier repeats).
- One notification when *entering* cool-down; zero during it. On tier expiry, retry one round; any real heal clears the counter and the cool-down state.
- A manual `pause [duration]` command with a TTL state file is the fallback — but the auto path must work with no human command at all. A disable mechanism that requires the user to remember a command is not a mechanism.

Reusable implementation: `scripts/watchdog-cooldown.sh` (source it; provides `paused_any`, `record_exhausted`, `clear_exhausted`, `cmd_pause`/`cmd_resume`).

### 4. Never resurrect what the user explicitly quit

On macOS, `open <url-scheme>` **launches the app** when it isn't running, and `open` without `-g` steals foreground. A watchdog whose remediation uses URL schemes (or `open -a`, or restarting a GUI app) will read to the user as "I quit it and it came back."

Gate every such action: check the target process is alive before invoking its scheme, and pass `-g` so a legitimate action never pops a window. If the user quit the app mid-remediation, abort the ladder — cleanup traps must honor the same gate, or the "ensure connected on exit" fallback becomes the resurrector.

## Deploy (mechanics that bite)

1. **Location**: user agent → `~/Library/LaunchAgents/` (GUI session context: can `open` apps, show notifications); system daemon → `/Library/LaunchDaemons/` (root, no GUI access). Choose by whether the job needs the user's GUI session, not by habit.
2. **plist**: start from `assets/launchagent.template.plist` (annotated: Label, ProgramArguments, StartInterval, StandardOutPath/StandardErrorPath, ThrottleInterval, Nice). Validate with `plutil -lint`. `ProgramArguments` element 0 = absolute path; never rely on PATH inheritance.
3. **Load/reload**: `launchctl bootstrap gui/$(id -u) <plist>`; after editing a plist, `bootout` then `bootstrap` again — launchd's active state must match disk. Force one run with `launchctl kickstart -k gui/$(id -u)/<label>`.
4. **Logs**: `StandardOutPath`/`StandardErrorPath` are non-negotiable (without them failures vanish), plus in-script log rotation (cap ~1 MB).
5. **Idempotency guard**: re-running your deploy must not double-install. `scripts/new-launchagent.sh <label> <script> <interval>` is the idempotent wrapper (bootout-if-loaded → write plist → bootstrap → verify `launchctl list`).
6. **TCC / Full Disk Access**: a LaunchAgent reading another app's Group Container or protected dirs needs FDA granted to the *actual interpreter* — Xcode's python3 stub fails where your real python3 works. Verify with the exact binary from `ProgramArguments`, not the one your shell resolves.
7. **Batch throttling by default**: any watchdog loop that spawns work (replays, fuzz, batch scans, parallel API calls) needs an explicit rate cap as a default parameter, not a later optimization. To the machine, an unthrottled loop and a runaway process are indistinguishable (real case: an unthrottled test replay forked 1,041 processes/sec for 7 minutes and pushed the die to 83 °C).

## Stop semantics (the deprecated trap)

| Intent | Command |
|---|---|
| Stop now, allow re-bootstrap later | `launchctl bootout gui/$(id -u)/<label>` (daemon: `sudo launchctl bootout system/<label>`) |
| Stop now AND keep stopped across login | `launchctl disable user/$(id -u)/<label>` (reverse: `enable`) |
| Edit then reload | `bootout` → edit plist → `bootstrap` |

**Never `launchctl unload`**: deprecated, and on Ventura+ the job re-loads via `RunAtLoad` when the plist stays in place — the "disabled" watchdog fires again (observed: an `unload`ed watcher re-firing 3 times in 2h). `bootstrap`/`bootout` are the modern pair.

## Troubleshooting quick map

| Symptom | First check |
|---|---|
| "It re-launches the app I quit" | URL-scheme/`open` calls missing the process-alive gate (clause 4) |
| "It spams the same repair every few minutes" | No exhausted-round cool-down (clause 3); also check the ladder's failure path doesn't reset its dead-counter |
| "It reports healthy through a real outage" | Health check certifies only the path it probes — one green probe ≠ all planes healthy (add the second plane's probe) |
| "bootout didn't stick / it came back" | `unload` used instead of `bootout`, or `RunAtLoad` + plist still in place |
| Silent no-runs | `StandardErrorPath` missing → failures invisible; then `log show --predicate 'process == "launchd"' --last 15m` |
| Works interactively, fails under launchd | TCC/FDA on the wrong interpreter; PATH assumptions in `ProgramArguments` |

Details and the sanitized war stories behind each clause: `references/quiet-watchdog-patterns.md`.
