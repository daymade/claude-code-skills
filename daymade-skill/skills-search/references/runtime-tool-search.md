# Runtime Cold-Library Tool Search (`runtime_search.py` & `mcp_server.py`)

When the host preloads only a compact Hot Set + domain Routers (~50 Skills), the
remaining installed Skills stay physically on disk under `~/.agents/skills` (and
configured extra local repos). Use `runtime_search.py` or its zero-dependency
stdio MCP server `mcp_server.py` for **Agent-native semantic catalog browsing**
and bounded on-demand loading.

## CLI Usage (Zero External Dependencies, Python 3.9+)

```bash
# 1. Inspect 9 compact domain categories (~220 tokens)
python3 <skill-dir>/scripts/runtime_search.py categories --raw

# 2. Browse bounded 1-line summaries for one category (Agent picks semantically)
python3 <skill-dir>/scripts/runtime_search.py browse macos-infra-ops --raw

# (Isolated subagent only) Full scan across all cold skills:
python3 <skill-dir>/scripts/runtime_search.py browse all --confirm-full-scan --raw

# 3. Exact-keyword shortcut when a product/service name is already known
python3 <skill-dir>/scripts/runtime_search.py search 'douban' --limit 8

# 4. Load bounded SKILL.md (default 16K chars/page, paginate with --offset) + scripts/references
python3 <skill-dir>/scripts/runtime_search.py get macos-load-doctor --query 'CPU异常进程排查' --raw

# 5. Add a learned alias or inspect telemetry summary
python3 <skill-dir>/scripts/runtime_search.py alias-add --skill douban-skill --term 书影音导出
python3 <skill-dir>/scripts/runtime_search.py stats
```

## Local Stdio MCP Server

Configure in `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "local-skills-search": {
      "command": "/usr/bin/python3",
      "args": [
        "<HOME>/.agents/skills/skills-search/scripts/mcp_server.py",
        "--host",
        "antigravity"
      ]
    }
  }
}
```

Tools exposed (4):
- `list_skill_categories(project?, include_hot?)` — compact (~220-token) category overview; does not trigger WatchPaths telemetry.
- `browse_skill_category(category, max_items?, offset?, confirm_full_scan?, project?, include_hot?)` — bounded 1-line summaries per category (`category='all'` requires `confirm_full_scan=true`, intended for isolated subagents).
- `search_local_skills(query, terms?, limit?, project?)` — fast exact-keyword / alias shortcut.
- `get_local_skill(name, query?, max_chars?, offset?, project?)` — bounded `SKILL.md` loader (default 16K chars, hard cap 32K, `offset` pagination + TOC headings) plus pruned `scripts/` & `references/` inventory; logs a single `load` telemetry event on `offset == 0`.

## Telemetry & Near-Real-Time Evolution

`search` and initial `load` (`offset == 0`) append sanitized JSONL events under a
shared sidecar lock (`telemetry.jsonl.lock`) to
`~/.local/share/skill-governance/telemetry.jsonl`, consumed by
`skill-governance/scripts/evolve_skill_surface.py`.
