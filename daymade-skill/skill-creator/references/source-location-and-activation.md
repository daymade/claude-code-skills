---
name: source-location-and-activation
description: >-
  Establish canonical source ownership before writing and verify registration, installation
  identity and actual consumption at delivery. Read before source checks and availability claims.
---

# Source location and activation

Read this source-owner procedure before the first write; read its delivery checks
when installation or local availability is in scope. Source-only requests retain
their authorized boundary. Name the current linked worktree root in `--repo`;
the Git common directory establishes its registered identity.

**NEVER edit installed skill copies first.** Treat all of these as installed/runtime copies unless the user explicitly says they are the source:
- `~/.codex/skills/<skill-name>`
- `~/.claude/skills/<skill-name>`
- `~/.agents/skills/<skill-name>`
- `~/.claude/plugins/cache/...`
- `~/.codex/plugins/cache/...`

Editing installed copies first causes changes to be:
- Lost when cache refreshes
- Not synced to source control
- Wasted effort requiring manual re-merge

**ALWAYS verify you're editing the source repository:**
```bash
# WRONG - cache location (read-only copy)
~/.claude/plugins/cache/daymade-skills/my-skill/1.0.0/my-skill/SKILL.md

# WRONG - personal installed copy unless explicitly used as source
~/.codex/skills/my-skill/SKILL.md

# RIGHT - source repository
<repo-root>/my-skill/SKILL.md
```

**Before any creation or edit**, run the source-owner check and say which path is source. This is separate from the private review archive and the runtime installation path:

```bash
uv run --project <skill-creator-dir> --frozen python <skill-creator-dir>/scripts/source_contract.py check-path <skill-dir> \
  --phase create --repo <source-repo> --scope marketplace
```

Stop on `invalid` or `unknown` before writing. An explicit `--repo` cannot override an existing source owner; for exported owner evidence, pass `--inventory <frozen-owner-inventory.json>`. New marketplace members must be registered before delivery; a permitted draft location is not a completed install.

For managed local sources, omit `--repo` only when the source-sync owner's inventory can establish the repository identity. An unavailable inventory is `unknown`, not permission to guess. Inventory source paths must be qualified absolute paths; missing, null or blank paths cannot borrow the caller's current directory. Linked worktrees are checked by their Git common directory. Project-local Skills use `--scope project`; reviewing or installing third-party packages does not make their cache an authored source.

At delivery, run the read-only check against the requested Skill name and declared source owner, not merely whatever happens to appear in a catalog:

```bash
uv run --project <skill-creator-dir> --frozen python <skill-creator-dir>/scripts/source_contract.py audit <skill-dir> \
  --repo <source-repo> --scope marketplace --install-path <installed-skill-entry>
```

This checks source containment, exact registration and source-backed installation identity. It never proves a current session loaded the Skill. Pass the original user outcome and separate source/install paths to `skill-reviewer`'s delivery contract; a runnable Skill, green tests and catalog visibility cannot substitute for ownership validation. Keep the contract private when it contains local paths. Missing runtime observations remain `unknown`.

If the available-skills list points at `~/.codex/skills`, `~/.claude/skills`, or a plugin cache, do not assume that path is source. Locate the repository-backed source first, edit it, validate it, and only then sync the installed copy when the user needs immediate local runtime use.

**Verify the actual consumed file before claiming availability.** A marketplace's registered source path does not identify its installed cache or prove session loading. Resolve the installed entry, read the content at that resolved location, and run the applicable fresh-host check. For source-backed aliases and ordinary versioned plugin copies, follow the installation and verification procedures in skill-governance’s skill-surface-governance reference. Source ownership, installation identity and current session evidence are separate checks.
