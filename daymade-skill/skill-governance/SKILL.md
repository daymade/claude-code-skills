---
name: skill-governance
description: >-
  Enforce source-of-truth discipline for Claude Code skill marketplaces and caches. Use whenever the user says "check skill drift", "检查 skill 漂移", "sync skills from source", "以源码为准同步 skill 缓存", "clean old skill cache versions", "清理 skill 缓存旧版本", "switch marketplace to local source", "marketplace 切到本地源码", or talks about skill caches being stale, version mismatches, orphaned plugins, or rebuilding the marketplace cache from a local source repo.
---

# Skill Governance

This skill keeps Claude Code skill marketplaces and their caches aligned with their source repositories. The source directory is the single source of truth; the cache is a derived copy. When the source changes, the cache must be rebuilt through official `claude plugin` commands, not by hand-copying files.

## Governance Principles

1. **Source is truth** — The local source repo is canonical. If the cache is older or different, rebuild the cache from source.
2. **Official methods only** — Use `claude plugin marketplace`, `claude plugin update`, `claude plugin uninstall`, and `claude plugin install`. Manual cache deletion or file copying is only a cleanup step, never the primary installation method.
3. **Scope preservation** — Reinstall each plugin at the scope (`user` or `project`) where it was originally installed.
4. **One version per skill in cache** — After syncing, remove old semver version subdirectories so only the latest remains.
5. **No-op safety** — Drift checks are read-only. Sync and cleanup run only after user confirmation or an explicit trigger.
6. **Workspace dirs are not plugins** — Ignore `*-workspace`, `dist`, `scripts`, `tests`, `references`, `demos`, and other non-plugin directories when deciding what belongs in the cache.

## What to ignore when comparing source to cache

`.git`, `.in_use`, `.security-scan-passed`, `.orphaned_at`, `.DS_Store`, `.gitignore`, `__pycache__`, `.pytest_cache`, `.venv`, `node_modules`, `*.pyc`, `*.pyo`.

Also ignore top-level directories that are not skills: `*-workspace`, `dist`, `scripts`, `tests`, `references`, `demos`.

## Workflow A: Check skill drift / 检查 skill 漂移

This is a read-only report. It does not modify anything.

1. Identify the marketplaces to check. Defaults are `daymade-skills` and `daymade-skills-pro`; use the marketplace the user names if they name one.
2. For each marketplace, find its source repo by reading `.claude-plugin/marketplace.json` in the source directory.
3. For each plugin entry in `marketplace.json`:
   - Locate the source directory (`source` field).
   - If the plugin is a suite with a `skills` array, treat the suite root as the source for the bundled sub-skills. Do not inspect the individual sub-skill directories separately.
   - Find the latest semver version subdirectory in `~/.claude/plugins/cache/<marketplace>/<plugin>/`.
   - Compare the source directory to that version directory, ignoring the patterns above.
   - Record:
     - **Stale** — content differs.
     - **Version mismatch** — `marketplace.json` version != latest cache version.
     - **Missing from cache** — listed in source but no cache subdirectory exists.
     - **Orphaned in cache** — cache subdirectory exists but plugin is not in `marketplace.json`.
4. Check `~/.claude/skills/` for direct-copy installs:
   - Any directory there that is not a symlink and differs from its source is flagged as a direct-copy drift.
   - Symlinks are expected for dev skills and are ignored.
5. Return a concise markdown report grouped by marketplace, with sections: Stale, Version mismatch, Missing, Orphaned, Direct-copy drift.

## Workflow B: Sync skills from source / 以源码为准同步 skill 缓存

This mutates cache state. Confirm with the user before proceeding unless they explicitly triggered the sync.

1. Determine target marketplace(s). If none specified, use both `daymade-skills` and `daymade-skills-pro`.
2. For each marketplace:
   - Run `claude plugin marketplace list` to verify the marketplace points to the expected local source path.
   - If it points elsewhere, run Workflow D first to switch it to the local source.
   - Run `claude plugin marketplace update <marketplace>`.
3. Run Workflow A to get the drift report.
4. For each stale or missing plugin:
   - Determine its installed scope. Look at the existing install metadata in `~/.claude/plugins/cache/<marketplace>/<plugin>/latest/` or infer from `~/.claude/plugins/installed_plugins.json`. Default to the scope it was originally installed at; if unknown, ask the user.
   - For suite plugins, install the suite once. Do not install individual sub-skills separately.
   - Run:
     ```
     claude plugin uninstall <plugin>@<marketplace> --scope <scope>
     claude plugin install <plugin>@<marketplace> --scope <scope>
     ```
   - This forces the cache to re-fetch from the current local source.
5. For orphaned plugins, uninstall them at the scope they were installed at.
6. After installation, run Workflow C to clean old version subdirectories.
7. Report what was updated, what was uninstalled, and any failures.

## Workflow C: Clean old skill cache versions / 清理 skill 缓存旧版本

This deletes cache directories. Confirm with the user before proceeding.

1. For each skill directory under `~/.claude/plugins/cache/<marketplace>/`:
   - List all semver version subdirectories (e.g., `1.0.0`, `1.1.0`).
   - Identify the latest version by semver ordering.
   - Before deleting, verify the latest version matches the source (e.g., by re-running Workflow A or comparing the latest cache dir to source). If it does not match, do not delete old versions; warn the user and stop.
   - Delete every version subdirectory except the latest.
2. Report which versions were removed and which remain.

## Workflow D: Switch marketplace to local source / marketplace 切到本地源码

1. Run `claude plugin marketplace list` to see the current source.
2. If the marketplace is not already pointing to the desired local path:
   ```
   claude plugin marketplace remove <marketplace-name>
   claude plugin marketplace add <local-path> --scope user
   ```
3. Verify with `claude plugin marketplace list`.
4. Report the new source path.

## Suite plugins

The following suites bundle multiple sub-skills. Install or reinstall the suite once; never try to install the individual sub-skills separately:

- `daymade-audio`
- `daymade-claude-code`
- `daymade-docs`
- `daymade-financial`
- `daymade-skill`

## Reporting format

Use this markdown template for drift reports and sync summaries:

```markdown
# Skill Governance Report: <Marketplace>

## Drift Summary
- Stale: N
- Version mismatch: N
- Missing from cache: N
- Orphaned in cache: N
- Direct-copy drift: N

## Stale Plugins
| Plugin | Cache Version | Source Version | Scope |
|--------|---------------|----------------|-------|

## Version Mismatch
| Plugin | Cache Version | Marketplace Version |
|--------|---------------|---------------------|

## Missing from Cache
| Plugin | Source Version |
|--------|----------------|

## Orphaned in Cache
| Plugin | Cache Version |
|--------|---------------|

## Direct-Copy Drift in ~/.claude/skills/
| Skill | Issue |
|-------|-------|

## Actions Taken
- ...

## Failures
- ...
```

## Troubleshooting

- **Cache version differs but marketplace update did nothing** — The marketplace may still point to an old source. Run Workflow D first.
- **Uninstall fails because scope is wrong** — Re-check `installed_plugins.json` or the cache directory metadata for the actual scope.
- **Latest cache dir does not match source after sync** — The marketplace may have cached metadata. Run `claude plugin marketplace update <marketplace>` again and reinstall.
- **Suite sub-skills reported individually** — This is a mistake. Suites are installed as one unit; bundle sub-skills only for comparison purposes, not for install/uninstall.
- **Old versions reappear after cleanup** — A stale marketplace source or an active Claude Code session may recreate them. Re-run Workflow B first, then Workflow C.
