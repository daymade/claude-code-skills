---
name: mcp-to-skill-converter
description: This skill should be used when the user asks to "convert MCP to skill", "create skill from MCP", "list MCP servers", "batch convert MCP", "generate skills from .mcp.json", or when working with MCP server configurations. Reduces context usage by 90%+ compared to native MCP loading.
version: 1.0.0
---

# MCP to Skill Converter

Convert any MCP server into a Claude Skill with progressive disclosure pattern, reducing context usage by 90%+.

## When to Use This Skill

- Converting MCP servers to skills for context efficiency
- Listing available MCP servers in a project
- Batch converting multiple MCP servers
- Creating skills from `.mcp.json` configuration

## Quick Commands

All commands run from project root where the plugin is installed.

### List Available Servers

```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --list
```

Shows all MCP servers with compatibility status (`stdio`, `http`, and `sse` types are compatible).

### Convert Single Server (auto-outputs to mcp-skills/)

```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --name <server-name>
```

**Example:**
```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --name github
# Outputs to: .claude/skills/mcp-skills/github/
# Automatically removes github from .mcp.json
# Updates mcp-skills/index.json
```

### Convert All Compatible Servers

```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --all
# Converts all compatible servers (stdio, http, sse) to mcp-skills/
```

### Custom Output Directory

```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --name github --output-dir /custom/path
```

### Specify Custom .mcp.json

```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --mcp-json /path/to/.mcp.json --name github --output-dir ./skills
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--list` | List all servers with compatibility info |
| `--name NAME` | Convert specific server by name |
| `--all` | Convert all compatible servers |
| `--output-dir PATH` | Output directory for generated skill(s) |
| `--mcp-json PATH` | Path to .mcp.json (auto-discovers if not specified) |
| `--mcp-config PATH` | [Legacy] Direct MCP config JSON file |

## Server Compatibility

| Type | Compatible | Notes |
|------|------------|-------|
| `stdio` | ✅ Yes | Standard input/output protocol |
| `http` | ✅ Yes | Streamable HTTP protocol |
| `sse` | ✅ Yes | Server-Sent Events protocol |

## Context Savings

| Scenario | Native MCP | As Skill | Savings |
|----------|------------|----------|---------|
| Idle | 30-50k tokens | ~100 tokens | 99%+ |
| Active | 30-50k tokens | ~5k tokens | 85%+ |
| Executing | 30-50k tokens | 0 tokens | 100% |

## Workflow Example

**Step 1: List available servers**
```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --list
```

Output:
```
📄 Servers in: /path/to/.mcp.json

Name                      Type       Compatible   Command
--------------------------------------------------------------------------------
github                    stdio      ✅ Yes        npx
context7                  stdio      ✅ Yes        npx
livekit-docs              http       ❌ No         https://...

📊 Total: 16 servers, 14 compatible
```

**Step 2: Convert desired server**
```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --name github
```

The converter automatically:
- Creates the skill in `.claude/skills/mcp-skills/github/`
- Initializes the mcp-skills registry (SKILL.md + index.json) if needed
- Updates `index.json` with the new skill
- Removes the server from `.mcp.json` to avoid duplicate loading

**Step 3: Add semantic trigger keywords (MANDATORY)**

The converter generates a placeholder description. You MUST update it with meaningful trigger keywords based on what the MCP server actually does.

1. **Read the generated SKILL.md** to understand what tools are available
2. **Identify semantic keywords** - What would users naturally ask for?
   - Think about user intent, not tool names
   - "ToolUI", "chat components" NOT "assistantUIDocs"
   - "create PR", "issues", "repository" NOT "create_pull_request"
3. **Update the SKILL.md description** with trigger keywords:

```yaml
# Before (auto-generated):
description: Dynamic access to assistant-ui MCP server (2 tools)

# After (agent-enhanced):
description: Use for assistant-ui documentation, ToolUI, generative UI, chat components, Thread, Composer, Message primitives, runtime integrations. Get docs and code examples for building AI chat interfaces.
```

4. **Update the registry SKILL.md** (`mcp-skills/SKILL.md`):
   - Add the skill to the "Available Skills" table
   - Include the trigger keywords column

Example registry entry:
```markdown
| Skill | Tools | Trigger Keywords |
|-------|-------|------------------|
| assistant-ui | 2 | ToolUI, generative UI, chat components, assistant-ui docs |
| github | 26 | PR, issues, repository, commits, code search |
```

**Step 4: Use the generated skill**
Claude will auto-discover the new skill in the mcp-skills registry and can invoke MCP tools with minimal context overhead.

## Generated Skill Structure

```
output-dir/server-name/
├── SKILL.md           # Instructions and tool documentation
├── executor.py        # Async MCP client wrapper
├── mcp-config.json    # Server configuration
└── package.json       # Dependency info
```

## Using Generated Skills

Use the central executor from project root:

```bash
# List tools in a skill
python .claude/skills/mcp-skills/executor.py --skill <skill-name> --list

# Describe specific tool
python .claude/skills/mcp-skills/executor.py --skill <skill-name> --describe tool_name

# Call a tool
python .claude/skills/mcp-skills/executor.py --skill <skill-name> --call '{"tool": "tool_name", "arguments": {...}}'
```

## Requirements

```bash
pip install mcp
```

Python 3.8+ required.

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| "Server not found" | Name doesn't exist | Run `--list` to see available servers |
| "Type not supported" | Server is HTTP/SSE | Only stdio servers can be converted |
| "Could not find .mcp.json" | No config found | Use `--mcp-json` to specify path |
| "mcp package not found" | Missing dependency | Run `pip install mcp` |

## Files in This Skill

- `SKILL.md` - This documentation
- `mcp_to_skill.py` - The converter script
- `templates/` - Template files for generated skills

---

*This skill enables converting MCP servers to Claude Skills for 90%+ context savings.*
