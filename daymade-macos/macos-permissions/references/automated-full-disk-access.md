# Automate a Full Disk Access repair

The success condition is the **named background job reading the protected data in its real launch context**. A toggled switch, HTTP 200, an interactive run, or a healthy process by itself does not prove that result. This route covers an explicitly authorized local machine and job; it does not require a second declaration that the user owns an account already identified as theirs.

## 1. Bind the exact job and permission subject

Read the job's plist or installer, executable paths, process tree, and one protected read the user expects. Compare an interactive run with a real `launchctl bootstrap gui/<uid>` run. Use TCC logs to distinguish the *responsible* launcher from the *accessing* child; the dialog title may name the wrong one. Read the system TCC database **only for relevant exact paths** if it is accessible. `auth_value=2` means an existing grant; an unreadable database means unknown, not denied. The SKILL.md attribution section has the log and database commands.

## 2. Reuse an existing grant when the owning installer supports it

Before opening System Settings, check whether the job's actual launcher already has Full Disk Access. On one Mac, `~/.local/bin/uv` had `kTCCServiceSystemPolicyAllFiles auth_value=2`; a Go reader launched as its direct child under a user LaunchAgent then read the account database. This is **one observed machine and one reader**, not a macOS-wide promise that any FDA-bearing app can launch any child.

In the verified Mac WeChat reader case, the `mac-launchagent.py` installer in the owning code repository has an optional `--uv-launcher <absolute uv path>` mode. Read that repository's current README and `--help`; use its installer and rollback instead of inventing a second wrapper in this Skill. It has **one fixed LaunchAgent label**: `--base` selects the health-check address, not a second instance or a new listening port. Stop a manually running listener before installation. When replacing a loaded LaunchAgent, the installer saves its prior binary and plist, restarts it on failure, and checks that it becomes ready. A successful install checks the exact `uv` LaunchAgent process, its direct `chatlog` child, the listener, and database readiness. Then run the installed reading Skill against that service to read the expected account and one known message; verify a real media item separately if media is in scope. If the existing grant or the actual protected read fails, use step 3.

Stop after the background read works. Adding another FDA entry would not improve that result.

## 3. Add a new grant through System Settings when needed

Apple's [Privacy & Security guide](https://support.apple.com/en-mk/guide/mac-help/mchl211c911f/mac) describes Full Disk Access as a System Settings list: use Add, select the app, then Open. `open 'x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles'` opened the correct pane on the tested Mac. Use an available native Computer Use tool to inspect the current window before clicking, and target the exact executable path found in step 1. If the pane requests Touch ID or a password, continue only with the user's available system-authentication method; never echo or save a supplied password in a file or report.

The **GUI completion path was not validated end to end in the 2026-09-25 case**: the native file chooser lost focus and System Settings later exposed no Accessibility window. A tool's `ok:true` did not mean a secure field received input. If the computer-use transport closes, try another available native UI channel once; if the same picker or window failure recurs, change route or report the exact remaining interaction. Do not keep replaying clicks, edit `TCC.db`, or claim that opening the pane granted permission.

After any new grant, restart the requesting process. Read back the exact system TCC entry when available, then run the protected read through the actual LaunchAgent and the user's normal client. Only the latter proves the job works; if the database is unreadable, the live read still decides the result.
