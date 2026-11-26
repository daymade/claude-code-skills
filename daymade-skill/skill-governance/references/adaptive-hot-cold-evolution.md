# Adaptive Hot/Cold Skill Surface Self-Evolution

`scripts/evolve_skill_surface.py` turns the Skill catalog across **Antigravity**,
**Codex**, and **Claude Code** into an adaptive L1/L2 cache:

- **Hot Set (L1, preloaded ~50 Skills)**: `skills-search`, all domain Routers,
  user-pinned core discipline Skills, and the highest-scoring active Skills.
  Eliminates Antigravity truncation and cuts prompt metadata size by ~89%.
- **Cold Pool (L2, on-disk ~340 Skills)**: stays physically intact in
  `~/.agents/skills/` and local source repos. Agents browse compact domain
  categories via `skills-search` (`runtime_search.py` or `local-skills-search`
  MCP); in Claude Code, personal cold Skills are set to `user-invocable-only`
  so manual `/skill-name` still works directly.
  - **Claude Code plugin boundary**: Claude Code `2.1.x` ignores `skillOverrides`
    for enabled non-`anthropic-skills` plugins. `project_claude` explicitly
    reports `plugin_bypassed_cold_count` instead of claiming plugins were hidden;
    to hide a standalone cold plugin in Claude Code, disable it in `enabledPlugins`.

## SSOT & State Files

| File | Purpose |
| --- | --- |
| `~/.config/skill-governance/hot-set.json` | Single source of truth for `pinned`, `dynamic_hot`, `router_children`, `blocked_cold`, policy thresholds, and history |
| `~/.config/skill-governance/aliases.json` | Sanitized self-learned `query -> skill` search aliases read by `skills-search` |
| `~/.local/share/skill-governance/telemetry.jsonl` | Locked runtime `search` / `load` telemetry emitted by `skills-search` |
| `~/.local/share/skill-governance/.evolve-status` | Health heartbeat with elapsed seconds, mode, and ledger refresh or reuse on success |
| `~/.config/skill-governance/backups/<ts>/` | Atomic pre-apply backups (retained up to latest 20) + `manifest.json` |
| `~/.local/share/skill-governance/reports/latest.md` | Latest human-readable evolution report |

## Workflow

```bash
# 1. Refresh Claude + Codex usage ledger
python3 <read-claude-code-history>/scripts/skill_usage_ledger.py index

# 2. Bootstrap hot-set.json (dry-run first, then --write)
python3 <skill-governance>/scripts/evolve_skill_surface.py init --max-hot 50
python3 <skill-governance>/scripts/evolve_skill_surface.py init --max-hot 50 --write

# 3. Read-only evolution proposal
python3 <skill-governance>/scripts/evolve_skill_surface.py propose --markdown

# 4. Apply to hosts with transactional rollback & true no-op when unchanged
python3 <skill-governance>/scripts/evolve_skill_surface.py apply --hosts antigravity,codex,claude --auto-aliases

# 5. Roll back any apply atomically (binary-safe, preserves permissions)
python3 <skill-governance>/scripts/evolve_skill_surface.py rollback --backup ~/.config/skill-governance/backups/<ts>

# 6. Install macOS suggestions on telemetry changes with periodic ledger refresh
python3 <skill-governance>/scripts/evolve_skill_surface.py install-schedule --interval-minutes 30 --throttle-seconds 60
```

In the default proposal mode, the periodic LaunchAgent refreshes the ledger
and regenerates the report. Its companion `-telemetry` LaunchAgent regenerates
the report after a telemetry update and reuses the last successful ledger
unless the database is missing or changed. Both share a lock. The runner can
regenerate the report once if telemetry changes during proposal generation.

## Safety Invariants

- Router children (`router_children`) and retired Skills (`blocked_cold`) are
  never promoted into `dynamic_hot`.
- Claude Code's explicit `"off"` overrides are never overwritten; `project_claude`
  coordinates with `ai.daymade.claude-skill-source-sync` and `claude-plugins-sync.py`
  using the exact shared lock protocol (`0o600` `~/.claude/.daymade-skill-sync.lock.guard`
  `fcntl.flock` + `0o700` `~/.claude/.daymade-skill-sync.lock/` directory/PID marker).
- Codex's nested paths (e.g. `ima-skill/knowledge-base/SKILL.md`), `.system/*`,
  and `gstack/*` entries are preserved; cold nested & `~/.codex/skills` duplicates
  are also disabled and validated with Python 3.11+ `tomllib`.
- LaunchAgent resolves a Python 3.11+ runtime (live `tomllib`), uses kernel
  `fcntl.flock`, and fails loud if `skill_usage_ledger.py` is missing.
- Every `apply` runs under `.apply.lock`, backs up all targets before mutation,
  auto-rolls back on error, and cleans unused backups on no-op runs.
