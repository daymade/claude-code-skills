# Suite Consolidation Workflow

Consolidate existing standalone skills into a new or existing suite without changing
their runtime behavior, leaving duplicate registrations, or stranding installed users.

## Contents

- [When to use](#when-to-use)
- [Success contract](#success-contract)
- [1. Freeze the mapping and authority](#1-freeze-the-mapping-and-authority)
- [2. Capture an immutable baseline](#2-capture-an-immutable-baseline)
- [3. Move the canonical bundles](#3-move-the-canonical-bundles)
- [4. Update the marketplace manifest](#4-update-the-marketplace-manifest)
- [5. Close every drift surface](#5-close-every-drift-surface)
- [6. Publish an installed-user migration](#6-publish-an-installed-user-migration)
- [7. Validate the source and real installation](#7-validate-the-source-and-real-installation)
- [8. Freeze, review, and ship](#8-freeze-review-and-ship)
- [Failure signals](#failure-signals)
- [Delivery report](#delivery-report)

## When to use

Use this workflow when the user asks to:

- put several existing skills into one suite;
- move one existing skill into an established suite;
- convert standalone plugins to suite-only distribution;
- rename a skill directory while aligning it with the `name` in `SKILL.md`;
- split or merge plugin boundaries while preserving each skill bundle.

Do not use it to merely refresh installed caches. Use
`daymade-skill:skill-governance` after the source migration has merged and the user
has asked to reconcile the current machine's installed state.

## Success contract

Declare these falsifiable outcomes before editing:

1. Every requested skill has exactly one canonical source directory under its target
   suite.
2. Every moved bundle preserves its relative file set, bytes, and executable modes
   unless the user separately approved a content change.
3. Every target suite is a top-level marketplace plugin with an explicit `skills`
   array relative to its own `source`.
4. No moved member remains registered as a standalone plugin when the requested model
   is suite-only.
5. Public install commands name the suite plugin; invocation examples use
   `<suite>:<frontmatter-name>`.
6. Existing users receive an executable migration path before old standalone entries
   disappear.
7. Validation exercises the real installed cache, not only manifest syntax.

## 1. Freeze the mapping and authority

Read the repository's manifest, project instructions, README install sections,
changelog policy, and the affected `SKILL.md` frontmatter. Record one mapping row per
skill before touching files:

| Old plugin | Old source | Frontmatter name | Target suite | Final source | Distribution |
|---|---|---|---|---|---|
| `<old-plugin>` | `<old-dir>` | `<skill-name>` | `<suite>` | `<suite>/<skill-name>` | `suite-only` |

Resolve these decisions explicitly:

- Create a new suite or extend an existing one.
- Preserve the current skill name or rename it. When directory and frontmatter names
  differ, prefer aligning them only when the user approved the rename; do not invent a
  compatibility alias.
- Preserve standalone installation or remove it. Treat a suite-only request as
  approval to remove the standalone marketplace entry, not as approval to change the
  skill's runtime instructions.
- Identify user-mutable state. Verify that persistent data lives outside the install
  bundle before claiming the move is data-safe.

Fail fast when any row is ambiguous. Do not infer a target suite from similar names or
from the skill's current directory.

## 2. Capture an immutable baseline

Create a feature branch and record the literal pre-edit commit SHA. Verify the affected
paths have no tracked working-tree changes. Preserve each complete old bundle from that
Git ref, including references, scripts, assets, agents, tests, evals, and executable
modes.

When `daymade-skill:skill-creator` is available, use its existing-skill migration gate
and declare each directory move with `--renamed-from`. Otherwise compare old and new
trees independently with `git ls-tree -r` and require identical relative paths, blob
IDs, and modes.

Classify the work accurately:

- Treat the bundle move itself as behavior-preserving relocation.
- Treat plugin namespace removal and install-command changes as a breaking distribution
  boundary.
- Separate any factual correction or skill-content edit from the move and validate it
  under its own evidence.

## 3. Move the canonical bundles

Create a real target suite directory when needed, then move each tracked directory with
`git mv`. Keep one physical canonical copy.

Do not:

- build a suite from symlinks;
- copy the skill and leave the old directory active;
- preserve an obsolete directory name merely to avoid updating documentation;
- stage unrelated paths from a shared checkout.

After moving, verify each final directory contains `SKILL.md` and that its frontmatter
name matches the intended invocation name.

## 4. Update the marketplace manifest

Edit entries by plugin name; never round-trip the whole JSON file through a formatter.

For a new suite:

- add one top-level plugin entry with `source: "./<suite>"`;
- set `strict: false` when the source has no `plugin.json`;
- set its first plugin version according to repository policy, commonly `1.0.0`;
- list each member path relative to the suite source.

For an existing suite:

- append the member path once;
- bump the suite version according to repository semver policy;
- update the suite description and keywords only when the user-facing scope changed.

For suite-only consolidation:

- remove each superseded standalone plugin entry;
- update the marketplace catalog version only when repository policy requires it;
- preserve unrelated plugin entries byte-for-byte.

Assert mechanically that the target suite contains the exact intended member set and
that every superseded standalone name is absent.

## 5. Close every drift surface

Search the whole repository for every old plugin name, old source path, standalone
install command, and invocation namespace. Include repository docs and files inside
other skills:

```bash
rg -n --fixed-strings \
  -e '<old-plugin>' -e '<old-source>' -e '<old-plugin>@<marketplace>' \
  -e '<old-plugin>:<skill-name>' <repo-root> \
  --glob '!.git/**' --glob '!**/*-workspace/**'
```

Inspect and update only directly affected surfaces:

- README and translated README install sections;
- each moved skill's detailed section and documentation links;
- repository instruction files and human-readable skill inventories;
- changelog and migration notes;
- tests, CI registries, health-check prompts, architecture references, and path-based
  scripts;
- any other skill that persists a manual suite inventory.

Replace manual suite inventories with manifest-driven discovery instead of appending
new names. A list that can be derived from `plugins[].skills` is guaranteed to drift
again.

Keep historical examples historical: label obsolete standalone commands as historical
and place the current command beside them instead of rewriting the event that happened.

## 6. Publish an installed-user migration

Document the sequence for existing users:

1. update the marketplace;
2. install the target suite at the existing scope;
3. verify the new `<suite>:<skill>` invocation and cache contents;
4. uninstall the superseded standalone plugin record only after the replacement works;
5. update scripts or docs that invoke the old namespace.

Do not claim that removing a marketplace entry cleans local installs. Treat installed
plugin metadata and caches as separate derived state. Route machine-level reconciliation
to `daymade-skill:skill-governance` after merge.

## 7. Validate the source and real installation

Run the smallest independent checks that cover every changed contract:

1. Validate every moved skill with the active Skill Creator validator.
2. Complete the old-vs-new bundle audit from the immutable baseline.
3. Run `check_marketplace.sh` for JSON, Claude validation, path resolution, and reverse
   sync.
4. Run the repository's README/manifest drift checker.
5. Run affected tests and syntax checks whose paths changed.
6. Search again for unlabelled standalone install commands and obsolete source paths.
7. Use an isolated Claude config directory to add the local marketplace, install and
   update each affected suite, and inspect the resulting cache top level.
8. Confirm the cache contains only tracked suite members and legitimate suite-scoped
   resources. Distinguish ignored local workspace directories from content that a Git
   install would actually ship.

Use a clean archive of the immutable commit, not a dirty working tree, so ignored local
workspace directories cannot contaminate the cache result. Replace the four placeholders
below, then run the block as one test. Every `claude` command in this test must carry the
same `CLAUDE_CONFIG_DIR` prefix. If any command omits it, stop: isolation from the user's
active plugin registry has not been established.

```bash
set -eu
SUITE_TEST_SOURCE="<absolute-path-to-source-repo>"
SUITE_TEST_REF="<immutable-commit-sha>"
SUITE_TEST_MARKETPLACE="<marketplace-name>"
SUITE_TEST_PLUGIN="<suite-plugin-name>"
SUITE_TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/tinkle_suite-install.XXXXXX")"

mkdir "$SUITE_TEST_ROOT/tinkle_repo" "$SUITE_TEST_ROOT/tinkle_config"
git -C "$SUITE_TEST_SOURCE" archive --format=tar \
  --output "$SUITE_TEST_ROOT/tinkle_repo.tar" "$SUITE_TEST_REF"
tar -xf "$SUITE_TEST_ROOT/tinkle_repo.tar" -C "$SUITE_TEST_ROOT/tinkle_repo"

CLAUDE_CONFIG_DIR="$SUITE_TEST_ROOT/tinkle_config" \
  claude plugin marketplace add "$SUITE_TEST_ROOT/tinkle_repo"
CLAUDE_CONFIG_DIR="$SUITE_TEST_ROOT/tinkle_config" \
  claude plugin install "$SUITE_TEST_PLUGIN@$SUITE_TEST_MARKETPLACE" --scope user
CLAUDE_CONFIG_DIR="$SUITE_TEST_ROOT/tinkle_config" \
  claude plugin update "$SUITE_TEST_PLUGIN@$SUITE_TEST_MARKETPLACE"
CLAUDE_CONFIG_DIR="$SUITE_TEST_ROOT/tinkle_config" claude plugin list

SUITE_TEST_INSTALL_PATH="$(jq -er \
  --arg id "$SUITE_TEST_PLUGIN@$SUITE_TEST_MARKETPLACE" \
  '.plugins[$id][0].installPath' \
  "$SUITE_TEST_ROOT/tinkle_config/plugins/installed_plugins.json")"
find "$SUITE_TEST_INSTALL_PATH" -mindepth 1 -maxdepth 2 -name SKILL.md -print
```

Compare the installed member paths with the target plugin's manifest `skills` array and
inspect suite-scoped top-level resources. Repeat the install/update/inspection portion for
each affected suite while reusing the same isolated config root. Keep every scratch file
under the prefixed temporary root shown above.

## 8. Freeze, review, and ship

Commit the complete migration before independent review so the reviewer inspects an
immutable ref rather than a moving worktree. Give the reviewer the user's mapping as an
external anchor and ask it to falsify:

- mapping fidelity;
- manifest/install consistency;
- byte-and-mode preservation of moved bundles;
- stale standalone instructions or duplicate registrations.

Fix verified in-scope findings, repeat the narrow failed-axis review when substantive
changes occur, then run the repository's PR workflow. After merge:

- verify the remote merge state;
- delete the feature branch;
- fast-forward local main with `pull --ff-only`;
- verify local HEAD equals remote main;
- invoke `daymade-skill:skill-governance` only when the task also includes reconciling
  installed state on the current machine.

## Failure signals

| Signal | Meaning | Action |
|---|---|---|
| A moved file is not reported as a 100% rename or has a different blob/mode | Bundle behavior may have changed | Stop and inspect the exact file before calling the move lossless |
| A member exists in both a suite `skills` array and a standalone entry | Distribution model is ambiguous | Remove the duplicate entry or obtain approval to preserve both |
| README installs `<member>@<marketplace>` but only the suite is registered | Public install path is broken | Install the suite and invoke the member through the suite namespace |
| Local install passes but GitHub install fails | The suite depends on files outside its source subtree | Make the suite self-contained and retest from Git |
| Removed standalone entries remain installed locally | Manifest and installed state have diverged | Verify the suite replacement, then reconcile through Skill Governance |
| A hardcoded suite list omits the new suite | A derived inventory drifted | Delete the list and derive it from the manifest |

## Delivery report

Report:

- the final old-to-new mapping;
- new and bumped suite versions;
- removed standalone installation identities and the replacement commands;
- bundle-preservation and real-install evidence;
- changed SSOT/documentation surfaces;
- pre-existing warnings or intentionally retained historical examples;
- any installed-state work not performed because it was outside scope.
