---
name: openclaw-model-switch
description: 'Switch the default AI model for OpenClaw (e.g., Kimi K2.6 to K2.7). Use when the user wants to change the active LLM model, upgrade to a newer model version, switch between reasoning and non-reasoning models, or modify the openclaw.json model configuration. Triggers on phrases like "switch model", "change model", "upgrade to k2.7", "use k2.7", "模型切换", "切换模型".'
---

# OpenClaw Model Switch

Switch the default AI model used by OpenClaw by safely modifying `openclaw.json`.

## Quick Start

Run the switch script:

```bash
python3 scripts/switch-model.py <model-id> --restart
```

Example — upgrade to K2.7:
```bash
python3 scripts/switch-model.py kimi-k2.7-code --restart
```

Example — roll back to K2.6:
```bash
python3 scripts/switch-model.py k2p6 --restart
```

## What This Script Does

1. **Backs up** the current `openclaw.json` to `~/.kimi_openclaw/config-backups/`
2. **Adds** the target model definition to the provider's `models` array (if missing)
3. **Updates** `agents.defaults.model.primary` to point to the new model
4. **Restarts** the OpenClaw gateway (with `--restart` flag)

## When to Use

- Upgrading to a newly released model (e.g., K2.6 → K2.7)
- Switching between models for different tasks
- Rolling back after testing a new model
- Adding a model definition that the user knows exists but isn't configured

## Workflow

### Manual Switch (if script unavailable)

1. Read `~/.kimi_openclaw/openclaw.json`
2. Back it up manually to `config-backups/`
3. Add model definition to `models.providers.kimi-coding.models` (see [references/kimi-models.md](references/kimi-models.md))
4. Set `agents.defaults.model.primary` to `kimi-coding/<model-id>`
5. Save valid JSON
6. Restart gateway: `openclaw gateway restart` (or restart Kimi desktop)

### Verification

After restart, confirm the active model via:
- System prompt metadata: check `model=` and `default_model=` fields
- Or run: `openclaw status` (if available)

## Safety Rules

- **Always backup** before editing `openclaw.json`
- **Preserve** existing `apiKey`, `headers`, and plugin configurations
- **Validate JSON** after manual edits (use `python3 -m json.tool openclaw.json`)
- **Do not** commit config files containing API keys to version control

## Resources

- **scripts/switch-model.py** — Automated model switcher with backup and restart
- **references/kimi-models.md** — Model specs, config snippets, and troubleshooting
