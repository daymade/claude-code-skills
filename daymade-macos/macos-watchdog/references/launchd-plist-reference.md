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

## TCC / permissions under launchd (the `uv` Full-Disk-Access trap)

LaunchAgent 的 job 在用户 GUI 会话里跑，能 `open` app、读用户 TCC 授权——但**无签名可执行文件是个例外**，`uv run` 是最高频的踩坑点。

- **症状**：LaunchAgent 反复弹「`python3.x` would like to access data from other apps」（Full Disk Access / `kTCCServiceSystemPolicyAllFiles`），点“允许”也没用、每个周期又弹。同一个脚本在交互式终端跑却不弹。
- **为什么**：发起方是 `uv` 二进制本身，不是它挑的 python、不是脚本、不是会话类型（`LimitLoadToSessionType`/`asuser` 都改不了）。launchd 起的 `uv` 是根进程，**没有带 FDA 的父进程可继承**；交互式跑不弹是因为终端（Ghostty/Terminal）本身有 FDA、`uv` 作为子进程继承了它。
- **修复**：给 `uv` 二进制（绝对路径，如 `~/.local/bin/uv`）授 Full Disk Access——**不是 python**（python 版本随 uv 漂移）。一次覆盖所有 `uv run` 的 LaunchAgent。授权按二进制路径记，uv 升级换路径后会失效、需重授。
- **判定**：`log show --predicate 'subsystem=="com.apple.TCC"'` 的 `from Sub:{...}` 是发起方；`sudo sqlite3 '/Library/Application Support/com.apple.TCC/TCC.db' "select client,auth_value from access where service='kTCCServiceSystemPolicyAllFiles';"` 看授权态（SIP 保护该库只读，授权只能走 GUI）。弹窗显示的名字是当前解释器、会漂移，别拿它当授权对象。
- 完整诊断流程见 `capture-screen/references/permission-triage-template.md` 的 Full Disk Access 专项。

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
