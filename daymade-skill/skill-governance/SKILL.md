---
name: skill-governance
description: >-
  Govern the real Claude Code and Codex Skill surface without losing cold
  capability. Use when users ask how many Skills are loaded, why the catalog is
  huge or descriptions are truncated, want only routers visible while
  gstack/Lark/IMA/UiPath stay on disk, or need to reconcile
  source/install/cache drift, `.agents/skills`/`.claude/skills`/legacy
  `.codex/skills`, loose or duplicate Skills, discovery policy, marketplace
  sources, suite migrations, superseded plugins, or old cache versions. Verifies
  the fresh host catalog and router resources; filesystem counts or completed
  cleanup are not success.
---

# Skill Governance

Govern the Skill surface the user actually experiences: the intended hot or
router entries are fully visible in a fresh host, cold capabilities remain
reachable, editable behavior has one canonical owner, and every retirement is
recoverable. A smaller directory count is not the outcome.

## Required outcome contract

Before acting, state in one sentence:

- which entries or routers must be model-visible;
- which capabilities must remain available cold;
- which layer the user authorized changing;
- what fresh-host evidence will prove success.

If the request is only “how many / what is loaded / why”, stay read-only.

## System model

Never collapse these layers into one:

1. **Canonical source** — where owned behavior may be edited.
2. **Installed inventory** — bundles and versions that exist on disk.
3. **Discovery policy** — what Claude or Codex may discover.
4. **Model-visible catalog** — metadata in a fresh model prompt.
5. **Runtime resources** — hidden scripts, references, and assets a router still
   needs.

Installed does not mean active; active does not prove visible; visible does not
prove usable. Counts and byte totals are diagnostic values only.

## Authority order

Use current runtime truth, not remembered conventions:

- owned source repos and their manifests for editable Skill behavior;
- `claude plugin ... --json` for current Claude marketplace/install state;
- the explicit source-sync activation manifest for managed Daymade links;
- `~/.agents/skills` as Codex's current user Skill root;
- exact-path `~/.codex/config.toml` policy for Codex discovery disables;
- `codex debug prompt-input` for the actual fresh Codex catalog;
- the installed vendor bundle for third-party cold resources.

`~/.codex/skills` is legacy/system compatibility unless a current local contract
explicitly assigns it another role. Never move third-party inventory into an
owned-source activation manifest just to make ownership look complete.

## Route the request

Read the named section of
[`references/skill-surface-governance.md`](references/skill-surface-governance.md)
completely before using that workflow.

| Request | Read and use |
|---|---|
| What Codex really loads; count, truncation, duplicate identity, missing router | §3–4, then §11 |
| Reconcile owned source links or `~/.agents/skills` activation | §2–5, then §11 |
| Keep gstack/Lark/IMA/UiPath or another bundle cold behind a router | §2–4, §6, then §11 |
| Claude marketplace/plugin source or installed-state drift | §2–3, §7, then §11 |
| Old cache versions | §2 and §7 “Exceptional manual cache repair” |
| Standalone plugins superseded by a suite | §7–8, then §11 |
| Project `.claude/skills` vs `.agents/skills` drift | §9, then §11 |
| Retire loose or duplicate Skill directories | §2–3, §10–11 |

## Fast read-only Codex audit

Run from this Skill bundle:

```bash
python3 scripts/audit_codex_skill_surface.py --json
```

Only add policy the user or activation SSOT actually declared:

```bash
python3 scripts/audit_codex_skill_surface.py \
  --require-visible gstack-router \
  --json
```

The script compares `codex debug prompt-input` with the complete metadata parsed
by Codex's own app-server `skills/list`, plus exact activation/discovery policy.
Exit `0` is clean, `1` is pressure or drift requiring a decision, and `2` means
the evidence is invalid. It is read-only. Do not convert exit `1` into automatic
pruning.

For a project's dual roots:

```bash
python3 scripts/audit_project_skill_roots.py <project-root> --json
```

That audit pairs direct child bundles by frontmatter `name`, recognizes only its
explicit fail-visible compatibility-router contract, and distinguishes shared
targets, identical copies, real drift, and invalid state.

## Non-negotiable safety boundaries

- Drift checks are read-only. Config edits, link sync, installs, uninstalls,
  moves, cache repair, and marketplace source changes require authorization.
- Preserve Claude plugin scope. Verify replacements before retiring old
  identities.
- Never use direct cache copying as installation or source sync.
- Do not enforce “one cache version”. Current Claude Code owns orphan-version
  grace for running sessions; manual cache removal is exceptional repair only.
- Do not use blind marketplace remove-then-add. Removing the last scoped
  marketplace can uninstall its plugins.
- Read every candidate's unique instructions, scripts, references, and assets
  before calling it redundant. Old or short does not mean valueless.
- Keep cold third-party resources installed; hide only their exact discovery
  paths, then prove the router still resolves one representative capability.
- Retire by recoverable move plus file/executable/hash manifest, never by
  `rm -rf`.
- Existing sessions retain startup metadata. Restart before treating the
  interactive catalog as verification.

## Source and activation ownership

For Daymade source-backed Codex activation, route to the current
`claude-switch-models-setup` dry-run/apply workflow. Its explicit
`codex-active-skills.json` owns only links created from declared source
marketplaces. Do not reimplement its collision, symlink, or pruning logic here.

For Claude plugins, inspect current marketplace and install JSON, update or
reinstall through the official CLI at the original scope, and independently
read back the result. Treat cache folders as derived runtime artifacts.

For suite topology changes, use `marketplace-dev` to edit the source manifest;
use this Skill only to reconcile already-landed migrations on the current host.

## Definition of done

All applicable claims must be proven independently:

- canonical source and current owner are named;
- selected direct entries/routers appear in a fresh prompt with intact
  descriptions;
- entries intended cold are absent from that catalog;
- one representative cold capability still resolves and works;
- source-backed links or Claude installs read back with the intended identity,
  source/version, and scope;
- any retired bundle and its recovery manifest still exist;
- unresolved ownership, host-version behavior, or deliberately retained
  exceptions are explicit.

Stop there. Do not create a new hook, manifest, report layer, or cleanup project
unless the requested outcome still lacks evidence.
