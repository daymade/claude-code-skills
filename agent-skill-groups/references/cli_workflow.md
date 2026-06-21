# agent-skill-groups CLI workflow

## Runtime presets

Use the runtime that matches the active agent environment:

| Runtime | Typical active skill root | Managed disabled root |
|---|---|---|
| `claude-code` | `$HOME/.claude/skills` | `$HOME/.claude/skills.disabled/managed` |
| `codex` | `$HOME/.codex/skills`, `$HOME/.agents/skills` | `$HOME/.codex/skills.disabled/managed` |
| `opencode` | `$HOME/.config/opencode/skills`, `$HOME/.claude/skills` | `$HOME/.config/opencode/skills.disabled/managed` |
| `generic` | `$HOME/.agents/skills`, `.agents/skills` | `$HOME/.agents/skills.disabled/managed` |

Check the current presets:

```bash
agent-skill-groups runtimes
```

## First-time setup

Start with read-only inspection:

```bash
agent-skill-groups analyze --runtime claude-code --json
agent-skill-groups suggest --runtime claude-code
```

Generate a starting table:

```bash
agent-skill-groups init --runtime claude-code --output groups.json
```

Recommended grouping pattern:

- `core`: essential always-on skills only.
- `research`: search, PDF, notebook, citation, and fact-checking skills.
- `frontend-browser`: UI implementation, browser automation, and screenshots.
- `security` or `ctf-*`: specialized security and challenge playbooks.
- `docs`: document conversion, writing, diagrams, and presentation skills.
- Team-specific groups: only when the skill set is clearly tied to one workflow.

## Validate and preview

Before moving directories:

```bash
agent-skill-groups validate --config groups.json --runtime claude-code
agent-skill-groups doctor --config groups.json --runtime claude-code
agent-skill-groups status --config groups.json --runtime claude-code --details
agent-skill-groups plan --config groups.json --runtime claude-code research
```

`plan` is the important guardrail. It shows which managed skills would be enabled and disabled for the requested profile.

## Switch profiles

Back up before profile changes:

```bash
agent-skill-groups backup --config groups.json --runtime claude-code
agent-skill-groups profile --config groups.json --runtime claude-code research
```

Return to a lean default:

```bash
agent-skill-groups profile --config groups.json --runtime claude-code core
```

## Agent memory

Once the group table is stable, write a managed memory block:

```bash
agent-skill-groups memory --config groups.json --runtime claude-code --write CLAUDE.md
```

Use `AGENTS.md` for Codex or OpenCode when that runtime reads project agent instructions:

```bash
agent-skill-groups memory --config groups.json --runtime codex --write AGENTS.md
```

## Recovery

Inspect current state:

```bash
agent-skill-groups status --config groups.json --runtime claude-code --details
```

Restore a saved state:

```bash
agent-skill-groups restore --config groups.json --runtime claude-code backup.json
```

If a skill folder was moved manually, rerun `doctor` and resolve the filesystem mismatch before switching profiles again.

## Canonical references

- Repository: <https://github.com/go165/agent-skill-groups>
- Documentation: <https://go165.github.io/agent-skill-groups/>
- Runtime guide: <https://github.com/go165/agent-skill-groups/blob/main/docs/RUNTIMES.md>
- Real-world test plan: <https://github.com/go165/agent-skill-groups/blob/main/docs/REAL_WORLD_TEST.md>
