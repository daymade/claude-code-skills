# Student Setup Guide

This guide is for students who attended the workshop and want to replicate the multi-provider Claude Code setup on their own machine.

## What you will get

After following this guide you can:

- Open one terminal and run Claude Code with **Kimi**
- Open another terminal and run Claude Code with **DeepSeek**
- Open a third terminal and run Claude Code with **Anthropic**
- All windows work at the same time, independently

## Before you start

You need:

1. **Claude Code CLI installed** — if you can run `claude --version` and see a version number, you are good.
2. **A shell** — this guide supports `zsh` (default on macOS) and `bash`.
3. **Python 3** — usually pre-installed on macOS and most Linux distributions.
4. **API keys** for the providers you want to use. The skill will ask for these during setup.

## Quick start

Open a terminal and tell Claude Code:

```
Set up Claude Code profiles for Kimi and DeepSeek
```

Claude will walk you through the rest.

## What happens under the hood

If you prefer to understand before running, here is the full manual flow:

### 1. Install the profile manager

Copy these two files to `~/.config/claude-switch-models-setup/`:

- `claude-profiles.sh`
- `claude-plugins-sync.py`

### 2. Add to your shell config

Open `~/.zshrc` (or `~/.bashrc`) and add:

```bash
source ~/.config/claude-switch-models-setup/claude-profiles.sh

alias csk='claude-profile kimi'
alias csd='claude-profile deepseek'
alias csg='claude-profile glm'
alias css='claude-profile stepfun'
```

Then reload:

```bash
source ~/.zshrc
```

### 3. Create a provider settings file

For each provider, create `~/.claude/settings/<provider>.json`.

Example for Kimi:

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "your-kimi-api-key",
    "ANTHROPIC_BASE_URL": "https://api.moonshot.cn",
    "ANTHROPIC_MODEL": "kimi-k2.7-code",
    "CLAUDE_CODE_SUBAGENT_MODEL": "kimi-k2.7-code",
    "DISABLE_GROWTHBOOK": "1",
    "DISABLE_TELEMETRY": "1",
    "DISABLE_AUTOUPDATER": "1",
    "ENABLE_TOOL_SEARCH": "false"
  }
}
```

Ask your instructor or provider documentation for the exact `ANTHROPIC_BASE_URL` and model name.

### 4. Initialize profiles

```bash
claude-profiles-init
```

This creates `~/.claude-profiles/<provider>/` for each settings file.

### 5. Launch

```bash
csk   # Kimi window
csd   # DeepSeek window
```

## Common questions

### Do I need an Anthropic key?

No. You only need keys for the providers you want to use. The default `claude` command (no alias) still uses your normal Anthropic setup in `~/.claude/`.

### Can I use OpenRouter instead of direct provider APIs?

Yes. Set `ANTHROPIC_BASE_URL` to your OpenRouter endpoint and use the model IDs OpenRouter expects.

### What if a command says "command not found"?

Make sure you reloaded your shell config (`source ~/.zshrc`) or opened a new terminal after adding the `source` line.

### Is this safe? Will it delete my existing Claude setup?

No. The profile manager creates new directories and symlinks. It does not delete or modify your existing `~/.claude/` directory except to add new `settings/<provider>.json` files.

### I only want one extra provider, not five

Create only the settings file for the provider you want. The init command only creates profiles for files that exist in `~/.claude/settings/`.
