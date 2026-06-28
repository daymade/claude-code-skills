# Common Issues and Fixes

## Profile fails to launch

Check that `~/.claude/settings/<profile>.json` exists and is valid JSON:

```bash
python3 -m json.tool ~/.claude/settings/kimi.json
```

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
