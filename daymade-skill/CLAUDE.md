# daymade-skill Suite

This directory bundles skills related to Claude Code skill development, quality, and governance.

## Verification Routing

Before selecting evidence or judging task completion, enter
[skill-creator](skill-creator/SKILL.md). Its
[named task-result examples](skill-creator/references/change-verification.md#named-task-result-examples)
distinguish consumer execution, answer correctness, and correction after supplied evidence.

## Supersede Hook (on-demand, never static)

When the official `skill-creator@claude-plugins-official` plugin is installed alongside this suite, the two skill-creator entries carry near-identical descriptions and Claude picks between them at random. The resolution lives in `skill-creator/scripts/`:

- `setup_supersede_hook.sh {install|uninstall|status}` — consent-based installer invoked from the skill-creator coexistence check. `install` refuses to do anything on machines where the official plugin is absent (zero footprint); otherwise it copies the routing hook into the user's Claude config and registers one `SessionStart` entry in `settings.json` (backed up, idempotent, reversible).
- `supersede-routing-hook.sh` — the routing hook source. The installer copies it as `skill-creator-supersede-hook.sh` in the user's Claude config. It self-checks its preconditions every session and goes silent if either the official plugin or the daymade skill-creator disappears, so stale installs are safe by construction. Non-destructive: the official plugin stays usable when the user asks for it by name.

The suite deliberately ships no static `hooks/hooks.json` — most installs never coexist with the official plugin and must not pay a per-session hook for it.

The kit is also a generator: `skill-creator/scripts/generate_supersede_kit.py` stamps the same conditional installer + routing hook (parameterized from `skill-creator/assets/supersede-kit/` templates) into any user skill that deliberately overlaps an installed plugin. skill-creator's own two scripts are regenerated from those templates — one source, no drift. Decision guide: `skill-creator/references/skill-precedence-and-coexistence.md`.

## Governance Principles

For source, installation, catalog-visibility or cache drift, enter
[skill-governance](skill-governance/SKILL.md) and follow its request router.
