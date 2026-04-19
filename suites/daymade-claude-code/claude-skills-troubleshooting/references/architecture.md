# Claude Code Plugin Architecture

## Directory Structure

```
~/.claude/
├── settings.json                    # User settings including enabledPlugins
├── plugins/
│   ├── installed_plugins.json       # Registry of ALL plugins (enabled + disabled)
│   ├── known_marketplaces.json      # Registered marketplace sources
│   ├── marketplaces/                # Marketplace git clones
│   │   ├── marketplace-name/
│   │   │   └── .claude-plugin/
│   │   │       └── marketplace.json # Plugin definitions
│   │   └── ...
│   └── cache/                       # Installed plugin files
│       └── marketplace-name/
│           └── plugin-name/
│               └── version/
│                   └── skill-name/
│                       ├── SKILL.md
│                       ├── scripts/
│                       └── references/
└── skills/                          # Personal skills (not from marketplace)
```

## Plugin Lifecycle

### Installation Flow

```
1. User runs: claude plugin install plugin@marketplace
       ↓
2. CLI reads marketplace.json from marketplace directory
       ↓
3. Plugin files copied to cache:
   ~/.claude/plugins/cache/marketplace/plugin/version/
       ↓
4. Entry added to installed_plugins.json:
   { "plugin@marketplace": [{ "version": "1.0.0", ... }] }
       ↓
5. ⚠️ BUG: Entry NOT automatically added to settings.json enabledPlugins
       ↓
6. User must manually enable:
   claude plugin enable plugin@marketplace
       ↓
7. Entry added to settings.json:
   { "enabledPlugins": { "plugin@marketplace": true } }
```

### Activation Flow

```
1. Claude Code starts
       ↓
2. Reads settings.json → enabledPlugins
       ↓
3. For each enabled plugin:
   - Loads skill metadata (name + description)
   - Metadata added to system prompt
       ↓
4. User sends message
       ↓
5. Claude matches message against skill descriptions
       ↓
6. Matching skill's SKILL.md loaded into context
       ↓
7. Claude uses skill instructions to respond
```

## Key Files Explained

### installed_plugins.json

**Purpose:** Registry of all plugins ever installed (NOT just active ones).

**Structure:**
```json
{
  "version": 2,
  "plugins": {
    "plugin-name@marketplace": [
      {
        "scope": "user",
        "installPath": "~/.claude/plugins/cache/...",
        "version": "1.0.0",
        "installedAt": "2025-01-01T00:00:00.000Z"
      }
    ]
  }
}
```

**Note:** A plugin listed here is NOT necessarily active. Check `settings.json` for actual enabled state.

### settings.json

**Purpose:** User preferences and enabled plugins.

**Relevant section:**
```json
{
  "enabledPlugins": {
    "plugin-name@marketplace": true,
    "another-plugin@marketplace": true
  }
}
```

**Important:** Only plugins with `true` value are loaded at startup.

### known_marketplaces.json

**Purpose:** Registry of marketplace sources.

**Structure:**
```json
{
  "marketplace-name": {
    "source": {
      "source": "github",
      "repo": "owner/repo"
    },
    "installLocation": "~/.claude/plugins/marketplaces/marketplace-name",
    "lastUpdated": "2025-01-01T00:00:00.000Z"
  }
}
```

### marketplace.json (in marketplace repo)

**Purpose:** Defines available plugins in a marketplace.

**Location:** `.claude-plugin/marketplace.json`

**Structure:**
```json
{
  "name": "marketplace-name",
  "metadata": {
    "version": "1.0.0",
    "description": "..."
  },
  "plugins": [
    {
      "name": "plugin-name",
      "description": "...",
      "version": "1.0.0",
      "skills": ["./skill-directory"]
    }
  ]
}
```

## Plugin vs Skill vs Command

### Plugin

- Distribution unit that packages one or more skills
- Defined in marketplace.json
- Installed via `claude plugin install`

### Skill

- Functional unit with SKILL.md and optional resources
- Auto-activates based on description matching
- Located in `skills/` directory

### Command

- Explicit slash command (e.g., `/seer`)
- Defined in `commands/` directory
- Appears in Skill tool's available list
- Must be explicitly invoked by user

## Scopes

Plugins can be installed in different scopes:

| Scope | Location | Visibility |
|-------|----------|------------|
| user | `~/.claude/settings.json` | All projects for current user |
| project | `.claude/settings.json` | Team members via git |
| local | `.claude/settings.local.json` | Only local machine |

## Common Misconceptions

1. **installed_plugins.json = active plugins**
   - Reality: It's a registry of ALL plugins, including disabled ones

2. **Plugins auto-enable after install**
   - Reality: Bug prevents auto-enable; manual step required

3. **Updating local files updates the plugin**
   - Reality: Must push to GitHub, then update marketplace cache

4. **Cache is just for performance**
   - Reality: Cache IS where plugins live; deleting it uninstalls plugins
