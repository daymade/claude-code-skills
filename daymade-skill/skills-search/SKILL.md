---
name: skills-search
description: >-
  Finds Skills in configured local repositories before searching CCPM. Use when
  discovering or reusing a Skill, finding PDF/code-review tools, inspecting a Skill,
  listing installed/popular/recent Skills, or installing/updating/removing Claude Code Skills/plugins.
allowed-tools: Bash, Read
---

# Skills Search — Agent Behavioral Directives

## Local repositories first

For capability discovery or experience reuse, read
[local repository search](references/local-repository-search.md) and execute its
helper. Resolve the Skill directory from this loaded bundle, not an installed
path guessed from memory.

```bash
uv run --script <skill-dir>/scripts/local_sources.py list
uv run --script <skill-dir>/scripts/local_sources.py search '<capability>' --tier owned
```

Search **every enabled repository in the owned tier** before choosing a candidate.
Read the returned `coverage`, examined counts and exact commit. A missing source,
bad configuration or interrupted scan is incomplete coverage, not "no Skill".
The default installation directory is an inventory, not the user's complete
source catalog. Configure all repositories the user named; do not stop after a
hit in the first one or silently infer paths for another machine.

Use progressive disclosure: catalog name/description → selected `SKILL.md` at
its returned commit → only the relevant linked reference/script. Metadata scores
rank candidates; read the capability, inputs, ownership and verification before
deciding it fits. Update a suitable existing Skill; create a new Skill when none
fits, rather than stuffing the workflow into an unrelated owner.

If this layer cannot resolve the remaining task, search configured `trusted`
repositories, then use the existing CCPM search below. Record why expansion was
needed; do not send private paths, repository names or contents to the registry.
Do not use an external hit to hide a failed local scan.

## CCPM preparation (only when needed)

For external registry discovery or an explicitly requested install/update/manage
operation, check `command -v ccpm`. If unavailable, `npx @daymade/ccpm` is the
existing CLI fallback. Local lookup needs neither CCPM nor registry credentials.
Use `npx @daymade/ccpm setup` only when the user requests ecosystem setup: it
also configures integrations and is not a prerequisite for an offline search.

## Core Behavior

Execute the selected local helper or `ccpm` command yourself through the shell.
Do not ask the user to copy-paste a command you can run within the task's authorization.

If `ccpm` is not globally installed, use `npx @daymade/ccpm` as a drop-in replacement for all commands below.

## Intent Mapping

Match the user's intent to the correct action:

| User Intent | Action |
|-------------|--------|
| "find skills for X" / "search X skills" / reuse before writing a Skill | Owned repositories → configured trusted repositories → `ccpm search <query>` if still needed |
| "what skills are popular" / "top skills" | `ccpm popular` |
| "what's new" / "latest skills" | `ccpm recent` |
| "install X" / "add X skill" | `ccpm install <skill-name>` |
| "what does X do" / "tell me about X" | Read the local candidate first; `ccpm info <skill-name>` for registry candidates |
| "what skills do I have" / "list skills" | `ccpm list` |
| "remove X" / "uninstall X" | `ccpm uninstall <skill-name>` |
| "update X" / "update all skills" | `ccpm update [name] [--all]` |
| "I need help with PDF/Excel/..." | Local discovery first; expand to `ccpm search <topic>` if needed, then inspect fit before suggesting installation |

## Execution Rules

1. **Always execute directly** — run the selected local helper or `ccpm` command, never ask the user to run it manually.
2. **Summarize results** — after executing, present the output in a clear, readable format.
3. **Choose from the result** — a local Skill may already be installed. Verify that separately; do not reinstall merely because it was found. If installation is needed, retain the existing opt-in installation flow. After install, remind the user to restart Claude Code.
4. **Handle errors gracefully** — if `ccpm` is not found, fall back to `npx @daymade/ccpm`. If the registry is unreachable, say so clearly.
5. **Namespaced skills** — support `@org/skill-name` format (e.g., `ccpm install @daymade/skill-creator`).

## Command Reference

### Search
```bash
ccpm search <query> [--limit <n>] [--tags <t1,t2>] [--author <name>] [--smart]
```

### Discovery
```bash
ccpm popular [--limit <n>]       # Most downloaded
ccpm recent [--limit <n>]        # Recently published/updated
```

### Install & Manage
```bash
ccpm install <skill-name>        # Install (user-level, default)
ccpm install <name> --project    # Install to current project only
ccpm install <name> --force      # Force reinstall
ccpm list                        # List installed skills
ccpm info <skill-name>           # Detailed skill information
ccpm update [name]               # Update a skill
ccpm update --all                # Update all skills
ccpm uninstall <skill-name>      # Remove a skill
```

## Post-Install Reminder

After any successful install, always tell the user:

> Skill installed successfully. Please restart Claude Code (or start a new conversation) for the skill to become available.

## MCP Server Alternative

For Claude Desktop users who want native tool integration (no Bash needed), the same functionality is available as an MCP server:

```json
{
  "mcpServers": {
    "skill-search": {
      "command": "npx",
      "args": ["-y", "skills-search-mcp"]
    }
  }
}
```

The MCP server wraps the external `ccpm` CLI. It does not search this Skill's
configured local repositories; local discovery remains with the bundled helper.

## Troubleshooting

### "ccpm: command not found"
Use `npx @daymade/ccpm` instead, or install globally: `npm install -g @daymade/ccpm`.

### Skill not available after install
Restart Claude Code — skills are loaded at startup.

### Permission errors
Check write permissions to `~/.claude/skills/`. Try installing with `--project` for project-level scope.
