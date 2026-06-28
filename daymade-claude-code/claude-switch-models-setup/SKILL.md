---
name: claude-switch-models-setup
description: Set up multiple isolated Claude Code CLI profiles so students and power users can run different LLM providers (Kimi, GLM, DeepSeek, StepFun, Anthropic) in separate terminal windows at the same time. Use this skill whenever the user asks about multi-provider Claude setup, multiple Claude Code windows, switching models, CLAUDE_CONFIG_DIR, post-class profile installation, or running Kimi/GLM/DeepSeek/StepFun alongside Anthropic in Claude Code.
---

# Claude Code Multi-Provider Profiles

## Overview

This skill creates an isolated-but-shared profile system for Claude Code CLI. Each profile gets its own `claude.json` state file (credentials, session history, plugin cache) while sharing skills, projects, hooks, and agents across all profiles.

The result: you can open one terminal with Kimi, another with DeepSeek, another with Anthropic — each running as a fully independent Claude Code process, without configuration bleed.

## How It Works

- `CLAUDE_CONFIG_DIR` tells Claude Code CLI which directory to use as its config root.
- Each profile lives in `~/.claude-profiles/<name>/` with an isolated `claude.json`.
- Everything else (`skills/`, `projects/`, `hooks/`, `agents/`, `settings/`) is symlinked back to the main `~/.claude/` directory so you only maintain one copy.
- Provider routing is done via `~/.claude/settings/<name>.json`, which sets `ANTHROPIC_MODEL`, `ANTHROPIC_BASE_URL`, and `ANTHROPIC_AUTH_TOKEN` for that window.

## One-Click Setup Workflow

When the user says something like "set up Claude Code profiles" or "I want to use Kimi and DeepSeek in different windows":

1. **Check prerequisites**
   - `claude` CLI is installed: `which claude`
   - Shell is zsh or bash: detect via `$SHELL`
   - `python3` is available

2. **Install the profile manager scripts**
   - Copy `scripts/claude-profiles.sh` to `~/.config/claude-switch-models-setup/claude-profiles.sh`
   - Copy `scripts/fix-marketplace-paths.py` to `~/.config/claude-switch-models-setup/fix-marketplace-paths.py`
   - Make both executable

3. **Add shell integration**
   - Source the profile manager in `~/.zshrc` or `~/.bashrc`
   - Add aliases: `csk`, `csd`, `csg`, `css`, `cssp`
   - Tell the user to run `source ~/.zshrc` (or open a new terminal)

4. **Generate provider settings files**
   - For each provider the user wants, create `~/.claude/settings/<provider>.json`
   - Use the templates in `templates/` as a starting point
   - Prompt the user for their API key and base URL; **never hardcode defaults**
   - Include the required isolation flags:
     - `CLAUDE_CODE_SUBAGENT_MODEL` (same as `ANTHROPIC_MODEL`)
     - `ENABLE_TOOL_SEARCH: "false"`
     - `DISABLE_GROWTHBOOK: "1"`
     - `DISABLE_TELEMETRY: "1"`
     - `DISABLE_AUTOUPDATER: "1"`

5. **Initialize profile directories**
   - Run `claude-profiles-init`
   - This creates `~/.claude-profiles/<provider>/` with isolated `claude.json` and symlinks

6. **Verify isolation**
   - Run `claude-profiles-doctor`
   - Confirm each profile directory has `claude.json` and valid symlinks

7. **Show the user how to launch**
   - `csk` → Kimi window
   - `csd` → DeepSeek window
   - `csg` → GLM window
   - `css` → StepFun window
   - `cssp` → StepFun planning window
   - `claude` (no alias) → default Anthropic profile

## Manual Commands

After setup, the user can run:

```bash
claude-profiles-init          # Re-scan settings/*.json and create missing profiles
claude-profile <name>         # Launch a specific profile
claude-profiles-ls            # List profiles
claude-profiles-doctor        # Check symlink health
claude-profile-rm <name>      # Remove a profile's isolation directory
```

## Provider Templates

Templates live in `templates/`:

- `kimi.json`
- `glm.json`
- `deepseek.json`
- `stepfun.json`
- `anthropic.json`

Each template has placeholders for `<API_KEY>` and `<BASE_URL>`. Ask the user for real values; do not guess or reuse values from the current machine unless the user explicitly provides them.

### Common base URLs (verify with your provider)

| Provider | Typical base URL |
|----------|------------------|
| Kimi     | `https://api.moonshot.cn` or OpenRouter-compatible endpoint |
| GLM      | `https://open.bigmodel.cn/api/paas/v4` or OpenRouter-compatible endpoint |
| DeepSeek | `https://api.deepseek.com` or OpenRouter-compatible endpoint |
| StepFun  | `https://api.stepfun.com` or OpenRouter-compatible endpoint |
| Anthropic| `https://api.anthropic.com` |

**Important:** The exact endpoint depends on whether the user is calling the provider directly or through a compatibility gateway (e.g., OpenRouter). Always ask.

## Shared vs. Isolated

| Data | Location | Shared? |
|------|----------|---------|
| Session history | `~/.claude-profiles/<name>/.claude.json` | **Isolated per profile** |
| Auth tokens/cache | `~/.claude-profiles/<name>/.claude.json` | **Isolated per profile** |
| Skills/plugins | `~/.claude/skills/`, `~/.claude/plugins/` | Shared via symlink |
| Projects/memory | `~/.claude/projects/`, `~/.claude/memory/` | Shared via symlink |
| Hooks/commands | `~/.claude/hooks/`, `~/.claude/commands/` | Shared via symlink |
| Provider settings | `~/.claude/settings/<name>.json` | Shared source, loaded per profile |

## Troubleshooting

### Marketplace paths break after plugin update

Symptom: A profile loads plugins from the wrong directory.
Fix: `fix-marketplace-paths.py` runs automatically at `claude-profile` launch. To run manually:

```bash
python3 ~/.config/claude-switch-models-setup/fix-marketplace-paths.py
```

### Third-party profile tries to use Anthropic-specific features

Symptom: WebSearch or other Anthropic-native tools fail with 400 errors.
Fix: Ensure the profile's `settings.json` sets:

```json
{
  "env": {
    "ENABLE_TOOL_SEARCH": "false",
    "DISABLE_GROWTHBOOK": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_AUTOUPDATER": "1"
  }
}
```

### Subagent calls fall back to a different model

Symptom: Subagents inside a Kimi window call `claude-opus-4-7`.
Fix: Set `CLAUDE_CODE_SUBAGENT_MODEL` to the same value as `ANTHROPIC_MODEL` in the profile's `settings.json`.

## Adding a New Provider Later

1. Create `~/.claude/settings/<new-provider>.json` using a template.
2. Run `claude-profiles-init`.
3. Add an alias to the shell rc file if desired.

## Security Notes

- API keys are written to `~/.claude/settings/<provider>.json` in plain text, the same way Claude Code stores `ANTHROPIC_AUTH_TOKEN`. This matches Claude Code's own security model.
- This skill never uploads keys or settings anywhere.
- For public distribution, the bundled scripts contain no hardcoded secrets, endpoints, or user-specific paths.

## Next Step

After setup, the user can immediately test by opening two terminals and running `csk` in one and `csd` in the other. Each window is independent.
