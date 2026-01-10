---
name: mcp-skills
description: Registry of MCP-derived skills with progressive disclosure. Use when asked about "github", "assistant-ui", "MCP tools", or any converted MCP server. Provides 90%+ context savings compared to native MCP loading.
version: 1.0.0
---

# MCP Skills Registry

Central directory for all MCP-derived skills. Each sub-skill wraps an MCP server with progressive disclosure.

## Available Skills

| Skill | Tools | Trigger Keywords |
|-------|-------|------------------|
<!-- Add skills here after conversion. See mcp-to-skill-converter workflow Step 3. -->

See `index.json` for the machine-readable list.

## ⚠️ These Are Skill Wrappers, NOT Native MCP Tools

You CANNOT call `mcp__shadcn__*`, `mcp__github__*`, etc. directly - those don't exist.
These skills wrap MCP servers via a central executor.py.

## Usage

**Step 1: Read the skill's SKILL.md** (from project root):

```bash
cat .claude/skills/mcp-skills/<skill-name>/SKILL.md

# Example: shadcn skill
cat .claude/skills/mcp-skills/shadcn/SKILL.md
```

**Step 2: Use the central executor.py** (from project root):

```bash
# List available skills
python .claude/skills/mcp-skills/executor.py --skills

# List tools in a skill
python .claude/skills/mcp-skills/executor.py --skill github --list

# Get tool schema
python .claude/skills/mcp-skills/executor.py --skill github --describe create_issue

# Call a tool
python .claude/skills/mcp-skills/executor.py --skill github --call '{"tool": "create_issue", "arguments": {...}}'
```

## Context Efficiency

| Scenario | Native MCP (all servers) | This Registry | Savings |
|----------|--------------------------|---------------|---------|
| Idle | 40-100k tokens | ~150 tokens | 99%+ |
| Using 1 skill | 40-100k tokens | ~5k tokens | 90%+ |
| After execution | 40-100k tokens | ~150 tokens | 99%+ |

## How It Works

1. **Registry loads first** - This file (~150 tokens)
2. **User requests a tool** - e.g., "create a GitHub PR"
3. **Sub-skill loads** - Only the relevant skill's SKILL.md (~4k tokens)
4. **Executor runs** - External process, 0 context tokens
5. **Result returned** - Context drops back to registry only

## Adding New Skills

Use the `mcp-to-skill-converter` skill:

```bash
cd .claude/skills/mcp-to-skill-converter
python mcp_to_skill.py --name <server-name>
# Outputs to .claude/skills/mcp-skills/<server-name>/
```

## Skill Structure

Each sub-skill contains:

```
.claude/skills/mcp-skills/<skill-name>/
├── SKILL.md           # Tool documentation
├── executor.py        # Async MCP client (legacy, use central executor)
├── mcp-config.json    # Server config
└── package.json       # Dependencies
```

---

*This registry enables progressive disclosure of MCP servers as Claude Skills.*
