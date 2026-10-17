# launchd plist Reference (macOS, verified Ventura+)

Field-level reference for watchdog plists. Scope: what a periodic or event-driven self-healing job needs — not the full launchd surface (sockets, MachServices).

## Domains and placement

| Kind | plist dir | Domain target | Context |
|---|---|---|---|
| LaunchAgent | `~/Library/LaunchAgents/` | `gui/$(id -u)` | User GUI session: can `open` apps/URL schemes, show notifications, read user TCC grants |
| LaunchDaemon | `/Library/LaunchDaemons/` | `system` (sudo) | Root (or `UserName`/`GroupName` override); no GUI session, no per-user TCC |

Label convention: reverse-DNS (`com.example.thermal-watch`). The label is the job's only handle — every `launchctl` verb targets it.

## Core keys

```xml
<key>Label</key>                <string>com.example.my-watch</string>
<key>ProgramArguments</key>     <array><string>/bin/bash</string><string>/ABS/path/to/script.sh</string><string>heal</string></array>
<key>RunAtLoad</key>            <true/>                  <!-- also fire once at bootstrap/login -->
```

Select a trigger through [the event workflow](event-driven-observers.md).
For an event-triggered job, omit the timer:

```xml
<key>WatchPaths</key><array><string>/ABS/PATH/TO/watched-dir</string></array>
```

For a justified periodic observer, use a timer instead:

```xml
<key>StartInterval</key><integer>300</integer>
```

Treat `WatchPaths` as a lossy launch hint; it supplies no event payload or
exactly-once queue. Apply the [event workflow's deployment and acceptance](event-driven-observers.md)
before relying on it. Do not infer quiet scheduling from `RunAtLoad` alone:
`KeepAlive` can also cause an initial launch.

- `ProgramArguments` element 0: absolute path to the executable (or `/bin/bash` + script path as element 1). PATH inheritance is not available — Homebrew binaries need their absolute path or an explicit `EnvironmentVariables/PATH`.
- Scripts need a shebang AND the execute bit; a missing `+x` fails silently (see Logging).
- ⚠️ **`plutil -replace ProgramArguments.0 -string X` does not replace index 0 — it APPENDS an element.** Measured: an existing `[daemon.sh]` became `[recorder.sh, daemon.sh]`, silently turning the original script into an *argument* of the new one (it kept working only because the wrapper ignored its args). To repoint a job, rewrite the whole array with `python3` + `plistlib` (or `plutil -remove` then `-insert`), then read it back with `plutil -p` before reloading.

### KeepAlive (respawn policy) — usually NOT what a periodic watchdog wants

`KeepAlive` turns a one-shot into a supervised service. For a StartInterval watchdog (runs, exits 0, sleeps), omit it entirely.

| Form | Effect |
|---|---|
| `KeepAlive: true` | Restart whenever the process exits, for any reason |
| `KeepAlive: { SuccessfulExit: false }` | Restart after non-zero exit; can also cause an initial launch |
| `KeepAlive: { NetworkState: true }` | Do not use as a reconnect signal: current `man launchd.plist` says it is no longer implemented |

### ThrottleInterval (respawn rate limit)

Minimum seconds between respawn attempts after an exit. Default 10.

- Guards against crash-loop storms: a `ThrottleInterval` of 1 with a crashing job produced 37 MB of identical error logs and, in another real incident, 30+ zombie processes because the port wasn't released before the respawn.
- **It is a fixed delay with no backoff**, and it only throttles *process respawn* — a job that runs, spams, and exits 0 is completely outside its reach. Escalating silence must be implemented in the script (see `quiet-watchdog-patterns.md` § auto-cooldown).

## Calendar deadlines and recovery

Apply this READ-DO check only to an already-authorized persistent calendar job with delivery deadlines. The task's operator and existing runner own recovery; reuse its due-time, acknowledgement and stop records rather than adding another scheduler or requiring a new state file per task.

Check the current host's `man launchd.plist`: `StartCalendarInterval` coalesces intervals missed during sleep into one wake event; this is not a guarantee of punctual execution while powered off or logged out. `RunAtLoad` launches once when loaded, defaults to false, and the manual discourages speculative startup work. Use it here only for a bounded due-state check at bootstrap/login, not an unconditional send or full historical replay.

1. Read the task's current authorization, STOP/cancel condition, next due time, last actual-output ACK and any pending/unknown delivery outcome. Compare `date +%s` with the due time converted to the same epoch using the task's declared timezone. Stop on cancellation; do not resend an ACKed round or one with unknown prior delivery. If not yet due, exit without sending. Missing state stays unknown.
2. If overdue, coalesce missed rounds into one catch-up decision under the existing task policy. Do not create a new schedule for an expired deadline or send one message per missed interval. A startup invocation only proves that the check ran.
3. Before the authorized catch-up, verify the currently available documented channel and exact intended target through their owning tool. An old successful canary does not establish current reachability. If the documented endpoint is unavailable, retain an explicit failure/unknown result; do not guess another socket, restart a shared service or blindly resend an unconfirmed attempt.
4. Separate the following evidence. Do not promote a lower layer into a higher one:

   | Layer | Required observation |
   |---|---|
   | Native job | Expected configuration readback, plus the completed native run's exit/failure evidence; registration or a process alone is insufficient |
   | Dispatch and consumption | The specific attempt's acceptance receipt **and** evidence that the exact target actually consumed it; a transport ACK alone is insufficient |
   | User result | The requested output actually delivered to the user; for a periodic report, the real report and its timestamp, not the reminder or canary |

5. Record the task's completion ACK only after the required user result, with its actual evidence and time. A later catch-up does not erase a missed deadline. To claim recovery, observe an authorized overdue bootstrap/login path through its required layers; when only configuration or startup passed, report those limits and the remaining delivery failure.

The native readback helper checks configuration only; it cannot enforce due/ACK policy or inspect user reports. The operator must inspect the owning task's records and actual output. Missing consumer evidence leaves that layer unverified.
Apply its [supported readback boundary](native-job-readback.md) before using a helper result as calendar-configuration evidence.

## Logging

```xml
<key>StandardOutPath</key>  <string>/ABS/PATH/TO/logs/my-watch.out.log</string>
<key>StandardErrorPath</key><string>/ABS/PATH/TO/logs/my-watch.err.log</string>
```

Without these, a failing job leaves no trace anywhere. launchd does not capture output by default. The script should additionally self-rotate its own application log (cap ~1 MB, keep 1 backup) — `Standard*Path` files only grow.

Inspect what launchd itself did with the job:

```bash
log show --predicate 'process == "launchd"' --last 15m | grep <label>
```

## Resource and environment control

| Key | Use |
|---|---|
| `Nice` (1-20) | Lower CPU priority; watchdogs should yield to interactive work |
| `LowPriorityIO: true` | Lower I/O priority for background scans |
| `ProcessType: Background` | Hint the scheduler this is non-interactive |
| `EnvironmentVariables` | Explicit env; launchd jobs do NOT inherit the user's shell env (a watchdog that reads proxy vars from ~/.zprofile works interactively and fails under launchd) |
| `WorkingDirectory` | Pin cwd if the script uses relative paths |
| `UserName`/`GroupName` | (LaunchDaemon only) run as a non-root user |

## TCC / permissions under launchd

When a LaunchAgent can read protected files interactively but fails under launchd, inspect the
actual TCC requester and any existing grant through `daymade-macos:macos-permissions`.
Its automated Full Disk Access route owns the repair and background readback; its `uv`
attribution reference records the observed case. Do not infer the
requester from the dialog title or assume every unsigned binary behaves like that case.

## launchctl command reference

| Intent | Command |
|---|---|
| Load | `launchctl bootstrap gui/$(id -u) <plist>` (daemon: `sudo launchctl bootstrap system <plist>`) |
| Stop now | `launchctl bootout gui/$(id -u)/<label>` |
| Stop and keep stopped across login | `launchctl disable user/$(id -u)/<label>` (reverse: `launchctl enable …`) |
| Re-load after editing plist | `bootout` → edit → `bootstrap` (active state must match disk) |
| Request one run of an idle owned job | `launchctl kickstart gui/$(id -u)/<label>` |
| Is it loaded? exit code of last run? | `launchctl list | grep <label>` (PID-or-`-`, last exit status, label) |

Check exact ownership, active work and pending intent through the
[deployment workflow](event-driven-observers.md) before replacement or stopping.
Do not use `kickstart -k` as a routine test: it terminates an existing instance.
Use `bootstrap`/`bootout` instead of deprecated `load`/`unload`; use `disable`
when the job must stay disabled across later loads.

## Verification commands

Before declaring a plist edit active, run `scripts/inspect_native_job.py` with
the exact expected plist and follow `native-job-readback.md`. Require explicit
job ENV and configured argv/path matches; do not use a first-match regex over
the whole `launchctl print` output. Apply the scheduling checks in
[native readback](native-job-readback.md), including absent expected keys.
Verify completed work separately.

```bash
plutil -lint <plist>                        # syntax
plutil -p <plist>                           # effective contents (catches type errors)
launchctl list | grep <label>               # loaded + last exit status
stat -f '%SB' <plist>                       # plist birth time (when this watchdog was installed)
log show --predicate 'process == "launchd"' --last 15m | grep <label>
```
