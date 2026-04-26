# marketplace.json Complete Schema Reference

Source: https://code.claude.com/docs/en/plugin-marketplaces + https://code.claude.com/docs/en/plugins-reference
Verified against Claude Code source code and `claude plugin validate`.

## Root Level

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | **Yes** | Marketplace identifier, kebab-case. Users see this: `plugin install X@<name>` |
| `owner` | object | **Yes** | `name` (required string), `email` (optional string) |
| `plugins` | array | **Yes** | Array of plugin entries |
| `metadata` | object | No | See metadata fields below |

### metadata fields (ONLY these 3 are valid)

| Field | Type | Description |
|-------|------|-------------|
| `metadata.description` | string | Brief marketplace description |
| `metadata.version` | string | Marketplace catalog version (NOT plugin version) |
| `metadata.pluginRoot` | string | Base directory prepended to relative plugin source paths |

**Invalid metadata fields** (silently ignored or rejected):
- `metadata.homepage` — does NOT exist in spec
- `metadata.repository` — does NOT exist in spec
- `$schema` — REJECTED by `claude plugin validate`

## Plugin Entry Fields

Each entry in the `plugins` array. Can include any field from the plugin.json
manifest schema, plus marketplace-specific fields.

### Required

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Plugin identifier, kebab-case |
| `source` | string or object | Where to fetch the plugin |

### Standard metadata (from plugin.json schema)

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Brief plugin description |
| `version` | string | Plugin version (independent of metadata.version) |
| `author` | object | `name` (required), `email` (optional), `url` (optional) |
| `homepage` | string | Plugin homepage URL |
| `repository` | string | Source code URL |
| `license` | string | SPDX identifier (MIT, Apache-2.0, etc.) |
| `keywords` | array | Tags for discovery (currently unused in search) |

### Marketplace-specific

| Field | Type | Description |
|-------|------|-------------|
| `category` | string | Freeform category for organization |
| `tags` | array | Tags for searchability (only `community-managed` has UI effect) |
| `strict` | boolean | Default: true. Set false when no plugin.json exists |

### Component paths (from plugin.json schema)

| Field | Type | Description |
|-------|------|-------------|
| `commands` | string or array | Custom command file/directory paths |
| `agents` | string or array | Custom agent file paths |
| `skills` | string or array | Custom skill directory paths |
| `hooks` | string or object | Hook configuration or path |
| `mcpServers` | string or object | MCP server config or path |
| `lspServers` | string or object | LSP server config or path |
| `outputStyles` | string or array | Output style paths |
| `userConfig` | object | User-configurable values prompted at enable time |
| `channels` | array | Channel declarations for message injection |

## Source Types

| Source | Format | Example |
|--------|--------|---------|
| Relative path | string `"./"` | `"source": "./"` |
| GitHub | object | `{"source": "github", "repo": "owner/repo"}` |
| Git URL | object | `{"source": "url", "url": "https://..."}` |
| Git subdirectory | object | `{"source": "git-subdir", "url": "...", "path": "..."}` |
| npm | object | `{"source": "npm", "package": "@scope/pkg"}` |

All object sources support optional `ref` (branch/tag) and `sha` (40-char commit).

## Reserved Marketplace Names

Cannot be used: `claude-code-marketplace`, `claude-code-plugins`,
`claude-plugins-official`, `anthropic-marketplace`, `anthropic-plugins`,
`agent-skills`, `knowledge-work-plugins`, `life-sciences`.

Names impersonating official marketplaces are also blocked.
