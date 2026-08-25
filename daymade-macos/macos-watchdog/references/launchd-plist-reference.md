# launchd plist Reference (macOS, verified Ventura+)

Field-level reference for watchdog plists. Scope: what a periodic self-healing job needs — not the full launchd surface (sockets, MachServices, WatchPaths).

## Contents
- Domains and placement
- Core keys (identity / schedule / respawn)
- Logging
- Resource and environment control
- launchctl command reference
- Verification commands

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
<key>StartInterval</key>        <integer>300</integer>   <!-- seconds between runs -->
<key>RunAtLoad</key>            <true/>                  <!-- also fire once at bootstrap/login -->
```

- `ProgramArguments` element 0: absolute path to the executable (or `/bin/bash` + script path as element 1). PATH inheritance is not available — Homebrew binaries need their absolute path or an explicit `EnvironmentVariables/PATH`.
- Scripts need a shebang AND the execute bit; a missing `+x` fails silently (see Logging).

### KeepAlive (respawn policy) — usually NOT what a periodic watchdog wants

`KeepAlive` turns a one-shot into a supervised service. For a StartInterval watchdog (runs, exits 0, sleeps), omit it entirely.

| Form | Effect |
|---|---|
| `KeepAlive: true` | Restart whenever the process exits, for any reason |
| `KeepAlive: { SuccessfulExit: false }` | Restart only on crash (non-zero exit) |
| `KeepAlive: { NetworkState: true }` | Restart when network connectivity changes (e.g. after wake) |

### ThrottleInterval (respawn rate limit)

Minimum seconds between respawn attempts after an exit. Default 10.

- Guards against crash-loop storms: a `ThrottleInterval` of 1 with a crashing job produced 37 MB of identical error logs and, in another real incident, 30+ zombie processes because the port wasn't released before the respawn.
- **It is a fixed delay with no backoff**, and it only throttles *process respawn* — a job that runs, spams, and exits 0 is completely outside its reach. Escalating silence must be implemented in the script (see `quiet-watchdog-patterns.md` § auto-cooldown).

## Logging

```xml
<key>StandardOutPath</key>  <string>/Users/&lt;username&gt;/Library/Logs/my-watch.out.log</string>
<key>StandardErrorPath</key><string>/Users/&lt;username&gt;/Library/Logs/my-watch.err.log</string>
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

## launchctl command reference

| Intent | Command |
|---|---|
| Load | `launchctl bootstrap gui/$(id -u) <plist>` (daemon: `sudo launchctl bootstrap system <plist>`) |
| Stop now | `launchctl bootout gui/$(id -u)/<label>` |
| Stop and keep stopped across login | `launchctl disable user/$(id -u)/<label>` (reverse: `launchctl enable …`) |
| Re-load after editing plist | `bootout` → edit → `bootstrap` (active state must match disk) |
| Force one immediate run | `launchctl kickstart -k gui/$(id -u)/<label>` |
| Is it loaded? exit code of last run? | `launchctl list | grep <label>` (PID-or-`-`, last exit status, label) |

Deprecated: `load`/`unload`. `unload` on Ventura+ leaves the job re-loadable by `RunAtLoad` while the plist stays in place — the "stopped" watchdog fires again. `bootstrap`/`bootout` are the modern pair.

## Verification commands

```bash
plutil -lint <plist>                        # syntax
plutil -p <plist>                           # effective contents (catches type errors)
launchctl list | grep <label>               # loaded + last exit status
stat -f '%SB' <plist>                       # plist birth time (when this watchdog was installed)
log show --predicate 'process == "launchd"' --last 15m | grep <label>
```
