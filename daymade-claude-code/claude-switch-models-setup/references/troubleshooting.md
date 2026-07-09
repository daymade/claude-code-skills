# Common Issues and Fixes

## Profile fails to launch

Check that `~/.claude/settings/<profile>.json` exists and is valid JSON:

```bash
python3 -m json.tool ~/.claude/settings/kimi.json
```

Also check that the profile directory has `.claude.json`:

```bash
test -f ~/.claude-profiles/kimi/.claude.json
```

`claude.json` is a legacy filename and is not enough for modern Claude Code when `CLAUDE_CONFIG_DIR` points at the profile directory. Re-run `claude-profiles-init` to create missing `.claude.json` files.

## Doctor reports a broken symlink such as `image-cache`

Run:

```bash
claude-profiles-init
```

Profile symlinks intentionally point back into `~/.claude`. Claude Code may create optional runtime directories such as `image-cache/` and later remove them. Current `claude-profiles-init` prunes stale symlinks whose target was under `~/.claude`, then rebuilds the links that still have a real base directory.

## `claude-profile` command not found

The shell function is loaded by sourcing `claude-profiles.sh`. Either:
- Run `source ~/.config/claude-switch-models-setup/claude-profiles.sh`, or
- Open a new terminal so the rc-file source takes effect.

## Third-party model gets Anthropic errors

Make sure the profile's `env` block includes:

```json
{
  "ENABLE_TOOL_SEARCH": "false",
  "DISABLE_GROWTHBOOK": "1",
  "DISABLE_TELEMETRY": "1",
  "DISABLE_AUTOUPDATER": "1"
}
```

These flags prevent Claude Code from trying Anthropic-only features when talking to a third-party endpoint.

## Subagents use the wrong model

Set `CLAUDE_CODE_SUBAGENT_MODEL` to the same value as `ANTHROPIC_MODEL` in the profile settings. Otherwise subagents may fall back to the default Anthropic model.

## Marketplace says "corrupted installLocation"

Each profile needs its OWN `known_marketplaces.json` — its `installLocation` is
config-dir-specific (Claude validates with `path.resolve`, which does NOT resolve
symlinks), so it cannot be shared across profiles. `claude-plugins-sync.py` rebuilds them.
It runs automatically every time `claude-profile` init/launches; to run manually:

```bash
python3 ~/.config/claude-switch-models-setup/claude-plugins-sync.py
```

## Skill is installed in default Claude but missing in a third-party profile

Claude Code stores the enabled plugin map in each config directory's `settings.json`.
Run the profile syncer so every profile mirrors the default profile's `enabledPlugins`:

```bash
python3 ~/.config/claude-switch-models-setup/claude-plugins-sync.py
```

Restart the affected Claude Code window after syncing.

## Local skill source changes do not appear in Claude Code or Codex

Normal edits should be live because installed locations are symlinks to the source repos.
If they are not live, first check whether the path is still a symlink:

```bash
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --print-watch-paths
```

For structural changes such as new skill entries, removed skill entries, renamed skills,
or version bumps, the macOS watcher should run automatically:

```bash
launchctl print gui/$(id -u)/ai.daymade.claude-skill-source-sync
```

If the watcher is not installed, install it:

```bash
~/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh --install
```

Manual repair fallback:

```bash
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --apply
```

The script backs up existing real copies under `.source-sync-backups/` before creating symlinks. If a skill was removed from the marketplace manifest, it prunes only stale Codex/agents symlinks that point into the managed source repos; real directories are left alone. Restart any already-running Claude Code/Codex sessions after repairing because skill metadata is loaded at session start.

## Several profiles launched at once fail with sync tracebacks

This should not happen on current scripts: `sync-local-skill-sources.py` and `claude-plugins-sync.py` share a cross-process lock before writing marketplace JSON, installed plugin metadata, or cache symlinks.

If you still see `FileExistsError` while creating a symlink or `FileNotFoundError` while replacing `known_marketplaces.json`, update the installed helper scripts from the source skill and rerun:

```bash
cp <source>/scripts/claude-profiles.sh ~/.config/claude-switch-models-setup/claude-profiles.sh
cp <source>/scripts/claude-plugins-sync.py ~/.config/claude-switch-models-setup/claude-plugins-sync.py
cp <source>/scripts/sync-local-skill-sources.py ~/.config/claude-switch-models-setup/sync-local-skill-sources.py
```

Then verify with concurrent version probes:

```bash
for profile in kimi kimi-long glm deepseek css cssl step step-pay; do
  tmux new-session -d -s "ccver-$profile" \
    "zsh -lc 'source ~/.config/claude-switch-models-setup/claude-profiles.sh; claude-profile $profile --version'"
done
```

## Profile loads skills but model request fails

Run with `--debug-file` and look for the order of events. If the log shows `Loaded ... installed plugins` and `Loaded ... unique skills` before an API error, the skill/profile sync layer is working and the failure is in the provider network/TLS path.

Example failure class: `UNKNOWN_CERTIFICATE_VERIFICATION_ERROR` after all skill-loading lines. Diagnose the configured `ANTHROPIC_BASE_URL` and the local proxy/TLS chain; do not treat that as a missing-skill problem.

## I want to add another provider

1. Copy a template to `~/.claude/settings/<new-provider>.json`.
2. Fill in the API key and base URL.
3. Update the model names to match that provider's Anthropic-compatible model IDs.
4. Run `claude-profiles-init`.
5. Add an alias to your shell rc file if desired.

## I want to remove a provider

Run:

```bash
claude-profile-rm <provider>
```

This deletes only the isolation directory (`~/.claude-profiles/<provider>/`). It does **not** delete `~/.claude/settings/<provider>.json`; remove that manually if you want it gone.
