# Automate a Full Disk Access repair

The success condition is the **named background job reading the protected data in its real launch context**. A toggled switch, HTTP 200, an interactive run, or a healthy process by itself does not prove that result.

## 1. Bind the exact job and permission subject

Read the job's plist or installer, executable paths, process tree, and one protected read the user expects. Compare an interactive run with a real `launchctl bootstrap gui/<uid>` run. Use TCC logs to distinguish the *responsible* launcher from the *accessing* child; the dialog title may name the wrong one. Read the system TCC database **only for relevant exact paths** if it is accessible. `auth_value=2` means an existing grant; an unreadable database means unknown, not denied. The SKILL.md attribution section has the log and database commands.

## 2. Reuse an existing grant when the owning installer supports it

Before opening System Settings, check whether the job's actual launcher already has Full Disk Access. On one Mac, `~/.local/bin/uv` had `kTCCServiceSystemPolicyAllFiles auth_value=2`; a Go reader launched as its direct child under a user LaunchAgent then read the account database. This is **one observed machine and one reader**, not a macOS-wide promise that any FDA-bearing app can launch any child.

In the verified Mac WeChat reader case, the owning repository's `mac-launchagent.py` installer supports an optional `--uv-launcher` mode. Read that repository's current README, installer and `--help`, then use its installation and rollback path. Do not invent a second instance by changing `--base`: the current installer has one fixed LaunchAgent label and uses `--base` for its health check. Stop a manually running listener before installation. Run the installed reading Skill against the background service to read the expected account and one known message; verify a real media item separately if media is in scope. If the existing grant or the actual protected read fails, use step 3.

Stop after the background read works. Adding another FDA entry would not improve that result.

## 3. Add a new grant through System Settings when needed

Apple's [Privacy & Security guide](https://support.apple.com/en-mk/guide/mac-help/mchl211c911f/mac) describes Full Disk Access as a System Settings list: use Add, select the app, then Open. `open 'x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles'` opened the correct pane on the tested Mac. Use an available native Computer Use tool to inspect the current window before clicking, and target the exact executable path found in step 1. If the pane requests Touch ID or a password, continue only with the user's available system-authentication method; never echo or save a supplied password in a file or report.

On the tested Mac, `mcp__cua_repl` transport was closed; `mcp__kimi_cu` could inspect and click System Settings and its native file picker. Reobserve after every click. A tool's `ok:true` alone does not prove the UI changed, and a reported typing error does not prove a secure field stayed empty. When background input misses a password field, foreground System Settings, focus that field and use an available permitted native input channel; System Events keystrokes reached the focused field in this test. Inspect masked input before submitting, then read the grant and run the job.

Two GUI routes completed with a dedicated, non-sensitive probe reading a TCC-protected file **as a user LaunchAgent** on macOS 26.6.2:

| Starting state | GUI action | Independent result |
|---|---|---|
| An exact executable already appears in the FDA list with its switch off | Select its row, switch it on, and complete macOS authentication | The probe's system TCC row changed from `auth_value=0` to `2`; the same LaunchAgent changed from `Operation not permitted` / exit 13 to a protected read / exit 0. |
| No row exists for the exact executable | Add → select the executable in a sidebar-reachable folder → Open | A new system TCC row appeared with `auth_value=2`; a separate LaunchAgent read the protected file and exited 0. |

The file-picker test selected the **actual probe executable** from Downloads. Copying a different job's binary there would grant the copy's path, not its original path. For a hidden executable, Go to Folder opened and accepted the full path, but the local desktop-input guard blocked the final Return; that path was **not** validated. Do not switch tools to evade a blocked input. Use the owning installer's already-authorized launcher if it works, or report the exact remaining picker interaction.

After any new grant, restart the requesting process. Read back the exact system TCC entry when available, then run the protected read through the actual LaunchAgent and the user's normal client. Only the latter proves the job works; if the database is unreadable, the live read still decides the result.
