---
name: agent-skill-groups
description: Manage large Claude Code, Codex, OpenCode, or generic Agent Skills inventories with scenario-based skill profiles using the agent-skill-groups CLI. Use when skills are too noisy, startup context is bloated, the user wants to enable or disable skill groups on demand, or a team needs a repeatable groups.json plus CLAUDE.md/AGENTS.md memory block instead of manually moving SKILL.md folders.
---

# Agent Skill Groups

## Overview

Use the `agent-skill-groups` CLI to turn a large local Agent Skills directory into runtime-aware profiles. Keep a small always-on core profile, park specialized skills in a managed disabled pool, and load only the scenario group needed for the current task.

The CLI supports Claude Code, OpenAI Codex, OpenCode, and generic `SKILL.md` layouts. It does not edit skill contents; it moves skill directories between active roots and a managed disabled root, with backups and dry-run plans before profile changes.

## When to Use This Skill

- Manage a large Claude Code skills library that has become noisy or slow to reason about.
- Split local skills into scenarios such as `core`, `research`, `frontend`, `ctf`, `security`, `docs`, or team-specific groups.
- Generate or maintain a `groups.json` profile table for `~/.claude/skills`, `~/.codex/skills`, `~/.config/opencode/skills`, or `.agents/skills`.
- Switch a task session to one group and disable unrelated managed skills.
- Write a persistent `CLAUDE.md` or `AGENTS.md` memory block that tells the agent which groups exist and how to load them.
- Diagnose missing, duplicate, ungrouped, or malformed `SKILL.md` directories.

## Core Workflow

1. Identify the runtime first:

   ```bash
   agent-skill-groups runtimes
   ```

   Use `claude-code` for Claude Code, `codex` for OpenAI Codex, `opencode` for OpenCode, and `generic` for portable Agent Skills roots.

2. If the CLI is missing, install it from the canonical repository:

   ```bash
   pipx install git+https://github.com/go165/agent-skill-groups.git
   # or
   python -m pip install git+https://github.com/go165/agent-skill-groups.git
   ```

3. Run the bundled read-only check from this skill before changing profile state:

   ```bash
   python scripts/check_agent_skill_groups.py --runtime claude-code
   ```

4. Analyze the current skill inventory:

   ```bash
   agent-skill-groups analyze --runtime claude-code --json
   agent-skill-groups suggest --runtime claude-code
   ```

5. Generate a starting group table:

   ```bash
   agent-skill-groups init --runtime claude-code --output groups.json
   ```

6. Edit `groups.json` deliberately. Keep a small `core` group and put optional or scenario-specific skills into named groups.

7. Validate before moving anything:

   ```bash
   agent-skill-groups validate --config groups.json --runtime claude-code
   agent-skill-groups doctor --config groups.json --runtime claude-code
   agent-skill-groups plan --config groups.json --runtime claude-code research
   ```

8. Back up state, then switch profile:

   ```bash
   agent-skill-groups backup --config groups.json --runtime claude-code
   agent-skill-groups profile --config groups.json --runtime claude-code research
   ```

9. Write persistent agent memory only after the group table is stable:

   ```bash
   agent-skill-groups memory --config groups.json --runtime claude-code --write CLAUDE.md
   ```

## Safety Rules

- Run `plan` and `backup` before `profile`.
- Do not hand-move managed skill directories while a profile switch is in progress.
- Keep `.system`, troubleshooting, and marketplace-recovery skills in `core` unless there is a strong reason to disable them.
- Treat `groups.json` as the source of truth. Update it when adding or removing skills.
- If profile state looks wrong, run `status --details` and restore from the latest backup before making more moves.

## Resources

- `references/cli_workflow.md` - detailed runtime commands, config layout, and recovery notes.
- `scripts/check_agent_skill_groups.py` - read-only local checker for CLI availability and optional config validation.
- Canonical project: <https://github.com/go165/agent-skill-groups>
