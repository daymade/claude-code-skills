# daymade-skill Suite

This directory bundles skills related to Claude Code skill development, quality, and governance.

## Included Skills

- `skill-creator` — Create and improve skills.
- `skill-reviewer` — Review skill quality and trigger accuracy.
- `skills-search` — Search across the skill marketplace.
- `skill-governance` — Enforce source-of-truth discipline for skill caches and marketplaces.

## Supersede Hook (on-demand, never static)

When the official `skill-creator@claude-plugins-official` plugin is installed alongside this suite, the two skill-creator entries carry near-identical descriptions and Claude picks between them at random. The resolution lives in `skill-creator/scripts/`:

- `setup_supersede_hook.sh {install|uninstall|status}` — consent-based installer invoked from the skill-creator coexistence check. `install` refuses to do anything on machines where the official plugin is absent (zero footprint); otherwise it copies the routing hook into the user's Claude config and registers one `SessionStart` entry in `settings.json` (backed up, idempotent, reversible).
- `supersede-routing-hook.sh` — the routing hook source. The installer copies it as `skill-creator-supersede-hook.sh` in the user's Claude config. It self-checks its preconditions every session and goes silent if either the official plugin or the daymade skill-creator disappears, so stale installs are safe by construction. Non-destructive: the official plugin stays usable when the user asks for it by name.

The suite deliberately ships no static `hooks/hooks.json` — most installs never coexist with the official plugin and must not pay a per-session hook for it.

The kit is also a generator: `skill-creator/scripts/generate_supersede_kit.py` stamps the same conditional installer + routing hook (parameterized from `skill-creator/assets/supersede-kit/` templates) into any user skill that deliberately overlaps an installed plugin. skill-creator's own two scripts are regenerated from those templates — one source, no drift. Decision guide: `skill-creator/references/skill-precedence-and-coexistence.md`.

## Governance Principles

The `skill-governance` skill encodes the operational workflow for keeping skill caches aligned with their source repositories. When working in this suite, observe the same principles:

1. **Source is truth** — The source repo is canonical. If the cache is stale, rebuild from source.
2. **Official methods only** — Use `claude plugin marketplace`, `claude plugin update`, `claude plugin uninstall`, and `claude plugin install`. Do not manually delete cache directories or copy files as the primary installation method.
3. **Scope preservation** — Reinstall a plugin at the same scope (`user` or `project`) it was originally installed at.
4. **One version per skill in cache** — After syncing, remove old semver version subdirectories so only the latest remains.
5. **No-op safety** — Drift checks are read-only. Sync and cleanup run only after user confirmation or explicit trigger.
6. **Workspace dirs are not plugins** — Ignore `*-workspace`, `dist`, `scripts`, `tests`, `references`, `demos`, and similar directories when deciding what should be cached.

For the full workflow, invoke `daymade-skill:skill-governance`.
