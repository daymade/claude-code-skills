# Plugin and Skill Architecture

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

**Loading mechanism** ([official Skill lifecycle](https://code.claude.com/docs/en/skills)):
1. **Metadata**: Advertised under the host's discovery policy and catalog budget; not every installed description is guaranteed to reach a fresh prompt
2. **SKILL.md body**: Loaded when Claude invokes the Skill or reads its instructions
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

Single-skill plugin (official pattern — `source` points to skill directory, no `skills` field):
```json
{
  "name": "my-plugin",
  "description": "Use when...",
  "source": "./my-plugin",
  "version": "1.0.0",
  "category": "utilities",
  "keywords": ["keyword1", "keyword2"]
}
```

Suite plugin (multiple skills under one namespace — `skills` required):
```json
{
  "name": "my-suite",
  "description": "Suite description",
  "source": "./my-suite",
  "version": "1.0.0",
  "skills": ["./skill-1", "./skill-2"]
}
```

Use the marketplace manifest for current plugin sources and suite membership. The shapes above illustrate the distinction; they are not a maintained catalog.

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
    ├── Metadata (subject to discovery policy and catalog budget)
    ├── SKILL.md (loaded when relevant)
    └── Resources (loaded as needed)
```

## Installation Flow

### Step 1: User initiates installation
```bash
claude plugin install daymade-macos@daymade-skills
```

### Step 2: CLI locates marketplace
```bash
# Check ~/.claude/plugins/marketplaces/daymade-skills/
# If not exists, git clone from GitHub
```

### Step 3: Resolve the registered plugin

Read the plugin's `source` and optional `skills` membership from
`.claude-plugin/marketplace.json`. Resolve suite members relative to the suite
source; do not copy a current member list or version into this guide.

### Step 4: Install the plugin content

The official CLI installs into a versioned cache directory. The maintainer
[source-backed layout](../daymade-claude-code/claude-switch-models-setup/references/local-source-sync-architecture.md)
is a separate supported local workflow; its cache and personal links can resolve
to canonical checkouts.

### Step 5: Read the installation record

Inspect the current CLI output and `installed_plugins.json` for the exact
qualified identity, scope, version, and install path. Do not infer the active
route from a cache basename or a sample record.

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

| Myth | Reality |
|------|---------|
| "Updating local files immediately updates the plugin" | Git-backed installed copies need publication and update; source-backed maintainer links read their checkout. Identify the layout first. |
| "Skills and plugins are the same thing" | Skills are functional units (SKILL.md + resources). Plugins are distribution packages (can contain multiple skills). |
| "marketplace.json is just metadata" | marketplace.json is the **source of truth** for plugin discovery. Without correct configuration here, `claude plugin install` will fail. |
| "Cache is just for performance" | Installed records can point at cache content. Deleting it can break live references without updating the installation registry; use official update/uninstall operations. |
| "Skills in ~/.claude/skills/ work the same as plugin skills" | Personal Skills can be source-backed links; plugins have qualified identities, versions, and scope. Verify the actual route and owner rather than treating the paths as equivalent. |

## Best Practices

### For Skill Authors

1. **Clear metadata**: Description should clearly state "Use when..." to help Claude match user intent
2. **Progressive disclosure**: Keep SKILL.md lean, move details to `references/`
3. **Test locally first**: Follow [the maintainer source workflow](../CLAUDE.md#testing-skills-locally) and its target-host gate; do not create a mutable second copy
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
3. **Repair the affected install**: Follow the installed `skill-governance` plugin workflow; preserve running-session resources and avoid blanket cache deletion
4. **Understand scopes**:
   - `--scope user`: Only you (default)
   - `--scope project`: Shared with team via `.claude/plugins/`
   - `--scope local`: Gitignored, local only
