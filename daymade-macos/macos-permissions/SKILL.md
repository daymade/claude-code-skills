---
name: macos-permissions
description: >-
  Diagnoses and repairs macOS TCC dialogs and silent denials: Full Disk Access, Screen Recording,
  Microphone, Camera, Accessibility, Automation. Use for recurring prompts, LaunchAgent/uv jobs
  that fail only in background, broken grants, or automating Full Disk Access (权限弹窗 / 授权了没用 /
  完全磁盘访问). Checks requester and grants first. Not for launchd design
  (macos-watchdog) or app permission UX (developing-ios-apps).
---

# macOS Permissions (TCC)

macOS gates per-app, per-resource access through **TCC** (Transparency, Consent, Control).
TCC records permission decisions in its databases and controls what a process can do.
Several common traps need different fixes:

| Trap | Symptom | Fix lives in |
|---|---|---|
| **Wrong subject granted** | Dialog names `python3.11`/`2.1.232`/`node`; you granted that but it still prompts | [The attribution trap](#the-attribution-trap) below |
| **Grant doesn't survive** | Worked, then a binary/uv/CLI update → prompt returns | `references/uv-fda-trap.md` |
| **Silent denial** | Feature "unavailable", no dialog, grant looks ON | `references/tcc-mechanics.md` § auth_value |
| **Can't read TCC.db** | `Permission denied` reading the DB; need FDA to diagnose FDA | `references/tcc-mechanics.md` § SIP |

## The attribution trap

### Reproduce the reported denial first

The executing agent first inspects the original protected operation through its task-owned handle and any retained result. Reuse current evidence for the same resource, requester and execution context. Keep a still-running request within its existing deadline; do not launch a replacement while its terminal state is unknown. When current evidence is missing or stale, issue one bounded read through the actual failing requester and context before choosing a permission repair. A file listing, another terminal, SSH access or a foreground run cannot substitute for that operation. Record the path/resource, requester, context and result; this is a diagnostic step, not a mechanical permission classifier.

If that read now succeeds, report **currently accessible; earlier cause unknown** and stop permission changes unless a specific required read still fails. Do not call the cause repaired without evidence of the cause and its correction, or add Full Disk Access, change ACLs, reconnect shared mounts or restart a shared host merely to clear a historical error. If it still fails, follow the attribution checks below; `Operation not permitted` alone does not establish TCC as the cause.

**The name in the dialog does not prove who to grant.** macOS attributes a request to the *responsible*
process in the process tree, but displays the name of the *accessing* executable — and for an
unsigned binary with no bundle (uv-managed python, per-version CLI, node helpers) that display
name is just the last path component, which changes with every version. Granting the displayed
name is the mistake that costs the most rounds.

**Before touching System Settings, inspect the request and any readable grant state:**

```bash
# 1. Who is actually requesting — the responsible process in the attribution chain
/usr/bin/log show --last 30m --predicate 'subsystem == "com.apple.TCC"' --info --debug \
  | grep -E 'from Sub:|responsible=|accessing=' | tail -20

# 2. Grant candidates, if this terminal can read the system database
sudo -n sqlite3 '/Library/Application Support/com.apple.TCC/TCC.db' \
  "select service, client, auth_value from access where service='kTCCServiceSystemPolicyAllFiles' and client like '%<name>%';"
```

Use `from Sub:` to identify a candidate requester, then verify its exact path and a real
protected read before choosing what to authorize. An unreadable TCC.db leaves grant state
unknown; its FDA bootstrap is in `references/tcc-mechanics.md`.
When interpreting preflight logs or an allowed grant row, first load
[Correlate preflight and grant evidence](references/tcc-mechanics.md#correlate-preflight-and-grant-evidence)
before choosing a permission repair.

## Decision tree

| The situation is… | Go to |
|---|---|
| User asks to complete Full Disk Access repair automatically, or a background job needs protected files | `references/automated-full-disk-access.md` (reuse a verified existing grant first; otherwise drive System Settings and read back) |
| Dialog reappears after clicking Allow; or a LaunchAgent / `uv run` job prompts every few minutes | `references/uv-fda-trap.md` (identify the requester; follow the automated repair route before adding a grant) |
| Need the full kTCCService catalog, schema, auth_value/auth_reason semantics, `tccutil` | `references/tcc-mechanics.md` |
| Reading TCC.db gives "Permission denied" | `references/tcc-mechanics.md` § SIP and the FDA bootstrap |
| A granted permission silently stopped working after an update | `references/tcc-mechanics.md` § common failure modes (toggle off/on, or `tccutil reset <Service> <bundle-id>`) |
| Grant won't stick for Automation / Apple Events | `references/tcc-mechanics.md` — BOTH controller AND target need the grant |

## Core rules (each from a real incident)

- **Dialog name ≠ responsible process.** `from Sub:` in the TCC log is the requester; the title
  is the accessing binary's basename and it drifts with versions. Grant by the real path.
  (2026-09-19: a `uv` FDA dialog showed `python3.11`; authorizing python, changing session type,
  and pinning the version all failed because the requester was `~/.local/bin/uv`.)
- **Grants are keyed to the exact binary path, not identity.** An unsigned executable (uv-managed
  python, per-version CLI, node helper) is a *new* app to TCC every time its path changes. This is
  why "worked yesterday, prompts today" after any update. Same root cause as Claude Code issues
  #74234 / #84948 / #86706.
- **"0 hits / can't catch it" is an instrument problem, not a conclusion.** `fs_usage` can emit 0
  bytes on some machines; short-lived processes fall between log time windows; an empty grep file
  looks identical to a real zero. To pin *which operation* triggers a prompt, use in-process
  `sys.addaudithook` to log `open` events aligned to the tccd timestamp — not `fs_usage`.
- **SIP protects the system TCC.db read-only.** You cannot `INSERT`/`UPDATE` a grant from the
  command line — authorization must go through the GUI. `auth_value` is readable, writable is not.
- **After granting, verify the request before considering a restart.** Follow
  [the request lifecycle below](#after-a-grant-or-reset); restart requirements depend on
  the permission and application, not on the presence of an Allow click.

## After a grant or reset

The executing agent checks the original request through its task-owned process/tool handle
and repeats the named protected operation in the same requester and execution context.
These are operator checks; this Skill does not automatically manage process lifecycles.

1. If the original request is still running, keep it alive and wait within its existing
   deadline for its actual result. An Automation/AppleEvent request can complete after Allow
   without restarting its requester. A dismissed dialog or an enabled switch is not success.
2. If a wait expires, inspect the original request's terminal result before retrying. A tool
   wait ending does not itself prove the underlying request ended; keep its state unknown
   when no result is available. A late Allow cannot make an expired request succeed. Once
   the original request has ended, issue one new bounded, read-only query when needed to
   verify access; check for any completed side effect before repeating the business action.
3. If access still fails, check the exact requester, permission and application-specific
   relaunch requirement. Restart only when that requirement or the observed failure makes
   it necessary, and only a task-owned process or an explicitly authorized target whose work
   is preserved. Before terminating another session's process or restarting a shared service,
   verify explicit authorization for that exact operation and preservation of its in-flight
   work. Without both, keep that repair pending while continuing independent diagnosis.
4. After any required relaunch, repeat the protected operation in its real context. Stop
   permission changes when it succeeds; a grant record alone does not prove the job works.

## Scope

This skill owns **permission diagnosis and repair**. It does not own: building an app's
permission-onboarding UX (app-development work, out of scope here), launchd job design (`macos-watchdog`),
or disk cleanup (`macos-cleaner`) — those link here when they hit a TCC wall.
