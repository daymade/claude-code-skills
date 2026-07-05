# daymade-skill Suite

This directory bundles skills related to Claude Code skill development, quality, and governance.

## Included Skills

- `skill-creator` — Create and improve skills.
- `skill-reviewer` — Review skill quality and trigger accuracy.
- `skills-search` — Search across the skill marketplace.
- `skill-governance` — Enforce source-of-truth discipline for skill caches and marketplaces.

## Governance Principles

The `skill-governance` skill encodes the operational workflow for keeping skill caches aligned with their source repositories. When working in this suite, observe the same principles:

1. **Source is truth** — The source repo is canonical. If the cache is stale, rebuild from source.
2. **Official methods only** — Use `claude plugin marketplace`, `claude plugin update`, `claude plugin uninstall`, and `claude plugin install`. Do not manually delete cache directories or copy files as the primary installation method.
3. **Scope preservation** — Reinstall a plugin at the same scope (`user` or `project`) it was originally installed at.
4. **One version per skill in cache** — After syncing, remove old semver version subdirectories so only the latest remains.
5. **No-op safety** — Drift checks are read-only. Sync and cleanup run only after user confirmation or explicit trigger.
6. **Workspace dirs are not plugins** — Ignore `*-workspace`, `dist`, `scripts`, `tests`, `references`, `demos`, and similar directories when deciding what should be cached.

For the full workflow, invoke `daymade-skill:skill-governance`.
