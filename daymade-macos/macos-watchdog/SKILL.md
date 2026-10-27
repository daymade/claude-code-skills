---
name: macos-watchdog
description: >-
  Designs and audits macOS launchd watchdogs: LaunchAgent/LaunchDaemon setup,
  plist edits, scheduled self-healing, repeated notifications, apps reopening after
  quit, crash/repair loops, Script Editor alerts, stop/disable/restart,
  cooldown/backoff, notification throttling, alert decisions, schedule readback,
  WatchPaths/FSEvents event triggers. Supports periodic observers.
  launchd 守护进程、常驻任务、开机自启、后台监控、定时自愈、通知来源排查、事件驱动监控。
---

# macOS Watchdog

## Bind the ordinary entry before choosing a mechanism

Before selecting event/periodic triggers, a transport, or a helper, record these
constraints from the original request in the current task plan; do not create a
separate document for a simple task:

- **Ordinary entry:** where the user will actually start or use the work. When
  its launcher adopts only some invocation or lifecycle forms, derive the
  relevant forms from the current launcher and actual requested use; record
  adopted, bypassed and unverified forms separately, and accept each claimed
  form through its real consumer.
- **Manual activation:** whether the request permits any extra command or setup
  after delivery.
- **Lifecycle:** whether the result covers a session, login, or machine, and
  which owned components must start and stop with it.

If the request explicitly limits the work to a manually run helper, an opt-in
experiment, or a read-only design, preserve that scope. Otherwise, accept through
the ordinary entry without unrequested manual activation. Reuse the existing
session owner for session-bound components; use launchd for login/machine
persistence rather than turning every automation request into a global watcher.

A completed business round inside a helper alone is component-only evidence:
leave the requested result unmet and continue authorized integration. Keep
unauthorized or unobserved old-session takeover and other lifecycle coverage
unknown; do not stop other tasks or bypass a host refusal to obtain acceptance.

When a safety condition is temporary and automatic work must resume afterward,
exercise its release in the same running instance: first verify no prohibited
action, then remove that condition and require the next eligible event to
complete the business action. A separate fresh-instance success, no-action
result or health flag does not establish this transition; preserve explicit
stop, lost identity and uncertain-delivery boundaries.

Select event or periodic triggers for the problem being observed, then apply the quiet-watchdog contract before remediation.

Bind a watchdog's lifecycle to its premise state. When it cannot repair the
condition (broken WiFi, user quit the target app, prerequisite state gone),
stand down without waiting for a human to disable it.

## Entry decision tree

| The situation is… | Go to |
|---|---|
| Installing a NEW watchdog from scratch | Select the trigger through `references/event-driven-observers.md`, then § Deploy and § The quiet-watchdog contract |
| Installing, upgrading, reusing or starting a persistent Python job | § Persistent Python runtime |
| An existing watchdog misbehaves (spam, re-launches apps, hammers) | § The quiet-watchdog contract, diagnose which clause it violates |
| Stopping / disabling / restarting a job | § Stop semantics; before replacement follow `references/event-driven-observers.md` § Wait for an authorized unload before replacement |
| Retiring a job and its tool permanently | § Stop semantics → Decommissioning a job permanently |
| plist key details (KeepAlive forms, domains, logging, resource limits) | `references/launchd-plist-reference.md` |
| Choosing between event-driven and periodic for a source of truth | `references/event-driven-observers.md` § Select event vs periodic |
| Deploying / accepting an event-driven observer (WatchPaths, FSEvents, inotify-style) | `references/event-driven-observers.md` § Deployment SOP and § Acceptance SOP |
| Checking whether a plist edit is active, or comparing job argv / explicit ENV / configured paths / scheduling keys | Run `scripts/inspect_native_job.py` with the exact expected plist; read `references/native-job-readback.md` for result, scheduling-flag and source-selection rules |
| Setting up or recovering an already-authorized persistent calendar job with delivery deadlines | `references/launchd-plist-reference.md` § Calendar deadlines and recovery; check overdue work and actual delivery separately |
| Cooldown/backoff/notification-throttle patterns + sanitized war stories | `references/quiet-watchdog-patterns.md` |
| SRE alert layering (page vs ticket, fatigue numbers) | `references/alert-discipline.md` |
| A watchdog alert appears under Script Editor or its sender is unclear | `references/alert-discipline.md` § Message content; inspect the delivered card |

## The quiet-watchdog contract

Before shipping or blessing any watchdog, every clause below must hold. Each clause exists because a real watchdog violated it.

### 1. Premise-state self-check — it knows when it has no job

The script's first act on every run: verify the state that justifies its existence still holds. If not, exit silently — no remediation, no notification, no side effects.

- A proxy-repair watchdog checks the proxy app is running first; user quit it → skip the cycle.
- A "did the config switch back" watcher checks the config state it watches; already switched → self-stop, not another round of misleading notifications. (Real case: a recovery watcher kept firing for 2h after its premise resolved, sending 3 spurious notices, because nothing told it to stop.)

### 2. Remediate first, page only on sustained failure

Detection stays honest on every cycle, but the *disruptive action* defers until the failure persists across N consecutive cycles (patient mode). Rationale: oscillating chains self-recover in minutes; a force-reconnect on a self-limiting blip is net-harmful. Measure your system's real self-recovery window before choosing N (one chain's 94-min observatory run showed ≤3 min self-recovery → N=2 cycles at 5-min interval).

When the trigger aggregates several independent sources into one verdict (not a single health check), the cross-source agreement fraction is a *second, separate* parameter from N — don't default to "all sources must agree." An all-or-nothing gate produces a false negative on exactly the correlated-but-partial incident the watchdog exists to catch, because real failures rarely take every source down at once (real case: a 9-source collection-health gate required 9/9 failing and missed a live incident sitting at 6/9; recalibrating against the actual incident data to a ≥60%-of-sources threshold caught it while fixture testing at 0%/11%/100% confirmed it still tolerated a single-source blip). Calibrate breadth (what fraction must agree) against real historical failure data the same way you calibrate depth (N) — a threshold picked from what "sounds strict enough" is a guess, not a calibration.

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

Before deploying or integrating an existing periodic observer, apply
`references/probe-cost.md`. Require bounded observation work and a completed native
launchd round; importing an existing script does not certify its cost or verdict.

Before declaring configuration active, use the native readback helper through
`references/native-job-readback.md`. Read explicit ENV from the job's own block;
do not take the first matching key from default or inherited environment sections.
Verify the completed business round separately from registration or process state.

1. **Location**: user agent → `~/Library/LaunchAgents/` (GUI session context: can `open` apps, show notifications); system daemon → `/Library/LaunchDaemons/` (root, no GUI access). Choose by whether the job needs the user's GUI session, not by habit.
2. **plist**: for periodic jobs start from `assets/launchagent.template.plist`; for event jobs follow `references/event-driven-observers.md` and its plist reference. Validate with `plutil -lint`. `ProgramArguments` element 0 = absolute path; never rely on shell PATH inheritance.
3. **Load/reload**: before replacing or stopping an existing job, apply the ownership, active-work and pending-intent checks in `references/event-driven-observers.md` § Deployment SOP. For an authorized idle job, load with `launchctl bootstrap gui/$(id -u) <plist>`; after a plist edit, `bootout` then `bootstrap`. Request one run of an idle owned job with `launchctl kickstart gui/$(id -u)/<label>`; `-k` terminates an existing instance and is not a routine test. **`kickstart -k` on an instantly-exiting job is a throttle trap, not a latency probe**: the kill+respawn collides with the 10 s `ThrottleInterval`, producing `spawn failed, error=89 (ECANCELED)` and respawns on 10.01–10.03 s beats, so the call blocks ~11–20 s. Measured 2026-10-20: 108/110 gaps at 10.01–10.03 s while plain `kickstart` returned sub-second. Do not read that blocking as launchd congestion.
4. **Logs**: `StandardOutPath`/`StandardErrorPath` are non-negotiable (without them failures vanish), plus in-script log rotation (cap ~1 MB).
5. **Idempotency guard**: re-running your deploy must not double-install. For periodic jobs only, use `scripts/new-launchagent.sh <label> <script> <interval>` after the replacement checks above; it can boot out a loaded job. For event jobs use the event SOP. In both cases, verify loaded configuration through the native helper and completed work separately.
6. **TCC / Full Disk Access**: a LaunchAgent reading protected files needs a working grant for its effective permission subject. Use `macos-permissions` to inspect TCC attribution and verify a protected read from the actual job; the shell's interpreter path alone does not decide this.
7. **Batch throttling by default**: any watchdog loop that spawns work (replays, fuzz, batch scans, parallel API calls) needs an explicit rate cap as a default parameter, not a later optimization. To the machine, an unthrottled loop and a runaway process are indistinguishable (real case: an unthrottled test replay forked 1,041 processes/sec for 7 minutes and pushed the die to 83 °C).
8. **Browser side-effect acceptance**: a successful data fetch alone does not prove a browser-backed watchdog is ready. The deploying operator must declare a budget for task-owned spaces and pages, then independently inventory them across multiple rounds, including injected initialization and cleanup failures. Counts must stay within that lifecycle budget; protect user-owned and unknown-origin pages throughout. If the task requires no focus stealing, independently observe the foreground app and visible windows during those rounds; CDP success is not focus evidence. For ego lite lifecycle, locking, ownership conflicts and cleanup readback, load the named Skill `ego-lite-use` when installed. Otherwise use the owning browser tool's documented lifecycle while meeting the same budget and readback requirements. Missing resource observations, or missing focus observations when no focus stealing is required, leave acceptance incomplete.
9. **Sub-minute `StartInterval` is a BTM transition tax — prefer a `KeepAlive` loop for high-frequency probes.** Every periodic firing enters running and then exited; `backgroundtaskmanagementd` converts each into a store write plus a 250 ms-coalesced distributed `userDataDidChange` broadcast that drives LoginItems.appex full monitor rebuilds — the amplifier behind the 2026-10-06/10-17 watchdog panics. A persistent job running an in-process loop (period = max(interval, runtime+1s)) keeps the cadence with zero steady-state transitions. Measured effect of converting the three biggest offenders: BTM-triggering monitor updates 0.45/s → ~0.20/s.
10. **macOS zeroes `XPC_SERVICE_NAME` for spawned children — identity guards break when you wrap the probe.** A launchd job process reads its own label, but every child it spawns (bash/sh/python) reads `XPC_SERVICE_NAME=0`, and `export` does not survive `exec` (measured on 27.0.1 with a dedicated probe job). A script whose guard is `[ "$XPC_SERVICE_NAME" = <label> ]` passes only when the script IS the job process. Wrap it in a loop/driver and the probe becomes a grandchild: the guard rejects 100% of iterations while `launchctl` shows `state=running` — one collector produced zero rows for 75 minutes. Pass identity through a different variable the driver sets (e.g. `<PROJECT>_CALLER_LABEL` via argv) and have the guard accept it as an alternative; direct execution stays refused because neither variable is set in a human shell.

### Persistent Python runtime

For a persistent Python job, separate dependency preparation from normal startup:

- **Install/upgrade:** use the owning installer's explicit prepare action to
  create a persistent environment outside uv's cache from retained locked inputs.
  Bind the selected Python series, complete frozen distribution set and base
  interpreter to that installation. Keep dependency changes in this phase.
- **Reuse:** execute the environment's actual Python to compare its series and
  complete installed distribution names/versions with those frozen inputs, and
  verify its resolved base Python still exists and runs. A ready marker or a
  matching Python series alone does not validate the environment. Reject an empty,
  mismatched or broken environment; resume the authorized prepare action rather
  than silently accepting it.
- **Run:** register the absolute environment Python path in `ProgramArguments`
  and invoke the service entry directly. Fail visibly when that runtime is missing
  or invalid; do not silently fall back to `uv run`, another interpreter, or an
  install during startup. Check inherited variables and startup hooks when they
  could redirect the selected runtime. Finite maintenance scripts may still use
  their declared `uv run` workflow.

Before switching an existing job, retain the ownership, active-work and pending
intent checks from § Deploy. Preserve its canonical configuration and rollback
target; compare the live configuration with the inspected version immediately
before replacing it, and stop on drift. Use the existing native readback and
completed business-round acceptance through the actual consumer; a marker, PID
or HTTP health response does not replace that result. The deploying operator
owns these checks; this Skill does not supply a generic environment installer.

Keep permission attribution separate from Python environment selection. When a
native executable needs an already authorized launcher's FDA identity, follow
`macos-permissions` and its
[measured uv attribution case](../macos-permissions/references/uv-fda-trap.md).
If the real protected read proves that exact `uv` launcher is required, retain
the verified responsibility chain. For a native executable, the installed uv's
supported `uv run --no-project --offline --no-cache -- <absolute-binary> ...` form
can avoid the shared main cache while preserving that launcher; verify the same
protected operation from the real job before accepting it. Do not generalize this
exception to Python dependency startup. `--no-cache` uses a temporary cache; it
does not promise zero temporary disk use or, for other Python tasks, zero downloads.

Consult [uv's environment-use guidance](https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment)
for direct environment execution and its
[cache documentation](https://docs.astral.sh/uv/concepts/cache/) for `--no-cache`.

## Stop semantics (the deprecated trap)

Before stopping or replacing a job, apply the ownership and active-work checks
in § Deploy and the current task's authorization boundary.

| Intent | Command |
|---|---|
| Stop now, allow re-bootstrap later | `launchctl bootout gui/$(id -u)/<label>` (daemon: `sudo launchctl bootout system/<label>`) |
| Prevent later loads across login (stop a loaded job separately) | `launchctl disable user/$(id -u)/<label>` (reverse: `enable`) |
| Edit then reload | `bootout` → bounded exact-service unload observation through the Deployment SOP → edit plist → `bootstrap` |

Use `bootstrap`/`bootout` instead of deprecated `load`/`unload`. When a job
must remain disabled across later loads, apply `disable`; stopping an instance
alone does not establish that persistent override.

A temporary job that stays loaded keeps paying the § Deploy-9 transition tax
(its every firing still feeds BTM broadcasts). When the task it served is
done, `disable` it — do not leave a dead-purpose periodic job running because
stopping it felt irreversible: `disable` is fully reversible (`enable` +
`bootstrap`), and the plist can stay on disk as the re-enable path.

### Decommissioning a job permanently

Retiring a job's whole line (job + plist + tool) is a different operation from
stopping one, and it is safe to be thorough: every step except the last is
recoverable.

1. **Stop and capture.** `bootout` a loaded job; an already-disabled idle job
   has nothing running. Read the plist once (`plutil -p`) and keep its content
   in the session record — it names the tool path, log paths, and schedule you
   are about to remove.
2. **Remove the plist** from `~/Library/LaunchAgents/`. A leftover
   `launchctl disable` override for the label is inert once the plist is gone;
   do not chase it.
3. **Prove zero references before deleting the tool**: grep the owning repo
   for the label and the tool name. Hits confined to the tool's own directory
   mean nothing imports, schedules, or documents it.
4. **Delete the tool through the repo's normal PR flow** — git history is the
   backup. After the merge lands, remove regenerable residue (`__pycache__`)
   from the checkout.
5. **Keep the data/log directory by default** (wherever the plist pointed,
   e.g. `~/.local/share/<tool>/`): it is small, it holds the config a revival
   would need, and deleting it is the only irreversible step — offer it
   explicitly instead of cleaning silently.

Measured 2026-10-20 (wechat-print retirement): an every-minute
`StartCalendarInterval` job kept incurring § Deploy-9 BTM tax while emitting
nothing but failure logs for six days.

## Troubleshooting quick map

| Symptom | First check |
|---|---|
| "It re-launches the app I quit" | URL-scheme/`open` calls missing the process-alive gate (clause 4) |
| "It spams the same repair every few minutes" | No exhausted-round cool-down (clause 3); also check the ladder's failure path doesn't reset its dead-counter |
| "It reports healthy through a real outage" | Health check certifies only the path it probes — one green probe ≠ all planes healthy (add the second plane's probe) |
| "bootout didn't stick / it came back" | Confirm the exact domain/service target and who bootstrapped it again; for a persistent stop follow § Stop semantics |
| Silent no-runs | `StandardErrorPath` missing → failures invisible; then `log show --predicate 'process == "launchd"' --last 15m` |
| "log mtime is fresh" but the job is actually failing | out.log all-green is **not** health — a failed pass may write nothing (`set -e` + prints-verified-only-on-success), so the last-success timestamp stays fresh forever. Judge the **failure** path (err.log / last-exit status), not success-side freshness (Pattern 7) |
| After `bootout`+`bootstrap`, "the data file has a recent row" is not proof the new job works | The OLD job's final row can land inside your freshness window (real case 2026-10-20: a probe conversion passed a 75 s freshness check while the new job's every iteration was rejected by its identity guard for 75 min). Anchor verification to the NEW job: rows timestamped after the new PID's start, or per-iteration status rows; `state=running` never proves the collector writes |
| Works interactively, fails under launchd | TCC/FDA on the wrong interpreter; PATH assumptions in `ProgramArguments` |
| Observation becomes slower as history grows | Audit cold, warm and delta work using `references/probe-cost.md`; caching bytes does not bound parsing or queries |

Details and the sanitized war stories behind each clause: `references/quiet-watchdog-patterns.md`.
