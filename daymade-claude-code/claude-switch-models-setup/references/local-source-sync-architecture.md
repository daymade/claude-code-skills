# Local Source Sync Architecture

This reference explains how maintainer machines keep Claude Code profiles and Codex skills aligned with local source repos.

## Goal

Local source repos are the single source of truth. Installed runtime locations should not become editable copies that drift from source.

## Runtime Model

Edits to an already activated canonical source require no sync command.
Authoring checkouts have a separate ownership boundary; for independent Fleet
clones, use [Leased Fleet authoring clones](#leased-fleet-authoring-clones).

- Claude Code plugin cache version directories are symlinks to source plugin directories.
- Codex user Skills selected by the expanded activation policy are symlinks from
  `~/.agents/skills` to source Skill directories.
- Managed marketplaces named in `claude_active_marketplaces` can also provide
  source-backed personal Claude entries under `~/.claude/skills`. This is an
  independent host choice: it fills direct links only where the current Claude
  plugin install and enable state does not already provide or explicitly block
  the Skill.
- `~/.codex/skills/.system` is owned by Codex itself. User-source sync neither
  writes into it nor treats the surrounding legacy root as a normal activation
  target. The optional compatibility subset keeps same-source legacy links only
  for long-lived hooks or processes that still hold old absolute paths.
- Existing Claude Code/Codex sessions may need a restart because they load skill metadata at session start, but the filesystem content is already source-backed.

The source marketplaces are inventory; the activation manifest is policy. A Skill
can remain available in source and Claude's marketplace without occupying Codex's
global prompt. The sync scripts exist for topology repair, not day-to-day editing.

## What Changes Need Automation

| Change | Mechanism |
|---|---|
| Edit an existing `SKILL.md`, script, reference, or asset in an activated canonical source | Live through symlink; restart running agent session if needed |
| Install/uninstall, or `claude plugin enable`/`disable --scope user`, a plugin in the default Claude profile | Default `settings.json` / `installed_plugins.json` changes; LaunchAgent watcher mirrors state to every profile within seconds (verified 2026-08-22: launchd run counter incremented within 5s of a `settings.json` touch) |
| Add a new skill/plugin entry | Marketplace manifest changes; LaunchAgent watcher runs source sync |
| Remove or rename a skill entry | Marketplace manifest changes; the watcher prunes stale managed links from `.agents/skills` but only reports legacy `.codex/skills` links for reviewed cleanup |
| Bump `plugins[].version` | Marketplace manifest changes; LaunchAgent watcher creates/updates the version symlink and installed metadata |
| Change the Codex global user set | Edit `active_skills` for individual names or `active_marketplaces` for whole managed marketplaces; the watcher links the expanded set into `~/.agents/skills` |
| Include/exclude skills without enumerating the full set | Schema v2: `include_skills` adds names on top of the other selectors, `exclude_skills` removes names even if another selector activated them. The two must not overlap (load-time abort). Final selection resolves in the order `active_skills` → `active_marketplaces` → `include_skills` → `legacy_codex_compat_skills`, then `exclude_skills` subtracts |
| Change Claude personal source links | Edit `claude_active_marketplaces`; the watcher reconciles allowed direct entries under `~/.claude/skills` without installing or bypassing plugin state |
| A long-lived hook/process still holds `~/.codex/skills/<name>` | Add that already-active name to `legacy_codex_compat_skills`; the watcher keeps a same-source legacy link without reactivating the full source inventory |
| Add a new Claude profile | `claude-profiles-init` runs source sync and plugin profile sync |
| Launch Kimi/GLM/DeepSeek/Step profile | `claude-profile` runs source sync, then mirrors enabled plugins |
| Watcher missing or non-macOS machine | Run `sync-local-skill-sources.py --apply` as a repair command |

Both Python sync scripts take the same cross-process lock — a lock directory kept in the Claude config dir, deliberately OUTSIDE the plugins directory so the sync never mirrors the lock itself into profiles — before changing marketplace JSON, installed plugin metadata, or cache symlinks. This matters because power users may open several tmux panes or terminal windows at once; without one shared lock, simultaneous `claude-profile ...` launches can race on cache symlink creation or `known_marketplaces.json` temp-file replacement.

Profile state uses `.claude.json` inside each `CLAUDE_CONFIG_DIR`. Older `claude.json` files may still exist as harmless legacy files, but modern Claude Code will not use them as the profile state file.

## Source Repo Discovery

The discovery inputs and accepted marketplace identities are owned by
[`sync-local-skill-sources.py`](../scripts/sync-local-skill-sources.py), in
`main()`, `infer_repos()` and `LOCAL_MARKETPLACE_NAMES`. Do not maintain a second
discovery order or candidate list. Inspect the deployed owner's read-only output:

```bash
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --print-source-inventory
```

A repo is identified by `.claude-plugin/marketplace.json`, read by `marketplace_name()`. Only one state is silent; the rest raise, so a repo stops vanishing from discovery because of a manifest it does have:

| State | Answer |
|---|---|
| The manifest path does not exist (`os.lstat` raises `FileNotFoundError`/`NotADirectoryError`) | `None`, silently. Discovery calls this for every ancestor of the script path, for hardcoded base candidates that do not exist, and for a `.claude-plugin` that is a plain file (there the manifest path genuinely is not there), so silence is required here. |
| The manifest path exists but cannot be read — `OSError`, `json.JSONDecodeError`, or `UnicodeDecodeError` | Raises `UnreadableMarketplaceManifest`, naming the manifest path and the underlying error. `UnicodeDecodeError` is a `ValueError`, not an `OSError`/`JSONDecodeError`, and is the realistic shape for a CJK-heavy manifest torn mid-multibyte-character, so it must be in the tuple. A read that fails only because a writer is mid-flight clears on its own, so the message asks for one retry after that writer finishes. |
| The manifest path exists but is not a readable regular file (dangling symlink, the manifest is a directory) | Same `UnreadableMarketplaceManifest`. `is_file()` would answer False here, which is the "no manifest" answer. |
| The manifest path exists but cannot even be looked at (`EACCES` on `.claude-plugin`) | Same `UnreadableMarketplaceManifest`. `Path.is_file()` raises `PermissionError` here; `os.path.lexists()` would return False, which is the "no manifest" answer, so a checkout with drifted ownership would silently drop out of discovery. Ask `os.lstat` directly and treat everything except `FileNotFoundError`/`NotADirectoryError` as "exists but unusable". |
| It reads whole, but declares no usable non-empty string `name` | Raises `InvalidMarketplaceManifest`, naming the manifest path and that the file itself is malformed in that checkout, so retrying will not help. |

An unreadable manifest is not a missing repository. Git branch switches can
unlink and rewrite working-tree files: a concurrent-reader experiment on a
160 KB CJK manifest observed torn reads and momentary `FileNotFoundError`s;
its no-writer control observed neither. A changed inode does not establish
atomicity. This demonstrates a possible writer class, not the cause of a
particular failed read. `git commit` does not rewrite the working-tree file.
Retry once after the writer finishes; a malformed complete file needs repair.

A manifest that names a marketplace outside `LOCAL_MARKETPLACE_NAMES` is a normal answer, not a failure: `add_repo()` skips it and keeps the others. A name padded with whitespace falls into that same silent path by design — `marketplace_name()` does not know the activation manifest, so it cannot tell "an unmanaged foreign marketplace" from "our marketplace with a typo'd name". `skill-install-audit.py` checks manifest presence with `.is_file()`, so a dangling-symlink or directory manifest is silently skipped there; the audit and discovery reader have distinct error coverage.

## Host-Specific User-Skill Activation

The machine-local manifest is
`~/.config/claude-switch-models-setup/codex-active-skills.json`. Start from the
bundled [`assets/templates/codex-active-skills.json`](../assets/templates/codex-active-skills.json);
do not copy its full JSON into another document.

Rules:

- `active_skills` selects individual frontmatter names for Codex. Names refer to
  frontmatter `name`, not directory basename or plugin name.
- When a selected marketplace declares suite plugins, expand each suite member
  to its final skill directory name before writing `active_skills`. The syncer
  treats suite entries as source routes, not as Codex-facing skill names.
- If the syncer reports that a checkout is on a branch that predates the skill
  links, switch that source repo to `main` before syncing. A feature branch
  forked before a skill was merged does not register that skill, so the syncer
  skips and warns instead of linking it. The warning is about branch state, not
  manifest correctness.
- Missing manifest, unsupported schema, invalid source preferences, or an
  undeclared duplicate name abort before any affected root is changed. See
  “Explicit source preferences” below for intentionally distinct same-name bundles.
- An active name that no discovered checkout registers does not abort. It is
  reported on stderr with each checkout's current branch and skipped for that
  pass; the remaining names still converge, and the skipped one is linked on the
  first pass after some checkout registers it. The usual cause is a shared
  checkout parked on a feature branch that forked before the skill merged to
  `main`; a misspelled or retired name repeats the warning until the manifest is
  corrected. A link the checkout registered earlier and no longer does is pruned
  like any other stale managed link, into `.source-sync-backups/`.
- The syncer creates and verifies the selected links in `~/.agents/skills`
  before changing any managed legacy links in `~/.codex/skills`.
- `legacy_codex_compat_skills` is optional. When present it must be an array;
  explicit JSON `null` is invalid. Its names must be a duplicate-free subset of
  `active_skills`. Marketplace expansion does not satisfy this subset rule: even
  if `active_marketplaces` selects the same Skill for Codex, the compatibility
  name must still be listed explicitly in `active_skills`. It is for live
  consumers that still retain an old absolute path, not a second activation
  inventory.
- Compatibility links and their `.agents` counterparts resolve to the same
  source directory frozen at the start of the pass. Registered plugin and Skill
  sources carry their declared repo and load-time inode into the freeze step;
  containment and identity are checked again there, then the final cross-root
  verifier checks the frozen source both before and after reading both links.
  Lexical, symlink, or validation-to-freeze escapes fail before activation.
  Other source-backed legacy links are reported for reviewed cleanup and remain
  untouched by the background watcher.
- At a requested legacy compatibility path, only an already-correct same-source
  symlink or an empty path is accepted. A real file, real directory, third-party
  symlink, or wrong managed-source symlink fails visibly and remains untouched;
  the syncer never archives or replaces it. Creation builds a private temporary
  symlink and publishes that known inode with an atomic, no-overwrite hard link;
  the temporary name is then removed. A path another process creates or replaces
  before, during, or after publication is preserved and the run fails even when
  the competing link happens to use the same source.
- During an apply pass, each affected root that exists must be a real directory.
  Before the mutable phase the syncer captures the affected root identities;
  pinning rejects a root that appeared, disappeared, or changed inode in the
  meantime. It freezes existing ancestor aliases exactly once, never re-resolves
  that frozen path, then walks every remaining component with no-follow directory
  semantics, keeps all top-level operations on that handle, and rechecks pathname
  identity before success. A root symlink or concurrent real-directory replacement
  therefore fails instead of redirecting active-root pruning into the legacy root.
  A missing root that the selected policy actually needs is created exclusively
  relative to an already-opened real parent.
- A marketplace named in the manifest's optional `active_marketplaces` has its whole
  current membership added to the Codex selection, so adding or removing a plugin
  there needs no per-Skill policy edit. An empty `active_skills` array therefore
  selects no individual names; Codex still activates members of selected marketplaces. Unknown names fail at manifest
  load, before any link is touched; marketplaces absent from that list are unaffected.
  Without it, a marketplace whose own installer activates every registered Skill will
  keep recreating links this syncer then prunes, and the two writers silently undo
  each other.
- `claude_active_marketplaces` independently opts an owned marketplace into
  personal Claude Skill activation without installing plugins or changing
  `enabledPlugins`. The bundled template declares the empty defaults. New registered
  members need no second per-Skill edit. The syncer creates missing links in
  `<claude-dir>/skills`, using the same root identity, source containment, atomic
  creation, and recoverable pruning checks as the Codex root.
  `--skip-claude-skills` leaves that root alone. Existing correct direct links
  retain their identity. An enabled user plugin already provides its members, so
  it receives no new direct aliases. Explicitly disabled plugins and installed
  plugins without a known enabled state do not gain a new personal entry; unknown
  states are reported. A scoped install conflict fails. User-owned directories
  and foreign links are not replaced. A pre-existing direct Skill remains
  independent of a disabled plugin with the same source.
- With the pinned layout, the background daemon executes a **pinned plugin copy**, installed into its own
  `CLAUDE_CONFIG_DIR` under `~/.local/share/`, not the live checkout. That isolation is
  deliberate: editing a source repo must not change what an already-running daemon does.
  The cost is that nothing advances the pin — a fix can be merged, tested and believed
  shipped while the daemon keeps running the old code. Source updates never advance
  this pin automatically. Follow the single “advance the pin” procedure in
  [troubleshooting.md](troubleshooting.md#advance-the-pin).
  `scripts/setup.sh` refuses to relink such a machine to the checkout; SKILL.md setup
  step 2 owns the two layouts.
- Reinstall the LaunchAgent after advancing its runtime pin. `--install` uses uv
  once to install Python in this profile manager's own configuration directory;
  ordinary runs invoke that absolute interpreter directly. The daemon uses the
  Python commands' shared lock and runs only at load and on `WatchPaths` events;
  the generated plist has no `StartInterval`. After installation or a deliberate
  trigger, require a new UTC
  `source-sync verified links and profiles at ...` log line. Registration and exit
  code alone do not prove a recent successful pass.
- Skills outside a host's expanded activation policy remain cold for that host.
  Real directories and third-party symlinks are outside automatic retirement.

`scripts/setup.sh` writes the empty template to a private temporary file and
publishes it with a no-overwrite hard link only when no manifest exists. A
concurrent writer wins and is preserved; setup never overwrites the user's
current selection.

### Convert an installed single-Skill plugin to a personal source link

For an explicitly authorized conversion, the executor uses the official Claude plugin CLI
and this existing sync owner; do not hand-edit plugin registries or create links manually.
This applies to a user-scope plugin that supplies only the requested Skill. A suite or plugin
with other commands, hooks, agents or components stays on its existing route until those
components have an authorized replacement.

1. Read the current activation manifest, registered source inventory, user-scope plugin record
   and enable state. Confirm the requested canonical source, its owning marketplace in
   `claude_active_marketplaces`, and the Codex selection when both hosts must agree. Disabled,
   unknown or conflicting scope is a diagnosis to resolve, not permission to bypass it.
2. Check `claude plugin uninstall --help` in the owning default profile. With `PLUGIN_ID` set
   to the verified `plugin@marketplace` identity, run
   `claude plugin uninstall "${PLUGIN_ID:?}" --scope user --keep-data --json`.
   Read back that exact plugin's uninstall result and installed/enabled state. `--keep-data`
   retains persistent plugin data; it does not prove cache retention. Verify cache paths still
   required by existing sessions separately and do not purge them. Never remove the marketplace
   to convert one plugin.
3. Run the deployed owner's dry-run below. Keep discovery of every marketplace named by the
   manifest: restricting `--repo` to just this Skill's repo can fail the policy preflight.
   Inspect all proposed changes; proceed only when they are within the authorized conversion.

   ```bash
   python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py \
     --skip-claude-cache --skip-codex --skip-agents --skip-marketplace-source
   ```

   After a successful, accepted dry-run, repeat that command with `--apply`. These flags limit
   repair to Claude personal links; they do not install or change the Codex selection. A watcher
   may already have created the requested link, so a no-change plan is valid only after readback.
4. Resolve both requested host entries to the intended canonical source, then use the
   official CLI to close any remaining enabled plugin route. If its user-scope setting is still
   enabled, run `claude plugin disable "${PLUGIN_ID:?}" --scope user --json` and read back the
   disabled state. Do this only after the personal source link exists: the syncer preserves
   that existing route independently, but refuses to create one for a disabled plugin.
   If native initialization recreates an install record while the old route is enabled,
   repeat the exact user-scope uninstall after disabling that route; the earlier uninstall
   result was partial. Require the record to be absent and retain the verified source link.
5. Use the
   [host availability and task-behavior checks](../../../daymade-skill/skill-governance/references/skill-surface-governance.md#14-verify-a-newly-registered-skill)
   for fresh-host discovery and actual consumption. After initialization, re-read the exact
   plugin state and source links to ensure the old route was not reinstalled. Existing sessions
   can retain old catalogs.
   If uninstall succeeded but sync failed, report that partial state, preserve the source/cache,
   and repair through this owner or restore the verified plugin through the official CLI;
   do not manufacture success with a manual link.

### Explicit source preferences

Use activation schema 3 when two deliberately different bundles register the
same frontmatter name. Add `source_preferences[skill]` with exactly two fields:
`prefer` is the selected `plugin@marketplace` identity; `over` is a non-empty
array of the other permitted identities. Take identities from the registered
marketplace manifests, including the owning suite name for suite members.

The resolver requires the observed candidate set to equal `prefer` plus `over`.
A missing preferred source, stale alternative, unexpected third candidate,
unknown marketplace, duplicate identity or JSON key, malformed rule, or unknown
schema-3 field fails before writes. A preference does not excuse two checkouts
of the same marketplace or duplicate names inside one marketplace. Names without
a preference retain the duplicate-source error. There is no fallback winner.

Activation still selects names. The canonical resolver chooses their source for
Codex, legacy compatibility and Claude personal links, even when the name was
activated through another marketplace. Claude plugin enable/disable and scope
checks still apply to the chosen plugin. Preferences do not change plugin installs,
enablement or source content; all candidate bundles remain in inventory.

Consumers call `merge_source_skills(sources, policy.source_preferences)` after
`load_skill_activation_policy(path)`. It returns one `SkillSource` per registered
name without modifying the input inventory. `skill-install-audit.py` uses this
same resolver to verify links. Dry-run progress reports each explicit choice;
structured inventory records the choice even with `--quiet`.

Deploy the new reader before changing a machine's manifest to schema 3. The new
reader continues accepting schema 1/2 without preferences; older readers reject
schema 3 instead of silently ignoring the choice. This is host-local policy:
never put a maintainer's source choices in the empty installation template.

### Leased Fleet authoring clones

For an approved Fleet pool, the operator enrolls its exact physical root in
`~/.config/claude-switch-models-setup/authoring-pools.json`. Keep machine values
outside the Skill bundle. The owner reads this separate file only for
`--print-source-inventory`; an absent file preserves the canonical inventory.
Use schema 1 with a `pools` array. Each entry has exactly `marketplace`,
`canonical_repo`, `origin`, and `pool_root`: the marketplace must be a discovered
managed source, the canonical repository must be its exact registered checkout,
and origin must equal that checkout's configured Git origin. Matching origin
alone never enrolls another clone. `--authoring-pools-manifest <absolute-path>`
selects another operator-owned enrollment file for a bounded read-only probe.

Take the canonical repository from that host's deployed source owner, and compare
the enrollment's origin with the approved pool's `pool.json` and the configured
Git origins of the canonical repository and leased clone. These strings must
match exactly; equivalent SSH and HTTPS URLs do not substitute for one another.
Pool configuration alone is not owner enrollment.

The owner validates Fleet's matching `pool.json` and `init.json`, its configured
slot count, and `leases.json`. Only a configured slot with a non-empty token,
owner, task, branch and base, on that exact task branch with its own physical
`.git` directory and exact origin, contributes authoring candidates. The lease
base must be an ancestor of its current HEAD. Registered Skill names, plugin
identities and relative source paths must match the canonical marketplace.
Dirty authoring content is allowed. Missing, null, malformed, foreign-origin,
symlinked or changed evidence rejects the entire inventory call; repair the
specific enrollment or Fleet state before retrying. Unleased slots and the
integration clone contribute no authoring authority.

For a leased source, `marketplaces[marketplace][skill]` becomes a candidate array,
retaining the canonical entry first. Skill Creator's source contract accepts
these owner-emitted candidates. `selected_skills`, source preferences, sync,
cache installation and host links continue using only canonical sources.
Printing inventory never writes enrollment, leases, Git state or install state.
After deploying the owner reader, verify the ordinary source-contract check from
the leased Skill directory without supplying an independent inventory override;
also check an unleased sibling remains invalid. A pinned runtime must advance
through the existing pin-update procedure before this readback proves activation.

Installation auditors use `selected_skills` after resolving the host's activation
policy, not the authoring candidates in `marketplaces`.
Lease ownership authorizes the task's source checkout; it does not make that
checkout the installed Skill identity. Keep installation and fresh-host acceptance
on the canonical source route. A returned lease's earlier positive check is
historical evidence, not current authoring authority.

### Third-party cold inventory

The activation manifest controls only Skills registered by the managed local
source marketplaces. A third-party bundle already installed under
`~/.agents/skills` remains outside that ownership boundary: the syncer preserves
it whether or not its name appears in the manifest.

When such a bundle must remain installed for unembedded references, scripts, or
assets but should stay out of Codex's model-visible catalog, use the “keep on disk,
hide from Codex” branch in `/daymade-skill:skill-governance`. That Skill owns the
exact `skills.config` shape, child-Skill handling, clean-session verification, and
resource-preservation check. This reference deliberately does not copy those steps:
its only contract is that `codex-active-skills.json` must not be repurposed to
control third-party bundles the source syncer does not own.

## macOS Watcher

Install:

```bash
~/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh --install
```

The LaunchAgent label is `ai.daymade.claude-skill-source-sync`. It watches:

- `~/.claude/settings.json`
- `~/.claude/plugins/installed_plugins.json`
- every activation/marketplace path emitted by `sync-local-skill-sources.py --print-watch-paths`

Verify registration and generated configuration:

```bash
launchctl print gui/$(id -u)/ai.daymade.claude-skill-source-sync
plutil -p ~/Library/LaunchAgents/ai.daymade.claude-skill-source-sync.plist
```

After installation or a deliberate trigger, verify liveness with a newly written
success line, not a historical line or `launchctl` exit status:

```bash
tail -50 ~/Library/Logs/claude-switch-models-setup/source-sync.err.log
tail -50 ~/Library/Logs/claude-switch-models-setup/source-sync.out.log
```

### Optional failure recorder

`scripts/sync-daemon-recorder.sh` wraps the daemon entry so a **failed** pass leaves a
trace. The upstream runner prints its `verified` line only after every step succeeds,
so a failing pass writes nothing to `source-sync.out.log` at all — the success log can
stay fresh forever while passes keep failing. The wrapper appends one line (timestamp,
exit code, last stderr line) to `source-sync.failures.log` on a non-zero exit, collapses
consecutive identical failures, rotates at 1 MB, and re-raises the original exit code so
launchd still records it. That reason is scoped to the current pass by a byte-count
snapshot taken before the run: `err.log` is append-only, so a bare `tail -n 1` would
blame whatever failed last time, and a silent pass would inherit a stranger's traceback.
When this pass wrote no stderr at all the line says `(no new stderr this pass)` instead
of guessing. It adds no notification and no remediation. `setup.sh` deploys the
recorder and its calibration script as links; it does not activate the wrapper.
Existing ordinary files are refused so local edits can be compared and preserved
before conversion to links.

Install it by pointing the plist's `ProgramArguments` at the wrapper instead of the
daemon entry, then `bootout` + `bootstrap`. `--install` does not overwrite an entry
that points elsewhere: it keeps the wrapper (and its arguments) and says so on stderr,
so installing the daemon after the recorder is in place does not detach it. Remove the
recorder the same way either route does — `--uninstall`, then `--install` — which
repoints the job back at the daemon entry.

**Liveness.** A fresh `verified` line proves that *some* pass succeeded, never that
*every* pass did. The health signal is the failure path — `source-sync.failures.log`
with the wrapper, `source-sync.err.log` without it — not the success log's freshness.
`launchctl` reports only the last exit code, so an intermittently failing job reads as
healthy between failures.

Uninstall:

```bash
~/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh --uninstall
```

## Verification Checklist

Use implementation-owned inventory instead of a hand-maintained plugin or Skill
list. First confirm which source identities are registered, then preview the exact
host selections and affected paths:

```bash
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --print-source-inventory
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py
```

For each identity required by the task, confirm its resolved link or enabled
user-plugin route against that inventory. Then run the target-specific fresh-host
acceptance gate in `/daymade-skill:skill-governance` §14. The source dry-run and
the read-only installation audit describe derived state; neither proves a fresh
Claude Code or Codex catalog.

Inspect only the legacy compatibility names requested by the task. Confirm each
link and its active counterpart resolve to the same source; do not treat a scan
of the legacy root as the expected activation inventory.

For profile drift:

```bash
python3 ~/.config/claude-switch-models-setup/claude-plugins-sync.py
```

Then compare `enabledPlugins` between the default profile and each profile.

For launch-path verification, take the profile names from `claude-profiles-ls` and
test those configured profiles concurrently because that is how race bugs surface.
Every configured profile should print the same Claude Code version and no sync
traceback. A profile directory without a matching
`~/.claude/settings/<profile>.json` is stale and should fail fast at settings-file
lookup.

If a `claude-profile <name> -p ...` probe starts successfully, debug logs should show plugin and skill loading before any API call. Network or TLS errors after lines such as `Loaded ... installed plugins` and `Loaded ... unique skills` are provider connectivity problems, not skill-sync failures.

## Design Boundaries

- This system does not hot-reload already-running Claude Code or Codex sessions. Restart the session when skill metadata needs to be re-read.
- This system does not install arbitrary new marketplaces. It only manages source repositories accepted by the syncer's implementation-owned marketplace policy.
- This system does not delete or automatically move real Skill copies. A real
  object or third-party link at a selected `~/.agents/skills` name fails visibly
  and remains in place for explicit `skill-governance` classification.
- In `~/.agents/skills`, this system prunes a symlink only when its resolved
  target is inside a managed source repo and its name is outside the
  active set. Pruning atomically moves that exact entry into
  `.source-sync-backups/`; it does not delete the object. The background pass does not clean those
  buckets. A backup can contain source variants absent from every repository's
  object store. Judge it with `prune-source-sync-backups.py`, which hashes every entry and keeps any bucket
  it cannot prove reproducible; never clear the directory wholesale. Classification and
  identity come from one entry snapshot, and the move uses the platform's
  no-replace rename primitive. If an unrelated writer replaces the entry after
  classification, the syncer restores that winner to the original name when it
  is still empty; unselected pruning then skips it, while a selected-name
  collision fails. If an even newer winner already occupies the original name,
  neither is overwritten: the earlier concurrent entry stays in recovery and
  the run fails visibly. In legacy `~/.codex/skills`, the syncer never removes
  any entry: stale managed links are reported for explicit `skill-governance`
  cleanup. Real legacy directories, third-party links, and `.system` remain
  untouched.
- Loose real Skills left in the legacy Codex root require a one-time, reviewed
  migration or retirement decision; automatic sync deliberately cannot infer it.
