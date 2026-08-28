# Skill Surface Governance Reference

This reference contains the detailed operating procedures for `skill-governance`.
The main Skill is the router. Read only the sections required by the selected
workflow.

## Contents

- [1. The governed system](#1-the-governed-system)
- [2. Authority and mutation boundaries](#2-authority-and-mutation-boundaries)
- [3. Establish a bounded baseline](#3-establish-a-bounded-baseline)
- [4. Audit the real Codex Skill surface](#4-audit-the-real-codex-skill-surface)
- [5. Reconcile source-backed activation](#5-reconcile-source-backed-activation)
- [6. Keep cold bundles without loading their catalog entries](#6-keep-cold-bundles-without-loading-their-catalog-entries)
- [7. Audit and repair Claude plugin installs](#7-audit-and-repair-claude-plugin-installs)
- [8. Reconcile a suite migration](#8-reconcile-a-suite-migration)
- [9. Audit project dual roots](#9-audit-project-dual-roots)
- [10. Retire a loose or duplicate Skill without losing value](#10-retire-a-loose-or-duplicate-skill-without-losing-value)
- [11. Verify the user-visible outcome](#11-verify-the-user-visible-outcome)
- [12. Report format](#12-report-format)
- [13. Troubleshooting](#13-troubleshooting)

## 1. The governed system

Treat these as different layers. A smaller number at one layer is not evidence
that the user's capability surface improved.

| Layer | Question | Typical authority |
|---|---|---|
| Canonical source | Where may the Skill's behavior be edited? | Owned source repo, or the vendor's installed package when no editable source is owned locally |
| Installed inventory | What bundles and versions exist on disk? | Claude plugin metadata/cache, package manager state, or an explicitly managed source inventory |
| Discovery policy | Which installed entries may a host discover? | Claude plugin scope/enabled state; Codex Skill roots and exact-path `skills.config` entries |
| Model-visible catalog | What metadata did a fresh model prompt actually receive? | Fresh-host prompt inspection, never a filesystem count |
| Runtime resources | Which hidden scripts, references, or assets remain reachable? | The selected router's real resolution path and read/run verification |

Four distinctions prevent most governance mistakes:

1. **Installed is not active.** A bundle may stay on disk while its individual
   entries are hidden behind a router.
2. **Active is not visible.** Config drift or catalog pressure can prevent an
   intended entry from reaching the model.
3. **Visible is not usable.** A router that cannot resolve its cold references
   has made the prompt smaller by deleting capability.
4. **Counts are diagnostics.** The desired result is the intended hot/router
   surface plus reachable cold capability, not the lowest possible count.

## 2. Authority and mutation boundaries

Before changing anything, identify the owner of each layer:

- **Owned Daymade source and activation:** use the current
  `claude-switch-models-setup` source-sync architecture and its explicit
  `codex-active-skills.json`. That manifest owns only source-backed links that
  its syncer manages; it does not own third-party bundles.
- **Claude marketplace/plugin state:** use current `claude plugin marketplace`
  and `claude plugin` commands plus their JSON output. Plugin caches are derived
  runtime state, not a second source repo.
- **Codex user activation:** the current official user root is
  `~/.agents/skills`. `~/.codex/skills` is legacy/system compatibility only
  unless a current local contract explicitly says otherwise.
- **Project Skills:** inspect only the current project's declared
  `.agents/skills` and `.claude/skills` roots.
- **Third-party cold inventory:** the installed bundle remains its own disk
  authority. Exact-path Codex disables control discovery; they do not transfer
  ownership into the source activation manifest.

Mutation rules:

- Audits are read-only.
- Sync, install, uninstall, move, cache repair, config edit, or marketplace
  source change requires an explicit user request covering that action.
- Preserve plugin scope (`user`, `project`, or other current supported scope).
- Never copy an installed/cache tree back over canonical source.
- Never infer that a short, old, duplicated, or hidden Skill has no value. Read
  its scripts, references, assets, and unique behavior first.
- Prefer reversible moves with a manifest over deletion.
- Do not hand-edit Claude plugin cache content as a sync mechanism.
- Do not normalize Claude's cache to one version. Current Claude Code keeps
  versioned entries during its orphan grace period so running sessions can
  finish; official lifecycle cleanup owns that state.

## 3. Establish a bounded baseline

Inspect only the layer implicated by the request. Do not scan unrelated repos.

```bash
codex --version
claude --version
claude plugin marketplace list --json
claude plugin list --json
git -C <canonical-source> status -sb
```

For Codex source-backed activation, inspect the explicit manifest and direct
links rather than counting all directories recursively:

```bash
jq . ~/.config/claude-switch-models-setup/codex-active-skills.json
find ~/.agents/skills -mindepth 1 -maxdepth 1 -type l -print
```

Record:

- requested user-visible entries or routers;
- capabilities that must remain available cold;
- canonical source(s);
- current scope or activation owner;
- exact authorized mutation;
- recovery path and stop condition.

## 4. Audit the real Codex Skill surface

Run from this Skill bundle. The audit is read-only and uses
`codex debug prompt-input` by default:

```bash
python3 scripts/audit_codex_skill_surface.py --json
```

Add explicit policy only when the user or current activation SSOT defines it:

```bash
python3 scripts/audit_codex_skill_surface.py \
  --require-visible gstack-router \
  --require-visible lark-cli-router \
  --json
```

`--max-visible N` is an optional user policy ceiling, not a built-in quality
score. Use `--prompt-json FILE` for a frozen test fixture.

The audit asks Codex's own app-server `skills/list` endpoint for the complete,
unshortened metadata parsed from disk, then matches each prompt locator to that
inventory by canonical target while retaining its lexical discovery path for
exact-path policy. It fails invalid if Codex reports any Skill scan error; it
does not maintain a second partial YAML parser. It reports:

- source descriptions that were shortened in the actual prompt;
- descriptions that differ without being a prefix truncation;
- duplicate display identities or distinct sources with the same frontmatter
  name;
- two visible discovery aliases that resolve to the same canonical Skill;
- exact disabled discovery paths that still appear;
- stale disabled paths;
- enabled inventory entries omitted from the initial prompt catalog;
- source-activation names whose direct `~/.agents/skills/<name>/SKILL.md`
  entry is missing or not model-visible;
- required routers that are absent;
- an optional visible-count ceiling breach.

Exit status is `0` for clean, `1` for policy pressure/drift, and `2` when the
evidence is invalid. A `1` is not permission to prune; classify each finding and
choose the layer that owns the fix.

Existing sessions retain their startup catalog. Restart Codex and rerun the
audit before claiming that discovery-policy changes took effect.

## 5. Reconcile source-backed activation

Use this workflow for owned source repos managed by
`claude-switch-models-setup`.

1. Read its current source-sync architecture reference and activation manifest.
2. Run its syncer in dry-run mode first. Do not recreate its link logic inside
   this Skill.
3. Reject duplicate frontmatter identities, unknown manifest names, real-path
   collisions, and third-party links before mutation.
4. Apply only after the requested active set is explicit.
5. Read back every selected `~/.agents/skills/<name>` link and verify it resolves
   into the declared canonical source.
6. Run the real Codex surface audit. A correct symlink set with a wrong prompt
   catalog is not complete.

The activation manifest is a selection policy, not an inventory dump. Do not
put every source Skill into it, and do not add third-party cold bundles merely
to explain why they exist on disk.

## 6. Keep cold bundles without loading their catalog entries

Use when a bundle's references, scripts, or assets must remain installed while
one router or umbrella Skill should be the model-visible entry.

1. Identify every independently discovered `SKILL.md` in the bounded bundle.
2. Prove which disk resources the router still needs. Record their paths and, for
   generated/vendor mirrors, the appropriate version or digest check.
3. Keep the bundle installed. Do not add it to an owned-source activation
   manifest and do not move it to retirement.
4. Add one exact discovery-path entry for every cold catalog entry to
   `~/.codex/config.toml`:

   ```toml
   [[skills.config]]
   path = "/absolute/discovery/path/to/SKILL.md"
   enabled = false
   ```

   The path is the discovery path to hide, not necessarily the resolved source
   target. This permits a separately exposed hot symlink to share the same
   source without being disabled accidentally.
5. Do not disable the chosen router.
6. Restart Codex and run the real surface audit with
   `--require-visible <router>`.
7. Exercise one representative cold-resource resolution through the router.

Success requires both: cold entries absent from the model catalog, and the
router still able to reach the retained capability.

## 7. Audit and repair Claude plugin installs

### Read-only audit

1. Resolve the current marketplace source with:

   ```bash
   claude plugin marketplace list --json
   ```

2. Resolve installed plugin identity, version, enabled state, and scope with:

   ```bash
   claude plugin list --json
   ```

3. Read the source `marketplace.json`. A top-level plugin with a non-empty
   `skills` array is a suite; compare/install the suite once rather than treating
   its member paths as standalone plugins.
4. Compare canonical source with the installed version while ignoring runtime
   artifacts such as `.git`, `.in_use`, `.security-scan-passed`,
   `.skill-regression-reviewed`, `.orphaned_at`, `.DS_Store`, `__pycache__`,
   `.pytest_cache`, `.venv`, `node_modules`, `*.pyc`, and `*.pyo`.
5. Report source drift, version mismatch, missing install, installed identity no
   longer present in the source manifest, and scope mismatch separately.

Discover suites dynamically:

```bash
jq -r '.plugins[] | select(((.skills // []) | length) > 0) | .name' \
  .claude-plugin/marketplace.json
```

### Supported repair

1. Update marketplace metadata through the official CLI.
2. Reinstall or update only the affected plugin at its original scope, using the
   commands supported by the current installed Claude version.
3. Verify the installed version and member `SKILL.md` files through independent
   readback.
4. Leave older versioned cache entries to Claude's orphan lifecycle.

### Exceptional manual cache repair

Manual cache removal is not normal governance. Consider it only when current
official loading is demonstrably broken and reinstall/update cannot repair it.
Before any removal:

- identify the exact plugin/version directory;
- prove no required source or unique loose content lives only there;
- account for running sessions that may still reference it;
- create a recoverable copy or move;
- obtain explicit deletion/move authorization;
- repair through the official install path and verify a fresh host.

Never delete every version except the numerically latest as routine hygiene.

### Marketplace source changes

Do not blindly run remove-then-add. Removing a marketplace from its last scope
can uninstall its plugins. For Daymade maintainer local-source switching, route
to the current `claude-switch-models-setup` workflow. For any other marketplace:

1. inventory installed plugins and scopes;
2. freeze the intended replacement source identity;
3. define how installs survive or are restored;
4. perform the source change with current official commands;
5. verify marketplace source, plugin installs, scopes, and a fresh session.

## 8. Reconcile a suite migration

Use only after the canonical marketplace migration has landed. Source topology
design belongs to `marketplace-dev`.

1. Require an explicit mapping from superseded standalone plugin names to the
   replacement suite and invocation names. Do not infer it from basenames.
2. Verify the current source manifest contains the suite, its non-empty `skills`
   array, and every expected member path.
3. Group superseded installs by their existing scope.
4. Update marketplace metadata and install the replacement suite once at each
   required scope.
5. Before uninstalling anything, independently verify:
   - the suite is enabled at that scope;
   - its installed version matches the source manifest;
   - every expected member `SKILL.md` exists;
   - the new namespaced invocation matches the member frontmatter name.
6. Uninstall each superseded standalone identity only after its replacement
   passes all checks.
7. Read back plugin state and, where relevant, the fresh model catalog.

## 9. Audit project dual roots

When the current project exposes both `.claude/skills` and `.agents/skills`, run:

```bash
python3 scripts/audit_project_skill_roots.py <project-root> --json
```

The script pairs direct child bundles by frontmatter `name` and returns:

- `canonical_router`: one full canonical bundle plus the exact fail-visible
  compatibility-router contract;
- `shared_target`: both roots resolve to the same canonical bundle;
- `identical_copy`: currently equal but still duplication debt;
- `drift`: divergent full bundles without a valid router;
- `single_root`: one declared root owns the name;
- `invalid`: malformed identity, broken symlink/router, or unauditable root.

Do not infer a router from short length or router-like prose. The accepted router
marker and pointer contract are enforced by the script. Choosing the canonical
owner and replacing a copy remains a repository-owner decision.

## 10. Retire a loose or duplicate Skill without losing value

Bound the scan to direct entries in the implicated roots. For a user-surface
request, check the requested subset of `~/.agents/skills`, `~/.claude/skills`,
and legacy `~/.codex/skills`; when the user asks to unify or clean the whole user
surface, all three are implicated. Before classification, read each root's
current package-manager ownership record, including the adjacent
`.skill-lock.json` when present, current Claude plugin metadata, and any explicit
source activation manifest. An unreadable or unfamiliar lock schema is
`Unknown`, not permission to move its entries. Then classify each candidate:

- **Managed source link:** owned by a current activation manifest; reconcile via
  its syncer.
- **Lock-managed direct Skill:** present in the current `.skill-lock.json`; use
  that manager's uninstall/update workflow and do not move the directory.
- **Plugin-managed:** owned by installed plugin metadata; use official plugin
  operations.
- **Third-party cold inventory:** kept on disk and hidden through discovery
  policy; do not retire it.
- **Source-backed duplicate:** behavior matches a canonical source; replace with
  the canonical link/install only after readback.
- **Loose but valuable:** unique methodology, scripts, references, assets,
  credential flow, or domain knowledge; migrate it to a source owner before
  removing the active copy.
- **Superseded or valueless duplicate:** no unique capability remains and a
  verified replacement exists; eligible for reversible retirement.
- **Unknown:** ownership or unique value is unresolved; keep it active or cold
  and report the blocker.

For a retire candidate:

1. Re-read lock, plugin, and activation ownership immediately before mutation.
   Any ownership match or unresolved schema aborts the move.
2. Capture path, frontmatter identity, file list, executable bits, and hashes.
3. Record the verified replacement or the evidence that no unique capability
   exists.
4. Move the complete bundle to a dated `retired-skills/<reason>-<date>/`
   location under the same owning profile or another user-approved recoverable
   destination. Do not use `rm -rf`.
5. Verify the replacement first, then verify the retired copy and its manifest.
6. Restart the affected host and inspect its actual catalog.

Do not keep a misleading retired rules snapshot in the active tree merely for
history. Git history or the retirement artifact is the historical record.

## 11. Verify the user-visible outcome

Verification follows the changed layer:

1. **Source:** diff and focused tests prove the intended behavior remains.
2. **Installed state:** official list JSON plus filesystem readback proves
   identity, version, scope, and member files.
3. **Discovery:** config/link readback proves the selected paths and policy.
4. **Catalog:** a fresh prompt audit proves the model-visible entries and full
   descriptions.
5. **Cold capability:** one representative router action proves hidden resources
   remain reachable.
6. **Recovery:** any retired/moved material and its hashes remain present.

Stop when the requested surface and retained capabilities are proven. Do not add
another governance layer merely because one more metric could be produced.

## 12. Report format

Report decisions rather than dumping every directory:

```markdown
# Skill Governance Result

## Requested outcome
- Intended visible entries/routers: ...
- Capabilities retained cold: ...

## Authority used
- Canonical source: ...
- Activation/discovery SSOT: ...
- Installed-state authority: ...

## Findings
| Layer | Finding | Evidence | Decision |
|---|---|---|---|

## Changes made
- ...

## Independent readback
- Fresh catalog: ...
- Cold capability probe: ...
- Recovery path: ...

## Remaining unknowns or exceptions
- ...
```

Do not persist derived totals as governance truth. Compute them from the current
audit when the user asks.

## 13. Troubleshooting

- **Filesystem count differs from the prompt:** expected; inspect the discovery
  policy and fresh prompt. Disk inventory is not the catalog.
- **A source description is truncated:** reduce catalog pressure by selecting
  hot/router entries, not by shortening every description until trigger quality
  collapses.
- **The prompt and `skills/list` disagree:** treat the audit as invalid or
  pressure according to the reported field. Do not fall back to a hand-written
  YAML approximation.
- **A disabled source still appears through a hot alias:** exact-path policy is
  lexical. Disable the discovery path to hide, not every symlink resolving to
  the same source.
- **A router remains but its child action fails:** the cold bundle or version
  parity was lost. Restore the resource before calling consolidation complete.
- **Old Claude cache versions remain:** this can be normal orphan grace for
  running sessions. Do not clean them solely to make a count reach one.
- **Marketplace remove would affect installs:** stop and design a scope-preserving
  migration; do not rely on remove-then-add.
- **A duplicate is byte-identical:** it is duplication debt, not evidence that
  either copy can be deleted without identifying the owner and replacement.
- **Current session still shows retired entries:** restart; startup metadata is
  not retroactively rewritten.
