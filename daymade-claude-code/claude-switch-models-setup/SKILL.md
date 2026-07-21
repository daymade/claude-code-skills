---
name: claude-switch-models-setup
description: >-
  Set up and maintain multiple isolated Claude Code CLI profiles so students and
  power users can run different LLM providers (Kimi K3, Kimi K2.7 highspeed, GLM,
  DeepSeek, StepFun, Anthropic) in separate terminal windows at the same time.
  Use this skill whenever the user asks about multi-provider Claude setup,
  multiple Claude Code windows, switching models or the csk/csd/csg aliases,
  CLAUDE_CONFIG_DIR, the ~/.claude-profiles directory, or running
  Kimi/GLM/DeepSeek/StepFun alongside Anthropic. It also owns profile-drift
  troubleshooting — a third-party profile missing skills/hooks/plugins the default
  profile has, claude-profiles-doctor reporting a real directory where a symlink
  belongs, or settings not converging — and per-provider context-window
  configuration (the [1m] marker or explicit CLAUDE_CODE_MAX_CONTEXT_TOKENS).
---

# Claude Code Multi-Provider Profiles

## Overview

This skill creates an isolated-but-shared profile system for Claude Code CLI. Each profile gets its own `.claude.json` state file (credentials and session history) while sharing skills, projects, hook scripts, agents, and installed plugin state across all profiles — and converging each profile's `settings.json` (hook registration, marketplaces, env feature flags, permissions, preferences) from the default profile, so the only intended difference between profiles is the model/provider.

The result: you can open one terminal with Kimi, another with DeepSeek, another with Anthropic — each running as a fully independent Claude Code process, without configuration bleed.

## How It Works

- `CLAUDE_CONFIG_DIR` tells Claude Code CLI which directory to use as its config root.
- Each profile lives in `~/.claude-profiles/<name>/` with an isolated `.claude.json`.
- Content directories (`skills/`, `projects/`, `hooks/`, `agents/`, `settings/`) are symlinked back to the main `~/.claude/` directory so you only maintain one copy. Note this shares hook **scripts**, not hook **registration** — registration lives in each profile's own `settings.json` (next bullet).
- **Config layer — `settings.json`:** each profile has its own `settings.json` (Claude Code treats it as config-dir-local), so everything stored there — hook registration, `extraKnownMarketplaces`, `enabledPlugins`, `env` feature flags, `permissions`, behavior preferences — silently drifts the moment it changes in the default profile (measured 2026-07-18: 9/9 real profiles had zero hook registrations). `sync-profile-settings.py` is the converger: registered as a SessionStart hook, it copies every key from the default profile's `settings.json` into the active profile's, except identity keys (top-level `model`; and env vars that carry provider routing or Anthropic-native isolation — `ANTHROPIC_*`, `CLAUDE_CODE_SUBAGENT_MODEL`, `ENABLE_TOOL_SEARCH`, `DISABLE_GROWTHBOOK/TELEMETRY/AUTOUPDATER` — which the provider settings file deliberately sets differently). Profile-only keys are preserved; the sync never deletes. This is what makes "everything except the model works in every profile" actually hold.
- **Exception — `plugins/`:** marketplace content and install state are shared, but each profile keeps its **own** `known_marketplaces.json`. Claude validates a marketplace's `installLocation` with `path.resolve()` (which does NOT resolve symlinks), so a single shared file would make every non-writing profile report "corrupted installLocation". `claude-plugins-sync.py` builds and maintains this per-profile structure.
- `claude-plugins-sync.py` also mirrors `enabledPlugins` from the default `~/.claude/settings.json` into each profile's `settings.json` (sharing cache files is not enough; Claude Code treats "enabled" state as config-dir-local). The SessionStart converger above covers the same key as part of its whole-settings sync; `claude-plugins-sync.py` remains the owner of the per-profile `known_marketplaces.json` structure.
- Local source sync is automatic on maintainer machines. Installed Claude plugin cache directories and Codex/agents skill copies are symlinked to the source repos, so normal source edits are live immediately. `sync-local-skill-sources.py` is the idempotent repair primitive; `claude-profile` init/launch runs it automatically, and `sync-local-skill-sources-daemon.sh --install` installs a macOS LaunchAgent that watches default Claude install state plus local marketplace manifests for structural changes. When a skill is removed from a marketplace manifest, the same repair pass prunes only stale Codex/agents symlinks that point back into the managed source repos; it never deletes real skill directories.
- Sync scripts use a shared cross-process lock. This is required because users often open several provider windows from tmux or multiple terminals at once; concurrent launches must serialize marketplace/cache rewrites while still allowing all profiles to start.
- For the full local-source architecture, read `references/local-source-sync-architecture.md` before changing these scripts.
- Provider routing is done via `~/.claude/settings/<name>.json`, which sets `ANTHROPIC_MODEL`, `ANTHROPIC_BASE_URL`, and `ANTHROPIC_AUTH_TOKEN` for that window.

## One-Click Setup Workflow

When the user says something like "set up Claude Code profiles" or "I want to use Kimi and DeepSeek in different windows":

1. **Check prerequisites**
   - `claude` CLI is installed: `which claude`
   - Shell is zsh or bash: detect via `$SHELL`
   - `python3` is available

2. **Install the profile manager scripts**
   - Copy `scripts/claude-profiles.sh` to `~/.config/claude-switch-models-setup/claude-profiles.sh`
   - Copy `scripts/claude-plugins-sync.py` to `~/.config/claude-switch-models-setup/claude-plugins-sync.py`
   - Copy `scripts/sync-local-skill-sources.py` to `~/.config/claude-switch-models-setup/sync-local-skill-sources.py`
   - Copy `scripts/sync-local-skill-sources-daemon.sh` to `~/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh`
   - Copy `scripts/sync-profile-settings.py` to `~/.config/claude-switch-models-setup/sync-profile-settings.py`
   - Make all five executable

3. **Add shell integration**
   - Source the profile manager in `~/.zshrc` or `~/.bashrc`
   - Add aliases: `csk`, `csks`, `csd`, `csg`, `css`, `cssp`
   - Tell the user to run `source ~/.zshrc` (or open a new terminal)

4. **Generate provider settings files**
   - For each provider the user wants, create `~/.claude/settings/<provider>.json`
   - Use the templates in `assets/templates/` as a starting point
   - Prompt the user for their API key and base URL; **never hardcode defaults**
   - Set the context window correctly for this specific provider — `[1m]` suffix vs explicit `CLAUDE_CODE_MAX_CONTEXT_TOKENS`/`CLAUDE_CODE_AUTO_COMPACT_WINDOW`, see "Configuring Context Window Size" below. Do this explicitly for every new profile rather than copying whatever the nearest template happens to already have — the nearest template not needing it is not evidence that this one doesn't either.
   - Include the required isolation flags:
     - `CLAUDE_CODE_SUBAGENT_MODEL` (same as `ANTHROPIC_MODEL`)
     - `ENABLE_TOOL_SEARCH: "false"`
     - `DISABLE_GROWTHBOOK: "1"`
     - `DISABLE_TELEMETRY: "1"`
     - `DISABLE_AUTOUPDATER: "1"`

5. **Initialize profile directories**
   - Run `claude-profiles-init`
   - This creates `~/.claude-profiles/<provider>/` with isolated `.claude.json` and symlinks
   - On maintainer machines, this also repairs local source symlinks before syncing plugin metadata

   **Statusline wiring:** `claude-profiles-init` auto-detects a statusline script from
   `~/.claude/settings.json` or `~/.claude/statusline.sh` and injects it into each new
   profile. If neither is present, profiles will work but without a status bar. **It is
   the AI's job** to decide whether the user needs a statusline, install the
   `statusline-generator` skill if appropriate, and run its installer — not the profile
   setup script. Do not hardcode dependency installs into shell scripts.

6. **Register the settings converger**
   - Add `~/.config/claude-switch-models-setup/sync-profile-settings.py` as a SessionStart hook in the **default** profile's `~/.claude/settings.json` `hooks.SessionStart` list (it no-ops when the active profile IS the default; its job there is to propagate into every profile's own `hooks` key on the first sync)
   - Run the initial alignment: `python3 ~/.config/claude-switch-models-setup/sync-profile-settings.py --all`
   - From then on every profile converges its `settings.json` from the default profile at each session start (changes apply next session). Audit without writing: `--check --all`

7. **Verify isolation**
   - Run `claude-profiles-doctor`
   - Confirm each profile directory has `.claude.json` and valid symlinks

8. **Install automatic local source sync for maintainers**
   - Skip this for normal students or users who do not edit the skill source repos
   - On a maintainer macOS machine, run `sync-local-skill-sources-daemon.sh --install`
   - This watches default Claude install state plus local marketplace manifests and repairs Claude/Codex installed copies automatically after install/uninstall or plugin topology changes

9. **Show the user how to launch**
   - `csk` → Kimi K3 window
   - `csks` → Kimi K2.7 highspeed window
   - `csd` → DeepSeek window
   - `csg` → GLM window
   - `css` → StepFun window
   - `cssp` → StepFun paid/account-specific window, when `step-pay.json` exists
   - `claude` (no alias) → default Anthropic profile

## Commands

After setup, the user can run:

```bash
claude-profiles-init          # Re-scan settings/*.json, create missing profiles;
                               # reports symlink drift (real dirs that should be symlinks).
                               # Add --repair to archive drift and replace with symlinks.
claude-profile <name>         # Launch a specific profile
claude-profiles-ls            # List profiles
claude-profiles-doctor        # Check symlink health
claude-profile-rm <name>      # Remove a profile's isolation directory
python3 ~/.config/claude-switch-models-setup/claude-plugins-sync.py
                               # Repair per-profile plugin structure and enabledPlugins
python3 ~/.config/claude-switch-models-setup/sync-profile-settings.py --all
                               # Converge every profile's settings.json from the default
                               # profile (hooks, marketplaces, env flags, permissions,
                               # preferences); --check --all audits without writing
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --apply
                               # Maintainers: one-shot repair for Claude/Codex source symlinks
~/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh --install
                               # Maintainers: install automatic macOS watcher
```

These are not day-to-day commands. Normal source edits are live through symlinks. The one-shot commands are for repair, bootstrap, or non-macOS environments without the LaunchAgent watcher.

## Provider Templates

Templates live in `assets/templates/`:

- `kimi.json` — Kimi K3 (1M context via the `[1m]` marker — see "Configuring Context Window Size" below)
- `kimi-highspeed.json` — Kimi K2.7 highspeed (legacy 200K context)
- `glm.json`
- `deepseek.json`
- `stepfun.json`
- `anthropic.json`

Each template has placeholders for `<API_KEY>` and `<BASE_URL>`. Ask the user for real values; do not guess or reuse values from the current machine unless the user explicitly provides them.

## Configuring Context Window Size

Every provider template sets the model's context window one of two ways — get this wrong and Claude Code doesn't know how much context the model can actually hold. Undershoot and it compacts (summarizes, drops old detail) far earlier than the provider actually requires; overshoot and it won't compact until the real limit is already blown past.

The full client-side mechanism of the `[1m]` marker — what it strips off the model
field, what it adds to the `anthropic-beta` header, and why a missing `[1m]` does
*not* mean the provider can't hold a big prompt — is documented in
`references/context-window-config.md`. Reach for it when a context number looks
wrong, not at template-writing time.

### Decision rule

When writing a new provider's `settings/<name>.json`, pick based on the provider's real, verified context window — not the model's marketing name, and not by copying whatever the nearest template happens to do:

| Provider's real context window | What to set | Example template |
|---|---|---|
| ~1M tokens, explicitly confirmed (not assumed from the model's tier/name) | `[1m]` suffix on every `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL` / `CLAUDE_CODE_SUBAGENT_MODEL` value. Must be the exact 4 characters `[1m]` — Claude Code matches this literal string, not a made-up marker like `[1million]` or `[max]`. | `kimi.json` |
| A known, smaller size (e.g. 200K) | Explicit `CLAUDE_CODE_MAX_CONTEXT_TOKENS` and/or `CLAUDE_CODE_AUTO_COMPACT_WINDOW` set to the real number — no `[1m]`. | `kimi-highspeed.json` (`200000`) |
| Unknown / not yet verified | Don't guess, and don't copy another provider's number just because a template needs *something* there. Ask the user to check the provider's own docs/console first. An unverified `[1m]` or an unverified large `CLAUDE_CODE_AUTO_COMPACT_WINDOW` just moves the failure from "compacts too early" to "doesn't compact until well past the real limit" — worse, because it's silent until a request actually fails. |

`deepseek.json` and `glm.json` set **both** `[1m]` and an explicit `CLAUDE_CODE_AUTO_COMPACT_WINDOW: "1000000"`. That's belt-and-suspenders, not redundant filler to strip out — the exact precedence between the marker and the explicit override hasn't been independently reverse-engineered, so if you're copying one of those two templates, keep both rather than dropping one.

The full step-2-16k template-correctness war-story (why an internally-consistent-looking context value is not the same as a currently-correct one — cross-check the model name against the provider's live docs, not just the numbers around it), plus a reusable recipe to verify whether any env var actually changes the bytes sent over the wire (a local `http.server` capture, since `--debug api` only shows internal state), live in `references/context-window-config.md`.

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
| Skills | `~/.claude/skills/` | Shared via symlink |
| Plugin content | `~/.claude/plugins/marketplaces`, `cache`, `data`, ... | Shared via symlink |
| Plugin install registry | `~/.claude/plugins/installed_plugins.json` | Shared via symlink |
| Enabled plugin map | `~/.claude/settings.json` -> `<profile>/settings.json` | Converged by `sync-profile-settings.py` (also mirrored by `claude-plugins-sync.py`) |
| Plugin marketplace index | `<profile>/plugins/known_marketplaces.json` | **Per-profile** (installLocation is config-dir-specific; can't be shared) |
| Projects/memory | `~/.claude/projects/`, `~/.claude/memory/` | Shared via symlink |
| Hook scripts | `~/.claude/hooks/`, `~/.claude/commands/` | Shared via symlink (scripts only — NOT registration) |
| `settings.json` config: hook registration, marketplaces, env flags, permissions, preferences | `<profile>/settings.json` | **Converged from default profile** by `sync-profile-settings.py` at session start (identity keys like `model` and provider-routing/isolation env vars are never synced) |
| Provider settings | `~/.claude/settings/<name>.json` | Shared source, loaded per profile |

## Troubleshooting

### A shared directory (skills/projects/hooks/agents/...) shows as a real directory, not a symlink

Symptom: `claude-profiles-doctor` reports
`<name> is a real directory (expected symlink to ~/.claude/<name>) — drift; run: claude-profiles-init --repair`.

Cause: the profile was created before the symlink-convergence design landed (or
was hand-created), so a shared content directory ended up as a real per-profile
directory instead of a symlink. That profile's copy now silently diverges from the
main `~/.claude/` copy — its skills/projects/hooks/agents are not the same as every
other profile's. The broken-symlink check cannot see this (a real directory is not
a broken link); on a real machine this drift went undetected for months until the
dedicated real-directory check was added (2026-07-21: legacy profiles created
before this check existed carried real `projects/` dirs for months, undetected).

Fix (reversible — data is archived, never deleted):

```bash
claude-profiles-init --repair
```

For each drifted directory this archives the real dir to
`<name>.pre-symlink-bak-<timestamp>` inside the profile directory, then creates the
symlink that should have been there. Run `claude-profiles-doctor` again to confirm
a clean bill. If an archive turns out to hold data you need, it is sitting right
there — nothing was destroyed.

Note on what gets shared: after repair, that directory points at the main
`~/.claude/<name>` copy, so the profile sees the same skills/projects/etc. as the
default profile — which is the entire point of the shared-symlink design. The
per-profile state that must stay isolated (`.claude.json`, `settings.json`
identity keys like `model`/provider env, `plugins/known_marketplaces.json`) is
never one of these symlinked dirs, so repair never touches it. Inspect the archive
before discarding it if the profile held session/history data you care about —
those would now resolve to the shared copy.

### Marketplace says "corrupted installLocation"

Symptom: `/plugin` or `claude plugin marketplace update` reports
`corrupted installLocation ... expected a path inside <config-dir>/plugins/marketplaces`.

Cause: `known_marketplaces.json` ended up shared across profiles (or hand-edited). Its
`installLocation` is config-dir-specific because Claude validates with `path.resolve()`
(symlinks NOT resolved), so one shared copy cannot satisfy multiple profiles.

Fix: `claude-plugins-sync.py` rebuilds each profile's own copy + the shared-content
symlinks. It runs automatically at `claude-profile` init/launch; to run manually:

```bash
python3 ~/.config/claude-switch-models-setup/claude-plugins-sync.py
```

### Skill exists in default Claude but is missing in Kimi/GLM/DeepSeek

Symptom: the default Anthropic profile can see a skill, but a third-party profile cannot.

Cause: Claude Code stores `enabledPlugins` in each config directory's `settings.json`.
Sharing `plugins/cache` only makes files available; it does not enable them.

Fix:

```bash
python3 ~/.config/claude-switch-models-setup/claude-plugins-sync.py
```

Then restart the affected Claude Code window.

### Local source edits do not show up in Claude Code or Codex

Symptom: you edit a skill in a local source repo, but Claude Code or Codex still loads an old installed copy.

Expected design: normal edits to existing source files are live immediately because the installed locations are symlinks. Existing Claude Code/Codex sessions may still need a restart because skill metadata is loaded at session start.

If the edit is structural (new plugin, new skill entry, version bump, install/uninstall, or marketplace manifest change), the macOS LaunchAgent should run automatically. Check:

```bash
launchctl print gui/$(id -u)/ai.daymade.claude-skill-source-sync
```

Repair manually only if the watcher is not installed or you are on a non-macOS machine:

```bash
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --apply
```

This moves existing real copies into timestamped `.source-sync-backups/` folders, replaces them with symlinks to the source repos, and prunes stale managed symlinks after a skill is removed from the manifest.

### A profile is missing hooks, marketplaces, env flags, or other default-profile settings

Symptom: the default profile has hook guards, marketplaces, or feature flags configured, but a third-party profile behaves as if they don't exist (no PreToolUse guards fire, `claude plugin marketplace list` is empty, a feature enabled in the default profile is off).

Cause: those live in each profile's own `settings.json`, which is config-dir-local — symlinking directories does not cover the config layer, and it drifts silently the moment the default profile changes.

Fix:

```bash
python3 ~/.config/claude-switch-models-setup/sync-profile-settings.py --all
```

Then restart the affected window. Once the converger is registered as a SessionStart hook (setup step 6), every profile self-converges at session start, so this should only be needed after a manual settings edit you want propagated immediately.

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

### A huge-context provider compacts/summarizes way too early, or the statusline context number looks wrong

Symptom: a provider whose own docs claim ~1M tokens of context gets auto-compacted by Claude Code well below that — long sessions get summarized when there's clearly no real need to yet, or the context percentage in the statusline tracks like it's looking at a ~200K model instead of the real ceiling.

Cause: the profile's `ANTHROPIC_MODEL` (and its `ANTHROPIC_DEFAULT_*_MODEL` / `CLAUDE_CODE_SUBAGENT_MODEL` siblings) is missing the `[1m]` marker. Claude Code has no other way to learn the provider's real context size — the request itself succeeding with a huge prompt doesn't tell Claude Code anything, since that's a property of the upstream provider, not of the client. See `references/context-window-config.md` for the full mechanism.

Fix: add the literal `[1m]` suffix to `ANTHROPIC_MODEL`, every `ANTHROPIC_DEFAULT_*_MODEL`, and `CLAUDE_CODE_SUBAGENT_MODEL` in the profile's `settings.json` (match `kimi.json`'s pattern). Restart the affected window.

## Adding a New Provider Later

1. Create `~/.claude/settings/<new-provider>.json` using a template.
2. Check the provider's real, verified context window and configure it — `[1m]` marker or explicit `CLAUDE_CODE_MAX_CONTEXT_TOKENS`/`CLAUDE_CODE_AUTO_COMPACT_WINDOW`, see "Configuring Context Window Size" below and `references/context-window-config.md`. Don't skip this because the template you copied from happened not to need it.
3. Run `claude-profiles-init`.
4. Add an alias to the shell rc file if desired.

## Security Notes

- API keys are written to `~/.claude/settings/<provider>.json` in plain text, the same way Claude Code stores `ANTHROPIC_AUTH_TOKEN`. This matches Claude Code's own security model.
- This skill never uploads keys or settings anywhere.
- For public distribution, the bundled scripts contain no hardcoded secrets, endpoints, or user-specific paths.

## Next Step

After setup, the user can immediately test by opening two terminals and running `csk` (Kimi K3) in one and `csd` in the other. Each window is independent.
