# Claude Code Architecture: Plugins, Skills, and Agents

This document explains the architecture of Claude Code's extension system and how different components work together.

## Core Concepts

### 1. Skills

**What**: Functional units that extend Claude's capabilities with specialized knowledge and workflows.

**Structure**:
```
skill-name/
├── SKILL.md (required)          # YAML frontmatter + Markdown instructions
├── scripts/ (optional)          # Executable code (Python/Bash)
├── references/ (optional)       # Documentation loaded as needed
└── assets/ (optional)           # Templates and resources
```

**Loading mechanism** (Progressive Disclosure):
1. **Metadata** (~100 tokens): Always in context (name + description from YAML frontmatter)
2. **SKILL.md body** (<5k tokens): Loaded when Claude determines the skill applies
3. **Bundled resources**: Loaded only as needed by Claude

**Location**:
- **Personal**: `~/.claude/skills/` (user-specific, not shared)
- **Project**: `.claude/skills/` (checked into git, shared with team)
- **Plugin cache**: `~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/{skill}/`

**Example**: When you ask "analyze my disk space", Claude loads the `macos-cleaner` skill's SKILL.md, then reads `references/cleanup_targets.md` as needed.

### 2. Plugins

**What**: Distribution units that package one or more skills for installation via marketplaces.

**Purpose**: Plugins enable:
- One-command installation (`claude plugin install skill-name@marketplace-name`)
- Version management
- Dependency tracking
- Marketplace distribution

**Relationship to Skills**:
```
Plugin (marketplace.json entry)
├── Skill 1 (./skill-name-1/)
├── Skill 2 (./skill-name-2/)
└── Skill 3 (./skill-name-3/)
```

**Configuration** (in `.claude-plugin/marketplace.json`):
```json
{
  "name": "my-plugin",
  "description": "Use when...",
  "version": "1.0.0",
  "category": "utilities",
  "keywords": ["keyword1", "keyword2"],
  "skills": ["./skill-1", "./skill-2"]
}
```

**Example**: The `skill-creator` plugin contains one skill (`./skill-creator`), while a hypothetical `developer-tools` plugin might contain multiple skills like `./git-helper`, `./code-reviewer`, `./test-runner`.

### 3. Agents (Subagents)

**What**: Specialized autonomous agents invoked via the `Task` tool for complex, multi-step operations.

**Types**:
- **Bash**: Command execution specialist
- **general-purpose**: Research, search, multi-step tasks
- **Explore**: Fast codebase exploration
- **Plan**: Software architecture planning
- **skill-creator**: Meta-agent for creating skills
- **Custom**: Domain-specific agents (e.g., `test-runner`, `build-validator`)

**When to use**:
- Tasks requiring multiple rounds of tool calls
- Open-ended exploration (finding files, searching code)
- Planning before implementation
- Autonomous execution without user intervention

**Example**:
```python
# Instead of manually searching multiple times:
Task(
    subagent_type="Explore",
    description="Find error handling code",
    prompt="Search the codebase for error handling patterns and list all files that handle HTTP errors"
)
```

### 4. Commands

**What**: Slash commands (e.g., `/commit`, `/review-pr`) that trigger skills.

**Relationship**: Commands are shortcuts to invoke skills.
- `/commit` → invokes `commit` skill
- `/review-pr` → invokes `review-pr` skill

**Configuration**: Defined in plugin's `commands/` directory or skill metadata.

## Architecture Diagram

```
Marketplace (GitHub)
    ↓ (git clone)
~/.claude/plugins/marketplaces/{marketplace-name}/
    ↓ (plugin install)
~/.claude/plugins/cache/{marketplace-name}/{plugin}/{version}/
    ├── skill-1/
    │   ├── SKILL.md
    │   ├── scripts/
    │   └── references/
    └── skill-2/
        └── SKILL.md
    ↓ (Claude loads)
Claude Code Context
    ├── Metadata (always loaded)
    ├── SKILL.md (loaded when relevant)
    └── Resources (loaded as needed)
```

## Installation Flow

### Step 1: User initiates installation
```bash
claude plugin install macos-cleaner@daymade-skills
```

### Step 2: CLI locates marketplace
```bash
# Check ~/.claude/plugins/marketplaces/daymade-skills/
# If not exists, git clone from GitHub
```

### Step 3: Read marketplace.json
```json
{
  "plugins": [
    {
      "name": "macos-cleaner",
      "version": "1.0.0",
      "skills": ["./macos-cleaner"]
    }
  ]
}
```

### Step 4: Download to cache
```bash
# Clone entire marketplace repo to:
~/.claude/plugins/cache/daymade-skills/macos-cleaner/1.0.0/

# Extract skill to:
~/.claude/plugins/cache/daymade-skills/macos-cleaner/1.0.0/macos-cleaner/
```

### Step 5: Record installation
```json
// ~/.claude/plugins/installed_plugins.json
{
  "plugins": {
    "macos-cleaner@daymade-skills": [{
      "scope": "user",
      "installPath": "~/.claude/plugins/cache/daymade-skills/macos-cleaner/1.0.0",
      "version": "1.0.0",
      "installedAt": "2026-01-11T08:03:46.593Z"
    }]
  }
}
```

### Step 6: Claude Code loads skill
```
When user asks: "My Mac is running out of space"
    ↓
Claude scans installed plugins metadata
    ↓
Finds "macos-cleaner" description matches
    ↓
Loads SKILL.md into context
    ↓
Executes workflow (analyze → report → confirm → cleanup)
    ↓
Loads references/scripts as needed
```

## Key Files and Locations

### Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| `marketplace.json` | `~/.claude/plugins/marketplaces/{name}/.claude-plugin/` | Defines available plugins |
| `installed_plugins.json` | `~/.claude/plugins/` | Tracks installed plugins |
| `known_marketplaces.json` | `~/.claude/plugins/` | Lists registered marketplaces |

### Directory Structure

```
~/.claude/
├── skills/                          # Personal skills (not from marketplace)
├── plugins/
│   ├── marketplaces/                # Marketplace clones
│   │   ├── daymade-skills/          # Marketplace name
│   │   │   └── .claude-plugin/
│   │   │       └── marketplace.json
│   │   └── anthropic-agent-skills/
│   ├── cache/                       # Installed plugins
│   │   └── daymade-skills/
│   │       └── macos-cleaner/
│   │           └── 1.0.0/           # Version
│   │               └── macos-cleaner/  # Skill directory
│   │                   ├── SKILL.md
│   │                   ├── scripts/
│   │                   └── references/
│   ├── installed_plugins.json       # Installation registry
│   └── known_marketplaces.json      # Marketplace registry
```

## Data Flow

### Skill Activation
```
User message
    ↓
Claude analyzes installed plugin metadata
    ↓
Matches description to user intent
    ↓
Loads SKILL.md (progressive disclosure)
    ↓
Executes instructions
    ↓
Loads bundled resources (scripts, references) as needed
    ↓
Generates response
```

### Plugin Update
```
Local changes to skill
    ↓
git add & commit
    ↓
git push to GitHub
    ↓
User runs: claude plugin marketplace update {marketplace-name}
    ↓
CLI pulls latest from GitHub
    ↓
Updates ~/.claude/plugins/marketplaces/{marketplace-name}/
    ↓
User runs: claude plugin update {plugin-name@marketplace}
    ↓
Re-downloads to cache with new version number
    ↓
Updates installed_plugins.json
```

## Common Misconceptions

### ❌ Myth 1: "Updating local files immediately updates the plugin"
**Reality**: Plugins are distributed via GitHub. Local changes require `git push` before users can install updates.

### ❌ Myth 2: "Skills and plugins are the same thing"
**Reality**: Skills are functional units (SKILL.md + resources). Plugins are distribution packages (can contain multiple skills).

### ❌ Myth 3: "marketplace.json is just metadata"
**Reality**: marketplace.json is the **source of truth** for plugin discovery. Without correct configuration here, `claude plugin install` will fail with "Plugin not found".

### ❌ Myth 4: "Cache is just for performance"
**Reality**: Cache (`~/.claude/plugins/cache/`) is where installed plugins actually live. Deleting cache uninstalls all plugins.

### ❌ Myth 5: "Skills in ~/.claude/skills/ work the same as plugin skills"
**Reality**:
- `~/.claude/skills/` = Personal skills (manual management, no versioning)
- Plugin cache = Managed by CLI (versioned, updateable, shareable)

## Best Practices

### For Skill Authors

1. **Clear metadata**: Description should clearly state "Use when..." to help Claude match user intent
2. **Progressive disclosure**: Keep SKILL.md lean, move details to `references/`
3. **Test locally first**: Copy to `~/.claude/skills/` for testing before packaging
4. **Version properly**: Use semver (MAJOR.MINOR.PATCH) in marketplace.json
5. **Document bundled resources**: All scripts and references should be mentioned in SKILL.md

### For Marketplace Maintainers

1. **Git workflow**: Always `git push` after updating marketplace.json
2. **Validate JSON**: Run `python -m json.tool marketplace.json` before committing
3. **Update cache**: Remind users to run `claude plugin marketplace update` after releases
4. **Version consistency**: Marketplace version ≠ plugin versions (they track independently)

### For Users

1. **Update marketplaces**: Run `claude plugin marketplace update {name}` periodically
2. **Check installed plugins**: Inspect `~/.claude/plugins/installed_plugins.json`
3. **Clear cache on issues**: `rm -rf ~/.claude/plugins/cache/{marketplace-name}` then reinstall
4. **Understand scopes**:
   - `--scope user`: Only you (default)
   - `--scope project`: Shared with team via `.claude/plugins/`
   - `--scope local`: Gitignored, local only

## Troubleshooting Guide

See [CLAUDE.md § Plugin and Skill Troubleshooting](#plugin-and-skill-troubleshooting) for detailed debugging steps.

## References

- [Official Skills Documentation](https://code.claude.com/docs/en/skills)
- [Plugin Reference](https://code.claude.com/docs/en/plugins-reference)
- [Marketplace Discovery](https://code.claude.com/docs/en/discover-plugins)
- [Anthropic Skills Best Practices](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices.md)
