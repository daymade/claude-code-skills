---
name: claude-switch-models-setup
description: >-
  Set up and maintain multiple isolated Claude Code CLI profiles so students and
  power users can run different LLM providers (Kimi K3, Kimi K2.7 highspeed,
  MiniMax M3, MiniMax M2.7, GLM, DeepSeek, StepFun, Anthropic) in separate
  terminal windows at the same time.
  Use this skill whenever the user asks about multi-provider Claude setup,
  multiple Claude Code windows, switching models or the csk/csd/csg aliases,
  CLAUDE_CONFIG_DIR, the ~/.claude-profiles directory, or running
  Kimi/MiniMax/GLM/DeepSeek/StepFun alongside Anthropic. It also owns profile-drift
  troubleshooting — a third-party profile missing skills/hooks/plugins the default
  profile has, claude-profiles-doctor reporting a real directory where a symlink
  belongs, or settings not converging — and per-provider context-window
  configuration (the [1m] marker or explicit CLAUDE_CODE_MAX_CONTEXT_TOKENS).
---

# Claude Code Multi-Provider Profiles

## Overview

This skill creates an isolated-but-shared profile system for Claude Code CLI. Each profile gets its own `.claude.json` state file (credentials and session history) while sharing skills, projects, hook scripts, agents, and installed plugin state across all profiles — and converging each profile's `settings.json` (hook registration, marketplaces, env feature flags, permissions, preferences) plus the **behavior slice of its `.claude.json`** (e.g. `workflowSizeGuideline`) from the default profile, so the only intended difference between profiles is the model/provider.

The result: you can open one terminal with Kimi, another with DeepSeek, another with Anthropic — each running as a fully independent Claude Code process, without configuration bleed.

## How It Works

- `CLAUDE_CONFIG_DIR` tells Claude Code CLI which directory to use as its config root.
- Each profile lives in `~/.claude-profiles/<name>/` with an isolated `.claude.json`.
- Content directories (`skills/`, `projects/`, `hooks/`, `agents/`, `settings/`) are symlinked back to the main `~/.claude/` directory so you only maintain one copy. Note this shares hook **scripts**, not hook **registration** — registration lives in each profile's own `settings.json` (next bullet).
- **Config layer — `settings.json`:** each profile has its own `settings.json` (Claude Code treats it as config-dir-local), so everything stored there — hook registration, `extraKnownMarketplaces`, `enabledPlugins`, `env` feature flags, `permissions`, behavior preferences — silently drifts the moment it changes in the default profile (measured 2026-07-18: 9/9 real profiles had zero hook registrations). `sync-profile-settings.py` is the converger: registered as a SessionStart hook, it copies every key from the default profile's `settings.json` into the active profile's, except identity keys (top-level `model` and `advisorModel` — the latter is Anthropic-model routing a third-party endpoint can't serve; and env vars that carry provider routing or Anthropic-native isolation — `ANTHROPIC_*`, `CLAUDE_CODE_SUBAGENT_MODEL`, `ENABLE_TOOL_SEARCH`, `DISABLE_GROWTHBOOK/TELEMETRY/AUTOUPDATER` — which the provider settings file deliberately sets differently). Profile-only **top-level** keys are preserved; nested collections inside a key main also has (e.g. `permissions.allow`, `enabledPlugins`) converge wholesale to main's value, and any profile-only nested entries dropped that way are listed (count on write, detail under `--check`) so the loss is visible rather than silent. This is what makes "everything except the model works in every profile" actually hold.
- **State layer — `.claude.json` behavior keys:** `settings.json` is not the only per-profile config file. Claude Code also keeps a per-profile state file (the main profile's is `~/.claude.json`; each third-party profile's is `<profile>/.claude.json` — asymmetric paths, verified on disk), and a few **behavior** settings live only there (`workflowSizeGuideline`, notification/UI preferences). On 2026-08-17 `workflowSizeGuideline: small` existed only on the main profile and 10/11 third-party profiles had no copy — a Kimi session fanned one Dynamic Workflow out to 30+ agents with no size guidance in its system prompt. The same converger therefore also syncs an **allowlist of behavior keys** into each profile's `.claude.json`. The safety mechanism is a three-way classifier in the script, not a hand-maintained key list: allowlisted behavior keys sync; state/cache/counter/migration/credential keys (matched by name patterns) are never touched; anything unknown-and-different is **reported — one line per drifted key per run, until a human classifies it** (the tripwire that surfaces the next behavior key the day it appears). Writes are backup + atomic-replace; measured safe against a live harness rewriting the file (a marker key survived 30+ minutes of an active session). Applies next session — the harness reads this file at startup.
- **Exception — `plugins/`:** marketplace content and install state are shared, but each profile keeps its **own** `known_marketplaces.json`. Claude validates a marketplace's `installLocation` with `path.resolve()` (which does NOT resolve symlinks), so a single shared file would make every non-writing profile report "corrupted installLocation". `claude-plugins-sync.py` builds and maintains this per-profile structure.
- `claude-plugins-sync.py` also mirrors `enabledPlugins` from the default `~/.claude/settings.json` into each profile's `settings.json` (sharing cache files is not enough; Claude Code treats "enabled" state as config-dir-local). It runs at profile launch and reactively — the LaunchAgent in the next bullet re-runs it on every write to the default profile's `settings.json`, so `claude plugin enable`/`disable --scope user` typically propagates to every profile within seconds without a relaunch (verified 2026-08-22). The SessionStart converger above covers the same key as part of its whole-settings sync; `claude-plugins-sync.py` remains the owner of the per-profile `known_marketplaces.json` structure.
- Local source sync is automatic on maintainer machines, but **source inventory is not activation policy**. Claude plugin cache directories remain source-backed; Codex user Skills are selected explicitly by `~/.config/claude-switch-models-setup/codex-active-skills.json` and linked into the official user root `~/.agents/skills`. `~/.codex/skills/.system` remains Codex-owned; the repair pass never edits it. After every selected replacement link is verified, the pass creates or confirms only the optional `legacy_codex_compat_skills` subset as same-source links under legacy `~/.codex/skills`; other managed legacy links are reported for reviewed cleanup, never deleted by the background task.
  - The manifest is intentionally fail-fast: missing file, non-array or duplicate name lists, unknown name, a compatibility name absent from `active_skills`, or the same frontmatter name registered by two different source bundles aborts before root mutation. Explicit JSON `null` is malformed, not an empty compatibility choice. This prevents a Python dictionary or directory scan order from silently choosing the winner.
  - **Pitfalls with daemon-owned symlinks** (observed 2026-07): never hand-create a symlink over an existing daemon-owned entry. BSD `ln` can put the new link *inside* the target directory, leaving a self-referential stray. Change `active_skills` for normal activation; when a long-lived hook or process still holds an old `~/.codex/skills/<name>` path, add that already-active name to `legacy_codex_compat_skills`. Verify links with `readlink`, not `ls -la <link>`—`ls` follows the link and can make a failed replacement look successful.
  - Third-party bundles already installed under `~/.agents/skills` are outside that manifest's ownership. Do not add them to the source manifest or delete them merely to reduce Codex prompt load. Route “keep the bundle on disk but hide it from Codex” to `/daymade-skill:skill-governance`; `references/local-source-sync-architecture.md` records the ownership boundary without duplicating that workflow.
- Sync scripts use a shared cross-process lock. This is required because users often open several provider windows from tmux or multiple terminals at once; concurrent launches must serialize marketplace/cache rewrites while still allowing all profiles to start.
- For the full local-source architecture, read `references/local-source-sync-architecture.md` before changing these scripts.
- Provider routing is done via `~/.claude/settings/<name>.json`, which sets `ANTHROPIC_MODEL`, `ANTHROPIC_BASE_URL`, and `ANTHROPIC_AUTH_TOKEN` for that window.

## One-Click Setup Workflow

When the user says something like "set up Claude Code profiles" or "I want to use Kimi and DeepSeek in different windows":

1. **Check prerequisites**
   - `claude` CLI is installed: `which claude`
   - Shell is zsh or bash: detect via `$SHELL`
   - `python3` is available

2. **Install the profile manager scripts — symlink them, do not copy**

   On a machine that has this repo checked out (the maintainer case), run the
   bundled installer — it does exactly what the manual form below does:

   ```bash
   <absolute-path-to-this-repo>/daymade-claude-code/claude-switch-models-setup/scripts/setup.sh
   ```

   Or link them by hand. `REPO` **must be an absolute path**: with a relative
   one every command below still succeeds and exits 0, leaving dangling
   links that break `csk` and the LaunchAgent with no error to trace.

   ```bash
   REPO=<absolute-path-to-this-repo>/daymade-claude-code/claude-switch-models-setup
   DST=~/.config/claude-switch-models-setup
   mkdir -p "$DST"
   for f in scripts/claude-profiles.sh \
            scripts/claude-plugins-sync.py \
            scripts/sync-local-skill-sources.py \
            scripts/sync-local-skill-sources-daemon.sh \
            scripts/sync-profile-settings.py; do
     ln -sf "$REPO/$f" "$DST/$(basename "$f")"
   done
   python3 "$REPO/scripts/seed-codex-active-skills.py" \
     "$REPO/assets/templates/codex-active-skills.json" \
     "$DST/codex-active-skills.json"
   ```

   The deployed paths are spelled out rather than globbed so that reading this file
   tells you which scripts exist and where — `scripts/*.sh` would not. No
   `chmod` step: each listed script is committed executable, so setting the bit again
   would only dirty the checkout with mode changes that then ride into somebody
   else's commit.

   **Why symlinks and not `cp`:** `~/.config/…` is what actually runs — the
   LaunchAgent and `claude-profile` invoke scripts by that path — while this
   repo holds their source. Copies drift, and nothing about a deployed copy
   looks different from its source, so "am I editing the SSOT?" is not a
   judgement anyone reliably makes. Measured on one machine before the switch:
   a lock-placement fix sat in the repo for 26 days while the deployed copy kept
   running the bug it fixed, and two cleanup routines written straight into the
   deployed copy never reached version control at all — **drift in both
   directions, silently.** A link removes both, *for as long as it stays a
   link* — an atomic-save editor, an `rsync` or a stray `cp` turns one back into
   a real file without saying so, which is why this is worth re-checking rather
   than declaring solved. It also lets `sync-local-skill-sources.py` locate its
   own source repo by resolving its own path, instead of falling back to
   guessing.

   Worth re-checking how? Any periodic check works; there is none bundled with
   this skill. One line, run wherever you keep such things:

   ```bash
   for f in ~/.config/claude-switch-models-setup/*.py ~/.config/claude-switch-models-setup/*.sh; do
     [ -L "$f" ] && [ -e "$f" ] || echo "not a live link: $f"
   done
   ```

   If one has become a real file, **move it aside before re-linking** — it may
   hold edits that exist nowhere else, which is the whole problem being
   described: `mv "$f" "$f.local-edits" && ln -sf <source> "$f"`, then diff.

   On a machine **without** the repo, copy the scripts listed by the installer out of this skill
   bundle instead — and accept that repo fixes will not reach it until you copy
   again.

3. **Add shell integration**
   - Source the profile manager in `~/.zshrc` or `~/.bashrc`
   - Add aliases: `csk`, `csks`, `csd`, `csg`, `css`
   - Add any further per-account/per-plan variant alias by hand if needed —
     `claude-profiles.sh` only defines the aliases listed above
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
   - From then on every profile converges its `settings.json` and the behavior slice of its `.claude.json` from the default profile at each session start (changes apply next session). Audit without writing: `--check --all`

7. **Verify isolation**
   - Run `claude-profiles-doctor`
   - Confirm each profile directory has `.claude.json` and valid symlinks

8. **Select and install Codex user Skills for maintainers**
   - Skip this for normal students or users who do not edit the skill source repos
   - Edit `~/.config/claude-switch-models-setup/codex-active-skills.json`; list only the source Skills that should be globally visible to Codex. An empty list is an explicit choice to activate none.
   - If a still-running hook or process retains a legacy path, list that already-active Skill under `legacy_codex_compat_skills`; otherwise keep the compatibility list empty.
   - Run `sync-local-skill-sources.py --apply`. It creates/verifies selected `~/.agents/skills` links before creating or confirming explicit compatibility links and reporting other managed legacy links for reviewed `skill-governance` cleanup.
   - On a maintainer macOS machine, run `sync-local-skill-sources-daemon.sh --install`
   - This watches the activation manifest, default Claude install state, and local marketplace manifests, then repairs derived state after selection, install/uninstall, or plugin topology changes

9. **Show the user how to launch**
   - `csk` → Kimi K3 window
   - `csks` → Kimi K2.7 highspeed window
   - `csd` → DeepSeek window
   - `csg` → GLM window
   - `css` → StepFun window
   - `claude` (no alias) → default Anthropic profile
   - Optional: hand-add a per-account/per-plan variant alias yourself, e.g.
     `alias cssp='claude-profile step-pay --dangerously-skip-permissions'` —
     `claude-profiles.sh` does not generate this; it is a manual pattern on top

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
                               # Converge every profile from the default profile:
                               # settings.json (hooks, marketplaces, env flags,
                               # permissions, preferences) + .claude.json behavior
                               # keys (workflowSizeGuideline etc.); --check --all
                               # audits without writing
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --apply
                               # Maintainers: activate the explicit Codex user set in
                               # ~/.agents/skills; retain compat/report stale legacy links
~/.config/claude-switch-models-setup/sync-local-skill-sources-daemon.sh --install
                               # Maintainers: install automatic macOS watcher
```

These are not day-to-day commands. Normal source edits are live through symlinks. The one-shot commands are for repair, bootstrap, or non-macOS environments without the LaunchAgent watcher.

## Provider Templates

Templates live in `assets/templates/`:

- `minimax.json` — MiniMax-M3, global endpoint, 1M context, adaptive or disabled thinking
- `minimax-cn.json` — MiniMax-M3, China endpoint, 1M context, adaptive or disabled thinking
- `minimax-m2-7.json` — MiniMax-M2.7, global endpoint, 204800-token context, always-on thinking
- `minimax-m2-7-cn.json` — MiniMax-M2.7, China endpoint, 204800-token context, always-on thinking
- `kimi.json` — Kimi K3 (1M context via the `[1m]` marker — see "Configuring Context Window Size" below)
- `kimi-highspeed.json` — Kimi K2.7 highspeed (legacy 200K context)
- `glm.json`
- `deepseek.json`
- `stepfun.json`
- `anthropic.json`

Every template uses the `<API_KEY>` placeholder. Templates for configurable gateways also use `<BASE_URL>`; the MiniMax templates pin the documented regional endpoint. Ask the user for every real placeholder value; do not guess or reuse values from the current machine unless the user explicitly provides them.

### MiniMax model behavior

| Templates | Model | Context configuration | Thinking behavior |
|---|---|---|---|
| `minimax.json`, `minimax-cn.json` | `MiniMax-M3` | Append `[1m]` to every routed model value and set `CLAUDE_CODE_AUTO_COMPACT_WINDOW` to `1000000`. | Supports adaptive or disabled thinking. Keep `ANTHROPIC_REASONING_MODEL` on the same model. |
| `minimax-m2-7.json`, `minimax-m2-7-cn.json` | `MiniMax-M2.7` | Set `CLAUDE_CODE_MAX_CONTEXT_TOKENS` and `CLAUDE_CODE_AUTO_COMPACT_WINDOW` to `204800`; do not append `[1m]`. | Thinking is always on; do not claim a template-level disable path. |

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

The MiniMax-M3 templates use the same 1M marker plus an explicit `1000000` auto-compact value. The MiniMax-M2.7 templates use explicit `204800` limits with no marker.

The full step-2-16k template-correctness war-story (why an internally-consistent-looking context value is not the same as a currently-correct one — cross-check the model name against the provider's live docs, not just the numbers around it), plus a reusable recipe to verify whether any env var actually changes the bytes sent over the wire (a local `http.server` capture, since `--debug api` only shows internal state), live in `references/context-window-config.md`.

### Common base URLs (verify with your provider)

| Provider | Typical base URL |
|----------|------------------|
| Kimi     | `https://api.moonshot.cn` or OpenRouter-compatible endpoint |
| GLM      | `https://open.bigmodel.cn/api/paas/v4` or OpenRouter-compatible endpoint |
| DeepSeek | `https://api.deepseek.com` or OpenRouter-compatible endpoint |
| StepFun  | `https://api.stepfun.com` or OpenRouter-compatible endpoint |
| MiniMax  | Global: `https://api.minimax.io/anthropic`; China: `https://api.minimaxi.com/anthropic` |
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
| `.claude.json` behavior keys (`workflowSizeGuideline`, notification/UI preferences) | `~/.claude.json` → `<profile>/.claude.json` | **Behavior allowlist converged** by the same script; state/cache/counter/migration/credential keys (incl. `projects`, `oauthAccount`, `userID`) are never synced; unknown drifted keys are reported for human classification |
| Provider settings | `~/.claude/settings/<name>.json` | Shared source, loaded per profile |

## Troubleshooting

### A profile directory exists but claude-profiles-doctor reports it as an "orphan profile"

Symptom: `claude-profiles-doctor` reports
`WARN: orphan profile — no settings/<name>.json; claude-profile <name> fails. Run: claude-profile-rm <name>`.

Cause: the profile isolation directory exists under `~/.claude-profiles/` but
the corresponding `~/.claude/settings/<name>.json` provider config file is
missing. `claude-profiles-init` only scans `settings/*.json`, so an orphan
profile's symlinks are never created or maintained, and `claude-profile <name>`
will fail to launch with "Error: Settings file not found." The profile directory
may still contain useful per-profile data (`history.jsonl`, `.claude.json` with
provider credentials, `settings.json`, skill workspaces).

Fix:
- **If the profile is no longer needed**: `claude-profile-rm <name>` — this
  safely removes the isolation directory (it checks for unexpected files first).
- **If you want to revive it**: recreate the settings file at
  `~/.claude/settings/<name>.json` (use a provider template from
  `assets/templates/`), then run `claude-profiles-init`.

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

Expected design: normal edits to an installed Claude plugin or an explicitly selected Codex user Skill are live immediately because their runtime locations are symlinks. A source Skill that is absent from `codex-active-skills.json` is deliberately cold inventory, not sync drift. Existing Claude Code/Codex sessions may still need a restart because Skill metadata is loaded at session start.

If the edit is structural (new plugin, new skill entry, version bump, install/uninstall, or marketplace manifest change), the macOS LaunchAgent should run automatically. Check:

```bash
launchctl print gui/$(id -u)/ai.daymade.claude-skill-source-sync
```

Repair manually only if the watcher is not installed or you are on a non-macOS machine:

```bash
python3 ~/.config/claude-switch-models-setup/sync-local-skill-sources.py --apply
```

This first validates the explicit activation manifest and the complete source-name set. Every registered Skill carries its marketplace-repo containment and load-time inode into the freeze step, which rechecks both before binding one source path and inode for the whole pass. It captures the existing identities of both user roots before the mutable phase, then opens every remaining component with no-follow directory handles and refuses a root that disappeared, appeared, or changed inode before pinning. It links the selected entries into `~/.agents/skills`, verifies every selected target, and only afterward creates or confirms `legacy_codex_compat_skills` under `~/.codex/skills`; a final cross-root check reads both links between source pre/post identity checks. A missing root is created exclusively only when the selected policy needs it. At a selected `.agents` destination, an empty path or the correct link is accepted; a wrong link into a managed source repo moves to timestamped recovery storage, while a real object, relative/broken link, or third-party link fails visibly and remains in place. Stale unselected managed links move to the same recovery storage; malformed foreign links are skipped as unowned. The move itself is exclusive: if the classified entry changes first, the concurrent winner is restored at the original name and selected replacement fails (unselected pruning skips it); if a newer winner already occupies that name, neither is overwritten and the run fails with the earlier winner retained in recovery. At a requested legacy compatibility path, only an already-correct same-source link or an empty path is accepted; every other existing object fails visibly and is never replaced. Creation publishes a known private symlink inode with an atomic no-overwrite hard link, so any competing path before, during, or after publication fails closed—even if it points to the expected source. Other source-backed legacy links are logged for explicit, reviewed cleanup through `skill-governance`; the LaunchAgent never unlinks them.

It also cleans up after itself, which earlier versions did not:

- **Version-alias symlinks.** Each cache link is named after the marketplace's current version, so every version bump left the previous link behind pointing at the very same source directory. One plugin had six version directories, four of them aliases for one source. The pass now removes sibling links that resolve to the same source; real directories are never touched, since Claude Code installs those and a live session may still hold them through `.in_use`.
- **`installed_plugins.json` backups.** Every run that changes the JSON writes one, and nothing removed them — a month of runs left 453 files behind. The `KEEP_JSON_BACKUPS` constant in the script caps the retained set; the names end in a `YYYYMMDD-HHMMSS` stamp, so lexical order is chronological.

Both are visible in a dry run before `--apply` touches anything.

### A profile is missing hooks, marketplaces, env flags, or other default-profile settings

Symptom: the default profile has hook guards, marketplaces, or feature flags configured, but a third-party profile behaves as if they don't exist (no PreToolUse guards fire, `claude plugin marketplace list` is empty, a feature enabled in the default profile is off).

**Sibling symptom, different layer (2026-08-17):** a behavior preference set on the default profile — e.g. the workflow size guideline — has no effect in third-party profiles (a Kimi session fanned a Dynamic Workflow out to 30+ agents despite `small` being set on main). That key lives in the per-profile `.claude.json`, which symlinks and the settings.json sync both miss. See "Default-profile behavior settings don't reach third-party profiles" in `references/troubleshooting.md`.

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
