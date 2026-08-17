# Quiet-Watchdog Patterns

Design patterns for the four contract clauses in SKILL.md, each with the sanitized war story that produced it. Every story is real; identifiers are generalized (the lesson transfers, the names don't).

## Contents
- Pattern 1: Premise-state self-check
- Pattern 2: Patient mode (defer disruption, not detection)
- Pattern 3: Escalating auto-cooldown
- Pattern 4: Never resurrect a user-quit app
- Pattern 5: Health checks certify only the plane they probe
- Pattern 6: Batch loops throttle by default

## Pattern 1: Premise-state self-check

**Pattern.** First lines of every run: test the premise. Not holding → `exit 0` silently. The check must be *state*, not *schedule* — "I was told to run" is not evidence the job is still needed.

**War story.** A watcher existed to detect "config has switched back to main." The switch happened; the watcher kept firing every interval for 2 hours, sending 3 notifications that all asserted the switch had NOT happened — because the notification text was a fixed string written when the watcher was created, and nothing re-read the actual state. Fix: premise check at script start (`=main → self-stop, no notice`); notification text generated from the live state, never from a frozen template. The lifecycle of a monitor binds to its premise state — `launchctl disable` from a human is symptom relief, not the mechanism.

## Pattern 2: Patient mode

**Pattern.** Split *detection* from *disruption*. Detection runs honestly every cycle. The disruptive action (reconnect, restart, force-refresh) fires only after the dead state persists across N consecutive cycles, counted in a state file with a staleness window (a counter from before a sleep/wake gap doesn't count).

**Why.** The failure mode that trains people to ignore a watchdog is the false-positive *action*, not the false-positive *log line*. One measured chain oscillated: bad phases self-recovered in ≤3 minutes, and force-reconnect was never what fixed it — the chain recovered even right after the watchdog logged "all levels exhausted." Disruptive heal on a self-limiting blip is net-harmful: it force-drops connections that would have cleared themselves.

**Calibration.** Measure your system's self-recovery window first (run a passive sampler for a few hours — count how long bad phases actually last), then set N so N×interval comfortably exceeds the window. N=2 at 5-min interval for a ≤3-min window.

## Pattern 3: Escalating auto-cooldown

**Pattern.** When the full remediation ladder fails, record an exhausted round and stand down for an escalating tier (e.g. 30 min → 2 h → 6 h). During cool-down: no probes, no remediation, no notifications, entry logged. On expiry: one retry round. Success clears the counter; failure advances the tier.

**War story.** A proxy-repair watchdog's ladder ended with `notify "all failed, needs human"` and **did not reset its dead counter**. Next cycle the counter still exceeded the patient threshold → full ladder again → notify again. On an unfixable network (real-IP reachable, domain path hijacked — a captive portal the watchdog cannot fix), this re-ran the entire ladder plus a chat notification every 5 minutes forever, each round re-launching the proxy app to the foreground. The user's report: "it keeps opening the app; I quit it and it comes back." `ThrottleInterval` cannot fix this — the job exits 0 every time; the spam is application-level, so the silence must be too.

**Implementation.** `scripts/watchdog-cooldown.sh` — source and wire three call sites: gate at entry (`paused_any`), record on ladder exhaustion (`record_exhausted`), clear on real heal (`clear_exhausted`). Manual `pause`/`resume` subcommands included as the human override.

## Pattern 4: Never resurrect a user-quit app

**Pattern.** Any remediation that invokes a GUI app (URL scheme, `open -a`, AppleScript activate) goes through a gate:

```bash
sr_open() {  # name yours after the target
    paused_any && return 1
    pgrep -x "$TARGET_PROCESS" >/dev/null 2>&1 || return 1   # user quit: do NOT relaunch
    open -g "$1"                                             # -g: never steal foreground
}
```

**Why both halves.** `open <url-scheme>` launches the app when it isn't running — the watchdog becomes the resurrector the user fights. And `open` without `-g` foregrounds the app even when it was already running, so every remediation cycle pops a window. Cleanup traps (`trap … EXIT`) that "ensure connected on abort" must pass the same gate — the trap fires exactly when the user may have just quit the app to make the loop stop.

## Pattern 5: Health checks certify only the plane they probe

**Pattern.** Enumerate the traffic planes your watchdog's service carries (proxied vs direct, read vs write, control vs data) and probe each one. "Healthy" must name the plane: `proxy-plane=ok direct-plane=dead`.

**War story.** A proxy watchdog probed only `google.com/generate_204` through the tunnel. The tunnel's domestic-direct forwarding plane broke for 2+ hours while the proxied plane stayed healthy — domestic domains all failed TLS while overseas traffic flowed. The watchdog logged "Proxy already healthy" through the entire outage. Second story, same shape: the chain intermittently *dropped* ~40-50% of connections instead of dying, so a single probe passed ~60% of the time during a real outage — fixed by N=8 samples requiring ≥6 successes per cycle. A green check certifies the path it probed, at the rate it probed, nothing more.

## Pattern 6: Batch loops throttle by default

**Pattern.** Any watchdog that spawns work in a loop (replays, fuzzing, batch scans, batch API calls) takes batch-size / interval / concurrency caps as first-class parameters with conservative defaults. Ask when writing the loop: "how many new processes/requests/files per second × how long will this run?"

**War story.** A perfectly correct hook-replay test ran with no throttle: fork 1,041/sec for 7 minutes, die temperature 83.1 °C, and a system policy daemon became the day's top CPU consumer from the fallout. The test logic was right; to the machine, an unthrottled loop and a fork bomb are the same thing. The inverse diagnostic habit too: when a machine runs hot, ask "is some test/batch running unthrottled?" before hunting runaway processes.
