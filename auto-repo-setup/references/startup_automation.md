# Startup automation decision and verification

## Contents

- Choose the mechanism from the outcome
- Default: project instructions
- Safe repository sync contract
- Hook gate
- Claude Code lifecycle details
- Codex lifecycle boundary
- Diagnose repeated output
- Install and verify a Claude startup nudge
- Sources

## Choose the mechanism from the outcome

Use the least stateful mechanism that meets the timing requirement.

| Required outcome | Mechanism | Why |
|---|---|---|
| User wants one action now | Natural-language Agent request | The Agent can inspect context and handle exceptions |
| Every Agent should follow a stable repository rule | AGENTS.md and/or CLAUDE.md | Static context belongs in project instructions |
| User wants an explicit, repeatable maintenance action | A documented command | It runs only when requested and is easy to verify |
| One-time preparation invoked from automation | Claude Code Setup hook | Setup is explicit rather than firing every session |
| Dynamic context or environment must exist before the first prompt | SessionStart | This is the lifecycle boundary hooks are for |
| A dangerous tool action must be blocked | PreToolUse | Enforcement must sit at the action boundary |
| Validation should follow an edit | Project workflow, test command, or scoped post-edit hook | Session start is unrelated to the changed artifact |

Do not choose a hook merely because the desired sentence contains "every time".
First ask whether a project instruction lets the Agent perform the action with
better context.

## Default: project instructions

Use project instructions for stable behavior such as:

- read a project map before work;
- check repository state;
- sync a clean branch;
- run a relevant test after edits;
- follow project-specific safety gates.

Use AGENTS.md for Codex-compatible repository guidance. Use CLAUDE.md when the rule
is Claude Code-specific. If both tools must follow the same rule and the repository
keeps two files, update both or use the repository's established single-source
mechanism.

Do not make the user change how they open the project. A normal opening sentence is
also sufficient when persistence is unnecessary:

> Sync the latest remote version before starting.

## Safe repository sync contract

Put this logic in the Agent instruction, not in a background shell hook:

1. Inspect the current branch, upstream, and working-tree state.
2. If the working tree is clean, run git pull --ff-only.
3. If the working tree has local changes, do not auto-stash or pull; report them.
4. If histories diverged, do not auto-merge, rebase, or force; report the graph.
5. If the network fails, report it and proceed locally only when stale state cannot
   invalidate the task.

git pull --ff-only permits only a fast-forward update and rejects divergent local
history. Automatic stash/pop is a separate stateful operation and can produce
non-trivial conflicts, so never smuggle it into "safe pull".

## Hook gate

Answer every question before installing:

1. What must happen before the first prompt that an Agent instruction cannot do?
2. Is the data dynamic, or is this static prose that belongs in project instructions?
3. Which runtime is targeted: Claude Code, Codex, or both?
4. Which lifecycle source should fire: startup, resume, clear, or compact?
5. Can root and subagent events be distinguished in the installed runtime?
6. What does success output? Checks should be silent on success; context injection
   should emit one concise, intentional message.
7. What failure must block, and what failure may continue?
8. How is the change tested and removed?

If question 1 has no concrete answer, do not install a hook.

## Claude Code lifecycle details

Claude Code SessionStart fires on new and resumed sessions. Its matcher selects:

- startup — a new session;
- resume — --resume, --continue, or /resume;
- clear — /clear;
- compact — automatic or manual compaction.

Always set the narrow matcher. Omitting it runs the group for every SessionStart
source. SessionStart receives JSON on stdin and adds plain stdout to Claude's
context. Keep it fast. For static context, Anthropic explicitly recommends
CLAUDE.md instead.

Claude Code hook input can include agent_type for subagents or named agents. When
root-only behavior matters, inspect the real input and filter deliberately rather
than inferring from process names.

Project hooks live in .claude/settings.json and can be committed. Merge into the
existing JSON; never replace unrelated settings.

## Codex lifecycle boundary

Codex loads repository instructions from AGENTS.md, so prefer that for stable
startup behavior.

Do not mirror a Claude hook into .codex/hooks.json without testing the installed
Codex version. Hook cadence and payload are runtime contracts, not portable config
syntax. In versions where root and subagent SessionStart events are identical and
the payload has no parent/root indicator, root-only side effects cannot be made
reliable. In that case, do not install the hook; use AGENTS.md or an explicit
command.

## Diagnose repeated output

Repeated text does not prove duplicate registration.

Collect:

1. every matching entry in project, local, user, managed, and plugin settings;
2. event and matcher for each entry;
3. timestamps and session/thread IDs for each firing;
4. root, resumed, compacted, and subagent processes active at those timestamps;
5. exact stdout and exit status.

Classify the cause:

- duplicate config entries;
- one entry firing for multiple lifecycle sources;
- one entry firing independently in several agents;
- an imported/mirrored configuration;
- two different hooks printing the same text.

Only then edit configuration.

## Install and verify a Claude startup nudge

The bundled initializer is intentionally narrow: it adds one Claude Code
SessionStart entry with matcher startup and an inline context nudge. It does not
run dependency checks, mutate Git, or install a Codex hook.

Preview:

~~~bash
uv run python scripts/init_session_start_hook.py \
  --repo <repo-root> \
  --guide ONBOARDING.md \
  --dry-run
~~~

Apply only after approval by removing --dry-run. The command preserves unrelated
settings and is idempotent.

Verify:

1. Parse .claude/settings.json with a strict JSON parser.
2. Confirm exactly one managed entry and matcher startup.
3. Run claude --init-only from the repository and inspect the output once.
4. Start a normal root session.
5. Spawn a subagent only if root/subagent behavior is in scope.
6. Confirm resume and compact do not emit the startup-only nudge.

Remove only the managed entry:

~~~bash
uv run python scripts/init_session_start_hook.py \
  --repo <repo-root> \
  --remove
~~~

## Sources

- Anthropic, Skill authoring best practices:
  https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Anthropic, Claude Code hooks reference:
  https://code.claude.com/docs/en/hooks
- OpenAI, Unrolling the Codex agent loop (AGENTS.md loading):
  https://openai.com/index/unrolling-the-codex-agent-loop/
- OpenAI Codex issue tracking root/subagent hook metadata:
  https://github.com/openai/codex/issues/16226
- Git, git-pull documentation:
  https://git-scm.com/docs/git-pull
