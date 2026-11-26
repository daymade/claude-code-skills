---
name: skill-governance
description: >-
  Governs Claude Code/Codex/Antigravity Skill surfaces: reconciles source/install/catalog-visibility
  drift and adaptive hot/cold evolution without losing cold capability. Use when users ask how many
  Skills load, why catalogs truncate, want routers hot while bundles stay cold, or need
  duplicate/old-cache cleanup. Not for marketplace manifests (marketplace-dev) or repo audits
  (marketplace-health-check).
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
- `~/.agents/skills` as the shared user Skill root (Codex + Antigravity);
- `~/.config/skill-governance/hot-set.json` as the adaptive hot/cold SSOT projected to Antigravity (`~/.gemini/config/skills.json`), Codex (`~/.codex/config.toml`), and Claude Code (`~/.claude/settings.json`);
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
| Adaptive hot/cold Skill cache evolution & 3-host projection (Claude/Codex/Antigravity) | [`references/adaptive-hot-cold-evolution.md`](references/adaptive-hot-cold-evolution.md) + `scripts/evolve_skill_surface.py` |
| Explicit delivery contract; verify source owner, registration and installed route | §16, then requested fresh-host gate in §14 |
| What Codex really loads; count, truncation, duplicate identity, missing router | §3–4, then §11 |
| Reconcile owned source links or `~/.agents/skills` activation | §2–5, then §11 |
| Keep gstack/Lark/IMA/UiPath or another bundle cold behind a router | §2–4, §6, then §11 |
| Claude marketplace/plugin source or installed-state drift | §2–3, §7, then §11 |
| Old cache versions | §2 and §7 “Exceptional manual cache repair” |
| Standalone plugins superseded by a suite, or a renamed Skill with a compatibility-alias plugin (multi-host hook dedup) | §7–8, then §11 |
| Project `.claude/skills` vs `.agents/skills` drift | §9, then §11 |
| Retire loose or duplicate Skill directories | §2–3, §10–11 |
| Decide which Skills stay model-visible vs user-invocable-only | §15, then §11 |

## Fast read-only Codex audit

For a newly registered Skill whose local use is part of the delivery, run the
target-name checks in `references/skill-surface-governance.md` §14 before calling
it ready. This covers Claude's fresh command catalog and Codex's fresh prompt.
The name must come from the requested delivery, not only the active whitelist.

Invoke the script by its resolved Skill path and pass the consuming project as
`--cwd`:

```bash
python3 "<skill-governance-dir>/scripts/audit_codex_skill_surface.py" \
  --cwd "<target-workspace>" --json
```

Only add policy the user or activation SSOT actually declared:

```bash
python3 "<skill-governance-dir>/scripts/audit_codex_skill_surface.py" \
  --cwd "<target-workspace>" \
  --require-visible gstack-router \
  --json
```

The script compares `codex debug prompt-input` with the complete metadata parsed
by Codex's own app-server `skills/list`, plus exact activation/discovery policy.
Exit `0` is clean, `1` is pressure or drift to classify, and `2` means
the evidence is invalid. It is read-only. Do not convert exit `1` into automatic
pruning.

For delivery of named targets, follow the
[target-verdict procedure](references/skill-surface-governance.md#named-target-verdict).

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
- Do not install from a stale, feature-branch or WIP source checkout. Prefer the
  official GitHub Marketplace for durable use; verify its complete host-scoped
  distribution against the intended published ref. If an exact temporary source
  is required, restore the durable source through a controlled migration and
  repeat the same complete readback before reporting adoption. Determine the
  installed CLI's same-name source behavior before migrating: current Claude Code
  can replace a directory source in place, which preserves plugin state, whereas
  Marketplace removal can delete plugin options, secrets and data. Treat removal
  as a separately authorized destructive exception with complete state backup and
  restore; include install-ledger commit identity, declaration scopes and plugin
  state in the migration receipt, not only CLI list output.
- Read every candidate's unique instructions, scripts, references, and assets
  before calling it redundant. Old or short does not mean valueless.
- Decide model-visible vs user-invocable-only per Skill from usage evidence
  (§15), never from its description or install location alone.
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
When the requested outcome is published-content adoption into a live canonical
checkout with WIP, use the source owner's
[published-content adoption procedure](https://github.com/daymade/claude-code-skills/blob/a5dc7829ef3222e1234df08bbbc5de5cbccb48ad/daymade-claude-code/claude-switch-models-setup/references/local-source-sync-architecture.md#adopt-published-content-into-a-canonical-checkout-with-wip)
instead of switching branches, copying a cache, or applying an ordinary sync.

For Claude plugins, inspect current marketplace and install JSON, update or
reinstall through the official CLI at the original scope, and independently
read back the result. Treat cache folders as derived runtime artifacts.

For suite topology changes, use `marketplace-dev` to edit the source manifest;
use this Skill only to reconcile already-landed migrations on the current host.

## Read-only delivery contract audit

For an explicit delivery review, read §16 and run `scripts/audit_skill_delivery.py <skill-path> --delivery-contract <private-contract.json> --json`. It delegates source ownership to `skill-creator`; runtime visibility and original-requirement fidelity remain separate evidence. A source error blocks delivery even if the Skill can run.

## Definition of done

All applicable claims must be proven independently:

- canonical source and current owner are named;
- selected direct entries/routers appear in a fresh prompt under the requested
  discovery policy; report description truncation separately, including when
  the installation-only target gate passes;
- entries intended cold are absent from that catalog;
- one representative cold capability still resolves and works;
- source-backed links or Claude installs read back with the intended identity,
  source/version, scope, and complete host-scoped distribution against the published
  commit; use branch/HEAD as context, not as a substitute for consumed-path equality.
  Report stale/unknown on any difference or incomplete comparison rather than switching
  the target branch;
- any retired bundle and its recovery manifest still exist;
- unresolved ownership, host-version behavior, or deliberately retained
  exceptions are explicit.

Use the reference's task-behavior check only when actual task execution is part
of delivery; catalog visibility alone does not prove that result.

Stop there. Do not create a new hook, manifest, report layer, or cleanup project
unless the requested outcome still lacks evidence.
