# daymade-skill Suite

This directory bundles skills related to Claude Code skill development, quality, and governance.

## Included Skills

- `skill-creator` — Create and improve skills.
- `skill-reviewer` — Review skill quality and trigger accuracy.
- `skills-search` — Search across the skill marketplace.
- `skill-governance` — Govern the real Claude/Codex Skill surface while preserving cold capabilities.

## Supersede Hook (on-demand, never static)

When the official `skill-creator@claude-plugins-official` plugin is installed alongside this suite, the two skill-creator entries carry near-identical descriptions and Claude picks between them at random. The resolution lives in `skill-creator/scripts/`:

- `setup_supersede_hook.sh {install|uninstall|status}` — consent-based installer invoked from the skill-creator coexistence check. `install` refuses to do anything on machines where the official plugin is absent (zero footprint); otherwise it copies the routing hook into the user's Claude config and registers one `SessionStart` entry in `settings.json` (backed up, idempotent, reversible).
- `supersede-routing-hook.sh` — the routing hook source. The installer copies it as `skill-creator-supersede-hook.sh` in the user's Claude config. It self-checks its preconditions every session and goes silent if either the official plugin or the daymade skill-creator disappears, so stale installs are safe by construction. Non-destructive: the official plugin stays usable when the user asks for it by name.

The suite deliberately ships no static `hooks/hooks.json` — most installs never coexist with the official plugin and must not pay a per-session hook for it.

The kit is also a generator: `skill-creator/scripts/generate_supersede_kit.py` stamps the same conditional installer + routing hook (parameterized from `skill-creator/assets/supersede-kit/` templates) into any user skill that deliberately overlaps an installed plugin. skill-creator's own two scripts are regenerated from those templates — one source, no drift. Decision guide: `skill-creator/references/skill-precedence-and-coexistence.md`.

## Governance Principles

`skill-governance` separates five layers: canonical source, installed inventory,
discovery policy, the model-visible catalog, and runtime resources retained behind
a router. Filesystem counts and cache tidiness do not prove that the intended
capability is visible or usable.

- Treat owned source as canonical and plugin caches as derived runtime state.
- Use current official plugin commands and preserve install scope.
- Use the explicit source activation manifest only for links its syncer owns;
  third-party cold inventory stays outside that manifest.
- Verify Codex with a fresh prompt audit and separately probe any hidden resource
  a router must still reach.
- Do not normalize Claude's cache to one version; current orphan-version cleanup
  belongs to Claude's lifecycle. Manual cache removal is exceptional repair.
- Audits are read-only. Config, install, uninstall, move, or source changes need
  explicit authorization and independent readback.

For workflow routing and detailed procedures, invoke
`daymade-skill:skill-governance`.
