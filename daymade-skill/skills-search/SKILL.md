---
name: skills-search
description: This skill should be used when users want to search, discover, install, or manage Claude Code skills from the CCPM registry. Triggers include requests like "find skills for PDF", "search for code review skills", "install cloudflare-troubleshooting", "list my installed skills", "what does skill-creator do", or any mention of finding/installing/managing Claude Code skills or plugins.
allowed-tools: Bash, Read
---

# Skills Search — Agent Behavioral Directives

## Auto-Bootstrap (Run First)

Before doing anything else, check if ccpm is available. If not, bootstrap the entire ecosystem with one command:

```bash
# Check availability
which ccpm || npx @daymade/ccpm setup
```

`ccpm setup` installs this skill + configures Claude Desktop MCP server (if installed). After bootstrap, all commands below work directly.

## Core Behavior

When this skill is activated, you MUST directly execute the appropriate `ccpm` command using the Bash tool. Do NOT show the user a command and ask them to copy-paste it — execute it yourself.

If `ccpm` is not globally installed, use `npx @daymade/ccpm` as a drop-in replacement for all commands below.

## Intent Mapping

Match the user's intent to the correct action:

| User Intent | Action |
|-------------|--------|
| "find skills for X" / "search X skills" | `ccpm search <query>` |
| "what skills are popular" / "top skills" | `ccpm popular` |
| "what's new" / "latest skills" | `ccpm recent` |
| "install X" / "add X skill" | `ccpm install <skill-name>` |
| "what does X do" / "tell me about X" | `ccpm info <skill-name>` |
| "what skills do I have" / "list skills" | `ccpm list` |
| "remove X" / "uninstall X" | `ccpm uninstall <skill-name>` |
| "update X" / "update all skills" | `ccpm update [name] [--all]` |
| "I need help with PDF/Excel/..." | `ccpm search <topic>`, then offer to install the best match |

## Execution Rules

1. **Always execute directly** — run `ccpm` commands via the Bash tool, never ask the user to run them manually.
2. **Summarize results** — after executing, present the output in a clear, readable format.
3. **Suggest next steps** — after search results, offer to install. After install, remind the user to restart Claude Code.
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

Both this skill and the MCP server wrap the same `ccpm` CLI — they are complementary, not conflicting.

## Troubleshooting

### "ccpm: command not found"
Use `npx @daymade/ccpm` instead, or install globally: `npm install -g @daymade/ccpm`.

### Skill not available after install
Restart Claude Code — skills are loaded at startup.

### Permission errors
Check write permissions to `~/.claude/skills/`. Try installing with `--project` for project-level scope.
