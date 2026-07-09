# Local Source Sync Architecture

This reference explains how maintainer machines keep Claude Code profiles and Codex skills aligned with local source repos.

## Goal

Local source repos are the single source of truth. Installed runtime locations should not become editable copies that drift from source.

## Runtime Model

Normal source edits require no sync command:

- Claude Code plugin cache version directories are symlinks to source plugin directories.
- Codex skill directories are symlinks to source skill directories.
- Existing Claude Code/Codex sessions may need a restart because they load skill metadata at session start, but the filesystem content is already source-backed.

The sync scripts exist for topology repair, not day-to-day editing.

## What Changes Need Automation

| Change | Mechanism |
|---|---|
| Edit an existing `SKILL.md`, script, reference, or asset | Live through symlink; restart running agent session if needed |
| Install/uninstall a plugin in the default Claude profile | Default `settings.json` / `installed_plugins.json` changes; LaunchAgent watcher mirrors state to every profile |
| Add a new skill/plugin entry | Marketplace manifest changes; LaunchAgent watcher runs source sync |
| Remove or rename a skill entry | Marketplace manifest changes; LaunchAgent watcher prunes stale Codex/agents symlinks that point into managed source repos |
| Bump `plugins[].version` | Marketplace manifest changes; LaunchAgent watcher creates/updates the version symlink and installed metadata |
| Add a new Claude profile | `claude-profiles-init` runs source sync and plugin profile sync |
| Launch Kimi/GLM/DeepSeek/Step profile | `claude-profile` runs source sync, then mirrors enabled plugins |
| Watcher missing or non-macOS machine | Run `sync-local-skill-sources.py --apply` as a repair command |

## Components

| Component | Role |
|---|---|
| `sync-local-skill-sources.py` | Idempotent repair primitive. Finds local source repos, points local marketplaces at directory sources, links Claude cache/Codex/agents installs to source, prunes stale managed Codex/agents symlinks, and updates installed plugin metadata. |
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

It only accepts repos whose `.claude-plugin/marketplace.json` name is `daymade-skills` or `daymade-skills-pro`. If none are found, it fails fast instead of guessing.

## macOS Watcher

Install:

```bash
~/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh --install
```

The LaunchAgent label is `ai.daymade.claude-skill-source-sync`. It watches:

- `~/.claude/settings.json`
- `~/.claude/plugins/installed_plugins.json`
- `<daymade-skills>/.claude-plugin/marketplace.json`
- `<daymade-skills-pro>/.claude-plugin/marketplace.json`

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
root = pathlib.Path.home()/".codex/skills"
for name in ["skill-creator", "sync-feishu-minutes", "claude-switch-models-setup"]:
    p = root/name
    print(name, p.is_symlink(), p.resolve())
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
- This system does not install arbitrary new marketplaces. It only manages the local daymade source repos.
- This system does not delete old real copies. It moves them into `.source-sync-backups/` before replacing them with symlinks.
- This system may remove stale symlinks from Codex/agents skill roots, but only when the symlink target is inside a managed daymade source repo and the skill is no longer registered in the marketplace manifest.
