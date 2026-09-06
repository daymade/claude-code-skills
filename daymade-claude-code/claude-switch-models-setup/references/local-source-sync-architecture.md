# Local Source Sync Architecture

This reference explains how maintainer machines keep Claude Code profiles and Codex skills aligned with local source repos.

## Goal

Local source repos are the single source of truth. Installed runtime locations should not become editable copies that drift from source.

## Runtime Model

Normal source edits require no sync command:

- Claude Code plugin cache version directories are symlinks to source plugin directories.
- Codex user Skills named in the explicit activation manifest are symlinks from
  `~/.agents/skills` to source Skill directories.
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
| Edit an existing `SKILL.md`, script, reference, or asset | Live through symlink; restart running agent session if needed |
| Install/uninstall, or `claude plugin enable`/`disable --scope user`, a plugin in the default Claude profile | Default `settings.json` / `installed_plugins.json` changes; LaunchAgent watcher mirrors state to every profile within seconds (verified 2026-08-22: launchd run counter incremented within 5s of a `settings.json` touch) |
| Add a new skill/plugin entry | Marketplace manifest changes; LaunchAgent watcher runs source sync |
| Remove or rename a skill entry | Marketplace manifest changes; the watcher prunes stale managed links from `.agents/skills` but only reports legacy `.codex/skills` links for reviewed cleanup |
| Bump `plugins[].version` | Marketplace manifest changes; LaunchAgent watcher creates/updates the version symlink and installed metadata |
| Change the Codex global user set | Edit `~/.config/claude-switch-models-setup/codex-active-skills.json`; watcher links only that set into `~/.agents/skills` |
| A long-lived hook/process still holds `~/.codex/skills/<name>` | Add that already-active name to `legacy_codex_compat_skills`; the watcher keeps a same-source legacy link without reactivating the full source inventory |
| Add a new Claude profile | `claude-profiles-init` runs source sync and plugin profile sync |
| Launch Kimi/GLM/DeepSeek/Step profile | `claude-profile` runs source sync, then mirrors enabled plugins |
| Watcher missing or non-macOS machine | Run `sync-local-skill-sources.py --apply` as a repair command |

## Components

| Component | Role |
|---|---|
| `sync-local-skill-sources.py` | Idempotent repair primitive. Finds local source repos, rejects duplicate source names, validates the explicit Codex activation manifest, points Claude marketplaces/caches at source, links and verifies the selected user set in `~/.agents/skills`, then creates/confirms the explicit legacy compatibility subset and reports other managed legacy links without deleting them. |
| `sync-local-skill-sources-daemon.sh` | macOS LaunchAgent runner. Installs or removes the watcher and runs one locked sync pass. |
| `claude-plugins-sync.py` | Per-profile Claude Code sync. Builds profile-local `known_marketplaces.json`, shares installed plugin state, and mirrors `enabledPlugins`. |
| `claude-profiles.sh` | Shell integration. Runs local source sync on profile init/launch before profile plugin sync. |

Both Python sync scripts take the same cross-process lock — a lock directory kept in the Claude config dir, deliberately OUTSIDE the plugins directory so the sync never mirrors the lock itself into profiles — before changing marketplace JSON, installed plugin metadata, or cache symlinks. This matters because power users may open several tmux panes or terminal windows at once; without one shared lock, simultaneous `claude-profile ...` launches can race on cache symlink creation or `known_marketplaces.json` temp-file replacement.

Profile state uses `.claude.json` inside each `CLAUDE_CONFIG_DIR`. Older `claude.json` files may still exist as harmless legacy files, but modern Claude Code will not use them as the profile state file.

## Source Repo Discovery

`sync-local-skill-sources.py` locates source repos in this order:

1. `--repo <path>` arguments.
2. `DAYMADE_SKILL_SOURCE_REPOS` as a colon-separated list.
3. The script's ancestor directories, when run from a source checkout.
4. Directory-source entries in `~/.claude/plugins/known_marketplaces.json`.
5. Common local worktree candidates under `~/workspace` and `~/Workspace`.

Accepted marketplace identities are defined only by `LOCAL_MARKETPLACE_NAMES`, and conventional workspace candidates only by `infer_repos()` in `scripts/sync-local-skill-sources.py`. Do not copy either current set into documentation. The script's default dry-run prints the resolved source inventory; if none qualify, it fails fast instead of guessing. Non-conventional checkout paths require `--repo`, `DAYMADE_SKILL_SOURCE_REPOS`, or a registered directory-source marketplace.

## Codex User-Skill Activation

The machine-local manifest is
`~/.config/claude-switch-models-setup/codex-active-skills.json`:

```json
{
  "schema_version": 1,
  "active_skills": ["skill-name"],
  "legacy_codex_compat_skills": []
}
```

Rules:

- Names refer to frontmatter `name`, not directory basename or plugin name.
- Missing manifest, unsupported schema, duplicates, or two source bundles
  declaring the same name abort before either active root is changed.
- An active name that no discovered checkout registers does not abort. It is
  reported on stderr with each checkout's current branch and skipped for that
  pass; the remaining names still converge, and the skipped one is linked on the
  first pass after some checkout registers it. The usual cause is a shared
  checkout parked on a feature branch that forked before the skill merged to
  `main`; a misspelled or retired name repeats the warning until the manifest is
  corrected. A link the checkout registered earlier and no longer does is pruned
  like any other stale managed link, into `.source-sync-backups/`.
- An empty list means “activate none”; it does not fall back to all marketplace
  entries.
- The syncer creates and verifies the selected links in `~/.agents/skills`
  before changing any managed legacy links in `~/.codex/skills`.
- `legacy_codex_compat_skills` is optional. When present it must be an array;
  explicit JSON `null` is invalid. Its names must be a duplicate-free subset of
  `active_skills`. It is for live consumers that still retain an old absolute
  path, not a second activation inventory.
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
- During an apply pass, each configured root that exists must be a real
  directory. Before the mutable phase the syncer captures both root identities;
  pinning rejects a root that appeared, disappeared, or changed inode in the
  meantime. It freezes existing ancestor aliases exactly once, never re-resolves
  that frozen path, then walks every remaining component with no-follow directory
  semantics, keeps all top-level operations on that handle, and rechecks pathname
  identity before success. A root symlink or concurrent real-directory replacement
  therefore fails instead of redirecting active-root pruning into the legacy root.
  A missing root that the selected policy actually needs is created exclusively
  relative to an already-opened real parent.
- A marketplace named in the manifest's optional `active_marketplaces` has its whole
  current membership treated as selected, so adding or removing a plugin there no
  longer needs a second manual edit to this manifest. Unknown names fail at manifest
  load, before any link is touched; marketplaces absent from that list are unaffected.
  Without it, a marketplace whose own installer activates every registered Skill will
  keep recreating links this syncer then prunes, and the two writers silently undo
  each other.
- The background daemon executes a **pinned plugin copy**, installed into its own
  `CLAUDE_CONFIG_DIR` under `~/.local/share/`, not the live checkout. That isolation is
  deliberate: editing a source repo must not change what an already-running daemon does.
  The cost is that nothing advances the pin — a fix can be merged, tested and believed
  shipped while the daemon keeps running the old code. Advance it with the same official
  commands that installed it, against that config dir:

  ```bash
  CLAUDE_CONFIG_DIR=<daemon config> claude plugin marketplace update <marketplace>
  CLAUDE_CONFIG_DIR=<daemon config> claude plugin update <plugin>@<marketplace>
  ```

  then repoint the script symlinks under `~/.config/claude-switch-models-setup/` at the
  new version directory. `skill-install-audit.py` reports the gap as `DAEMON_RUNTIME_LAG`;
  it is the only thing that compares the two numbers. `scripts/setup.sh` refuses to
  relink such a machine to the checkout; SKILL.md setup step 2 owns the two layouts.
- Unselected source Skills remain cold inventory. Real directories and third-party
  symlinks in either root are outside automatic retirement.

`scripts/setup.sh` writes the empty template to a private temporary file and
publishes it with a no-overwrite hard link only when no manifest exists. A
concurrent writer wins and is preserved; setup never overwrites the user's
current selection.

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

Verify:

```bash
launchctl print gui/$(id -u)/ai.daymade.claude-skill-source-sync
plutil -p ~/Library/LaunchAgents/ai.daymade.claude-skill-source-sync.plist
```

Logs:

```bash
tail -50 ~/Library/Logs/claude-switch-models-setup/source-sync.err.log
tail -50 ~/Library/Logs/claude-switch-models-setup/source-sync.out.log
```

Uninstall:

```bash
~/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh --uninstall
```

## Verification Checklist

Use these checks when debugging drift:

```bash
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --print-watch-paths

python3 - <<'PY'
import json, pathlib
for plugin_id in ["daymade-claude-code@daymade-skills", "sync-feishu-minutes@daymade-skills-pro"]:
    data = json.loads((pathlib.Path.home()/".claude/plugins/installed_plugins.json").read_text())["plugins"]
    rec = data[plugin_id][-1]
    p = pathlib.Path(rec["installPath"])
    print(plugin_id, rec["version"], p.is_symlink(), p.resolve())
PY

python3 - <<'PY'
import pathlib
root = pathlib.Path.home()/".agents/skills"
for name in ["skill-creator", "sync-feishu-minutes", "claude-switch-models-setup"]:
    p = root/name
    print(name, p.is_symlink(), p.resolve())
PY

python3 - <<'PY'
import pathlib
root = pathlib.Path.home()/".codex/skills"
print("system-owned", (root/".system").is_dir())
print("legacy-compat-links", [p.name for p in root.iterdir() if p.is_symlink()])
PY
```

For profile drift:

```bash
python3 ~/.config/claude-switch-models-setup/claude-plugins-sync.py
```

Then compare `enabledPlugins` between the default profile and each profile.

For launch-path verification, test concurrently because that is how race bugs surface:

```bash
# adjust the list to the profiles you actually configured
for profile in kimi glm deepseek stepfun anthropic; do
  tmux new-session -d -s "ccver-$profile" \
    "zsh -lc 'source ~/.config/claude-switch-models-setup/claude-profiles.sh; claude-profile $profile --version'"
done
```

Expected: every configured profile prints the same Claude Code version and no sync traceback. A profile directory without a matching `~/.claude/settings/<profile>.json` is a stale profile and should fail fast at settings-file lookup.

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
  `.source-sync-backups/`; it does not delete the object. Nothing ever cleans those
  buckets, and they look like disposable cache from the outside — but a 2026-09-05
  survey found most of them holding files present in no repository's object store,
  one carrying a 75-file variant of a skill whose shipped version has 13. Judge them
  with `prune-source-sync-backups.py`, which hashes every entry and keeps any bucket
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
