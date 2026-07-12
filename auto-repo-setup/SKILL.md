---
name: auto-repo-setup
description: >-
  Diagnose, repair, and standardize repository setup and safe Git workflows for
  Claude Code or Codex. Use when a repository will not run, a collaborator is
  onboarding, dependencies or credentials are missing, the user wants startup
  sync, SessionStart output is duplicated, project instructions or hooks need
  auditing, or commit/push/conflict/history-cleanup needs a guarded workflow.
  Route ordinary startup behavior through project instructions or a natural
  language request; use lifecycle hooks only when behavior must occur before the
  first prompt and the target runtime has been verified.
argument-hint: "[repository path]"
---

# Auto Repo Setup

Make the repository usable without changing the user's normal way of working.
Treat setup as an evidence-driven repository task, not as a special interface for
people with a particular job title.

## Entry router

Classify the request before changing anything. Do not combine modes merely because
they all contain the word "setup".

| User outcome | Mode | First action |
|---|---|---|
| "It won't run", missing dependency, new machine | Environment repair | Read project instructions and detect the actual stack |
| "Sync before we work", "pull the latest" | Session routine | Use project instructions or execute the user's natural-language request |
| Repeated or unexpected hook output | Hook diagnosis | Count registrations and firing sessions before editing configuration |
| A teammate needs a repeatable handoff | Repository handoff | Audit existing onboarding and fill only the missing operational contract |
| Commit, push, conflict, leaked secret/history | Git safety | Read [references/git_safety.md](references/git_safety.md) before mutation |
| Behavior must happen before the first prompt | Startup automation | Read [references/startup_automation.md](references/startup_automation.md) and pass its hook gate |

## Operating principles

1. **Do not infer competence from role.** Match the user's demonstrated altitude.
   A collaborator can tell an agent "sync the remote first"; do not invent a
   launcher, shortcut, or wizard unless the user asked for one.
2. **Use the least mechanism that satisfies the outcome.** Prefer, in order:
   direct Agent instruction → project instruction → explicit command → lifecycle
   hook. A hook is not a more professional version of a sentence.
3. **Inspect authority before producing.** Read the current user request, then
   project instructions, onboarding/runbooks, manifests, lockfiles, and actual
   command output. Do not make ONBOARDING.md, Python, uv, ffmpeg, or .env mandatory
   for repositories that do not declare them.
4. **Preserve user work.** Never auto-stash, merge, rebase, force, discard, or
   overwrite local changes to make setup look successful.
5. **Define a falsifiable success state.** "Dependencies installed" is not enough;
   run the project's real smoke test or startup command and verify the observable
   result.
6. **Keep diagnosis read-only until the cause is known.** Installation, config
   edits, hook registration, commits, and external writes require the authority
   implied by the user's request; destructive or public actions require explicit
   approval.

## Workflow A — Environment repair

### A1. Read the project map

Read only files that exist, in this order:

1. AGENTS.md and AGENTS.override.md
2. CLAUDE.md and scoped project rules
3. ONBOARDING.md or the repository's named setup/runbook
4. README.md
5. Manifests, lockfiles, task runners, CI, and container configuration
6. Existing Claude/Codex settings only when the request concerns agent behavior

If no onboarding guide exists, infer the setup path from authoritative manifests
and exercised commands. Do not stop to ask whether to create documentation unless
a durable handoff is part of the request.

### A2. Run a read-only capability inventory

Use the bundled scripts/check_env.py against the repository root when a Python
3.10+ runner is already available. It detects the declared ecosystem and checks
only the relevant toolchain; it does not install dependencies or read secret
values. If Python is itself the missing prerequisite, perform the same read-only
manifest inventory directly instead of installing Python merely to run the audit.

~~~bash
uv run python scripts/check_env.py --repo <repo-root>
uv run python scripts/check_env.py --repo <repo-root> --json
~~~

Treat the inventory as evidence, not as the project setup specification. A custom
runbook or CI workflow can require tools the generic inventory cannot infer.

Expected result:

- exit 0: all toolchains inferred from manifests are available;
- exit 1: one or more inferred prerequisites are missing;
- exit 2: the repository or its metadata could not be inspected safely.

### A3. Repair the root cause

For each failed requirement:

1. Capture the exact command, exit code, stdout, and stderr.
2. Trace the failure to the declaring source: project guide, manifest, lockfile,
   configuration, or runtime log.
3. Apply the smallest project-consistent repair.
4. Re-run the failed check before moving on.

Do not restart, reinstall everything, or switch package managers as a first move.
Do not print .env or credential contents; verify presence and behavior without
echoing values.

### A4. Verify the product path

Run the project's documented smoke test, build, or start command. If none exists,
derive one from CI/task-runner configuration and label the derivation. Verify the
observable result, not merely a zero exit code.

Report:

- what was broken and the evidence;
- what changed;
- the exact verification and result;
- any remaining user action or blocked authority.

## Workflow B — Routine Git sync

For "sync before work", prefer a short project instruction shared by the agents
that use the repository. The routine is:

1. Inspect branch, upstream, and working-tree state.
2. If the working tree is clean, run git pull --ff-only.
3. If there are local changes, do not auto-stash or pull; explain the state.
4. If local and remote histories diverged, do not auto-merge, rebase, or force;
   explain the state.
5. If the network fails, say so and continue locally only when the user's task can
   safely proceed on the local version.

A collaborator may also simply say:

> Sync the latest remote version before starting.

That is a normal Agent instruction, not a degraded fallback.

Do not register SessionStart merely to automate this routine. Static behavior
belongs in AGENTS.md/CLAUDE.md; the Agent can inspect context and handle exceptional
Git states instead of hiding them in a shell process.

## Workflow C — Repository handoff

Create or revise onboarding only when the user wants a durable handoff and the
existing project map does not already provide one.

Use [references/onboarding_template.md](references/onboarding_template.md) as a
checklist, not as a literal Python/video template:

- derive prerequisites from manifests and actual project commands;
- include expected output after each command;
- separate one-time setup from daily use;
- include recovery for real observed failures;
- keep project instructions as the operational SSOT and avoid duplicating values.

Validate every command on the target operating systems that matter to the user.

## Workflow D — Startup automation and hook diagnosis

Read [references/startup_automation.md](references/startup_automation.md) before
adding or changing any hook.

### Diagnose repeated output first

1. Enumerate project, local, user, managed, and plugin hook registrations.
2. Count matching entries; do not infer "three registrations" from three outputs.
3. Identify which root sessions, resumes, compactions, or subagents fired them.
4. Verify the event matcher and current runtime payload.
5. State the root cause before proposing a change.

### Install only after the hook gate passes

The bundled initializer is Claude Code-specific and installs only a lightweight
startup context nudge. It preserves unrelated settings, adds matcher startup,
validates the guide path, writes atomically, and is idempotent.

Preview first:

~~~bash
uv run python scripts/init_session_start_hook.py \
  --repo <repo-root> \
  --guide ONBOARDING.md \
  --dry-run
~~~

After the user confirms that pre-prompt injection is genuinely required, run the
same command without --dry-run. Remove only the managed entry with --remove.

Never copy this configuration into Codex by analogy. Codex project behavior should
normally live in AGENTS.md; if a Codex hook is truly required, verify the installed
version's root/subagent behavior and payload first.

## Git safety

Read [references/git_safety.md](references/git_safety.md) before commit, push,
conflict resolution, or history rewrite. The load-bearing rules are:

- stage only intended paths;
- never bypass hooks unless the user explicitly typed the bypass in this session;
- verify repository visibility from the hosting service before push;
- get explicit approval before public push, force push, or history rewrite;
- resolve conflicts from project semantics, never by blindly choosing "ours" or
  "theirs";
- revoke leaked credentials before treating history cleanup as complete.

Use [references/pii_guard.md](references/pii_guard.md) for public-distribution
content review. A green scanner does not replace semantic review.

For a read-only history scan, the existing scripts/sanitize_history.sh remains
available. It never rewrites history; treat its findings as candidates and do not
execute rewrite commands without explicit approval.

## Counter-review boundary

Use counter-review when the approved work materially changes security policy,
shared lifecycle hooks, CI/CD, dependencies, or destructive Git behavior. Do not
spawn a review team for an ordinary setup check or a one-line project instruction.
Filter every finding by probability, cost, real usage, and direct verification.

## Resources

- scripts/check_env.py — stack-aware, read-only repository inventory
- scripts/init_session_start_hook.py — guarded Claude Code startup-nudge manager
- scripts/sanitize_history.sh — read-only history candidate scan
- [references/startup_automation.md](references/startup_automation.md) — project
  instruction vs command vs hook decision and verification
- [references/git_safety.md](references/git_safety.md) — sync, commit, push,
  conflict, and history rewrite gates
- [references/onboarding_template.md](references/onboarding_template.md) — durable
  handoff checklist
- [references/pii_guard.md](references/pii_guard.md) — public-content scan layers
