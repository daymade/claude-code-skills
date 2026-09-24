# The `uv`-in-launchd Full-Disk-Access trap

An observed permission problem on this machine: a LaunchAgent running `uv run`
repeatedly pops "python3.x would like to access data from other apps", and clicking Allow does
not stop it. This is the applied case behind `../SKILL.md`'s attribution trap — same root cause
family as Claude Code issues #74234 / #84948 / #86706 (per-version binary path).

## Symptom

A background job (LaunchAgent) prompts every few minutes; the same command run interactively in a
terminal does not prompt. In this case the dialog named `python3.11` / `python3.14` / a bare version
number rather than `uv`.

## Root cause

The requester is the **`uv` binary itself**, not the python it picks, not the script, not the
session type. In the TCC log:

```
/usr/bin/log show --predicate 'subsystem == "com.apple.TCC"' --info --debug \
  | grep -E 'from Sub:|responsible=|accessing='
# → from Sub:{~/.local/bin/uv}, accessing={...cpython-3.x.../python3.x}
```

- `responsible` = `uv` (the launcher). The dialog *displays* the accessing interpreter's basename
  (`python3.11`), which drifts as uv picks different versions — so authorizing `python3.11` is the
  wrong subject and never sticks.
- A launchd-spawned `uv` is a **root process with no FDA-bearing parent to inherit from**. An
  interactive run does not prompt because the terminal (Ghostty/Terminal) already holds FDA and `uv`
  inherits it as a child.
- `uv` itself has no FDA grant → each run requests `kTCCServiceSystemPolicyAllFiles` → Service
  Policy denies → `promptType=1` → dialog. (`auth_reason = 5`, structural.)

## What does NOT work (all measured, 2026-09-19)

- Authorizing `python3.11` / `python3.12` — the requester is `uv`, not python; and the version drifts.
- `LimitLoadToSessionType = Aqua` in the plist — does not change the requester.
- `launchctl asuser 501` re-launch from inside the job — the detached process still has no FDA parent.
- Pinning `uv run --python 3.12` — still `uv` requesting FDA.

## Repair

Follow [`automated-full-disk-access.md`](automated-full-disk-access.md) first: check the exact
requester and any existing grant, then test the protected read under the real LaunchAgent.
In this observed case, `uv` was the responsible requester. Reusing its existing FDA grant
worked for the Mac WeChat reader; that result does not establish inheritance for every job.

If no usable grant exists, add the **absolute `uv` path from the job's actual
`ProgramArguments`** in System Settings → Privacy & Security → Full Disk Access. The file
picker's Go to Folder action (`Cmd+Shift+G`) can select a binary outside `/Applications`.
Verify the exact client path using the query in [`tcc-mechanics.md`](tcc-mechanics.md), then
restart the job and repeat its protected read. TCC stores the absolute path, not a literal `~`.

## It recurs

The grant is keyed to uv's **absolute path**. If uv is upgraded to a new path, or swapped for a
Homebrew build, the grant is void and the prompt returns — re-add the new path. This is the same
per-path fragility as everything in this skill; there is no identity-stable grant for an unsigned
binary.

## Diagnostic instrument discipline

To confirm *which* binary requests FDA, do not rely on:
- `fs_usage` — can emit 0 bytes on some machines (environment-limited); 0 output ≠ no access.
- log time windows — a short-lived process falls between samples; "caught 0" ≠ not happening.
- `pgrep` — a 50ms-lived process is gone before you poll; "not running" is a false negative.

Reliable: read the TCC `from Sub:` attribution (who), and for *which operation* triggers it, use an
in-process audit hook (`sys.addaudithook` logging `open`) aligned to the tccd timestamp.
