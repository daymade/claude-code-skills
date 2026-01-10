# MCP Skills Plugin

Convert MCP servers to Claude Skills with progressive disclosure, reducing context usage by 90%+.

## Features

- **MCP to Skill Converter**: Transform any MCP server into a context-efficient Claude Skill
- **Session Start Hook**: Automatically loads the MCP skills registry on session start
- **Progressive Disclosure**: Only load tool definitions when actually needed
- **Multi-Transport Support**: Compatible with `stdio`, `http`, and `sse` MCP server types
- **Automatic Registry Management**: Maintains an index of all converted skills

## Installation

Install the plugin using Claude Code's `--plugin-dir` option:

```bash
# Clone or download the plugin
git clone https://github.com/your-org/mcp-skills-plugin.git

# Run Claude Code with the plugin
claude --plugin-dir /path/to/mcp-skills-plugin
```

Or add to your Claude Code configuration for persistent use.

## Requirements

- **Python 3.8+**
- **mcp package**: `pip install mcp`

## Usage

### Converting MCP Servers to Skills

Once the plugin is installed, Claude can use the `mcp-to-skill-converter` skill.

#### List Available Servers

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
brave-search              stdio      ✅ Yes        npx

📊 Total: 10 servers, 8 compatible
```

#### Convert a Single Server

```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --name github
```

This will:
1. Create a skill in `.claude/skills/mcp-skills/github/`
2. Update the MCP skills registry
3. Remove the server from `.mcp.json` to prevent duplicate loading

#### Convert All Compatible Servers

```bash
python ${PLUGIN_DIR}/skills/mcp-to-skill-converter/mcp_to_skill.py --all
```

### Using Converted Skills

After conversion, Claude can invoke the MCP tools through the generated skill:

```bash
# List tools in a skill
python .claude/skills/mcp-skills/executor.py --skill github --list

# Get tool schema
python .claude/skills/mcp-skills/executor.py --skill github --describe create_issue

# Call a tool
python .claude/skills/mcp-skills/executor.py --skill github --call '{"tool": "create_issue", "arguments": {"title": "Bug fix", "body": "Details..."}}'
```

### Session Start Hook

The plugin automatically loads the MCP skills registry at the start of each Claude Code session. This provides:

- **Context efficiency**: Only ~150 tokens for the registry vs 30-50k tokens for native MCP loading
- **Discovery**: Claude knows which skills are available without loading all tool definitions
- **On-demand loading**: Full tool details are only loaded when needed

## Context Savings

| Scenario | Native MCP | Skills Plugin | Savings |
|----------|------------|---------------|---------|
| Idle (no tools used) | 30-100k tokens | ~150 tokens | 99%+ |
| Using 1 skill | 30-100k tokens | ~5k tokens | 90%+ |
| Tool execution | 30-100k tokens | 0 tokens | 100% |

## Plugin Structure

```
mcp-skills-plugin/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── skills/
│   └── mcp-to-skill-converter/
│       ├── SKILL.md          # Skill documentation
│       ├── mcp_to_skill.py   # Converter script
│       └── templates/
│           ├── index.json
│           └── registry-SKILL.md
├── hooks/
│   ├── hooks.json            # Hook configuration
│   └── load-mcp-skills.sh    # Session start hook
├── README.md
└── LICENSE
```

## Server Compatibility

| Type | Compatible | Notes |
|------|------------|-------|
| `stdio` | ✅ Yes | Standard input/output protocol |
| `http` | ✅ Yes | Streamable HTTP protocol |
| `sse` | ✅ Yes | Server-Sent Events protocol |

## Security Notes

⚠️ **Important Security Considerations**:

1. **Command Execution**: The converter and executor scripts run MCP servers as subprocesses. Only convert and use MCP servers from trusted sources.

2. **Environment Variables**: MCP server configurations may include environment variables (API keys, tokens). These are stored in the generated `mcp-config.json` files.

3. **Code Execution**: Generated skills can execute arbitrary code through MCP tool calls. Review the tools available in each converted skill before use.

4. **File System Access**: The converter reads from `.mcp.json` and writes to the skills directory. Ensure appropriate file permissions.

## Troubleshooting

### "mcp package not found"
```bash
pip install mcp
```

### "Could not find .mcp.json"
Specify the path explicitly:
```bash
python mcp_to_skill.py --mcp-json /path/to/.mcp.json --name github
```

### "Server not found"
Run `--list` to see available servers in your `.mcp.json`.

### Hook not loading
Ensure the hook script is executable:
```bash
chmod +x hooks/load-mcp-skills.sh
```

## Contributing

Contributions are welcome! Please read the contributing guidelines before submitting PRs.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

*Reduce your Claude Code context usage by 90%+ with MCP Skills.*
