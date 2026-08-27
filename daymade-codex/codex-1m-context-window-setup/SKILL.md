---
name: codex-1m-context-window-setup
description: >-
  Configures and verifies an expanded, model-aware context window for OpenAI
  Codex CLI and Codex Desktop by safely updating the shared base config. Use
  whenever Codex shows about 258K context, the user asks for 500K or 1M context,
  auto-compaction happens too often, model_context_window or
  model_auto_compact_token_limit needs repair, or a workstation/classroom needs
  the same long-context setup across macOS and Windows. Detects the selected
  model's live maximum, requests up to 1M tokens, sets compaction to 60% of the
  attainable window, preserves unrelated TOML, backs up changes, and fails
  rather than guessing when the model contract cannot be verified.
argument-hint: "[doctor|apply|verify]"
---

# Codex 1m Context Window Setup

Expand future Codex sessions without pretending every model supports one million
tokens. The bundled script reads Codex's current model catalog, caps the request at
the selected model's declared maximum, and applies the user's established 60%
auto-compaction policy.

## Route the request

| User intent | Action |
|---|---|
| Inspect the current limit, explain 258K, or preview the recommendation | Run `doctor` |
| Configure/fix/raise the context window | Run `apply` |
| Confirm a prior setup is still correct after an update or model switch | Run `verify` |

Do not ask the user for raw token numbers. The model catalog is the authority and
the script derives the attainable values.

## Run the workflow

When this Skill loads, the host exposes its installed path. Resolve it explicitly:

- In Codex, take the directory containing `SKILL.md` from this Skill's `file:`
  entry in the current **Available skills** catalog.
- In Claude Code, use the **Base directory for this skill** shown by the Skill
  load result.

Do not search a home directory for another copy. If the host did not expose an
installed path, stop with `installed Skill path not exposed` rather than guessing.

On macOS/Linux, set that exact directory and run:

```bash
SKILL_DIR="/absolute/path/from-the-loaded-skill-metadata"
uv run --no-project python "$SKILL_DIR/scripts/codex_context_window.py" doctor
uv run --no-project python "$SKILL_DIR/scripts/codex_context_window.py" apply
uv run --no-project python "$SKILL_DIR/scripts/codex_context_window.py" verify
```

On Windows PowerShell, use the same exposed directory with forward slashes:

```powershell
$SkillDir = "C:/absolute/path/from-the-loaded-skill-metadata"
uv run --no-project python "$SkillDir/scripts/codex_context_window.py" doctor
uv run --no-project python "$SkillDir/scripts/codex_context_window.py" apply
uv run --no-project python "$SkillDir/scripts/codex_context_window.py" verify
```

### `doctor`

Run first. It is read-only and reports:

- selected model resolved by Codex;
- catalog default, model maximum, and usable percentage;
- requested raw window (up to 1,000,000), usable window, and 60% compaction point;
- current base-config values and whether `apply` is needed;
- exact `$CODEX_HOME/config.toml` target.

If Codex cannot return a live model catalog, stop. Do not substitute remembered
model limits, API marketing numbers, or a bundled default.

### `apply`

Run only after `doctor` succeeds. The script:

1. Re-reads the live model contract.
2. Changes only the top-level `model_context_window` and
   `model_auto_compact_token_limit` keys.
3. Creates a content-addressed backup only when bytes will change.
4. Uses an atomic same-directory replace and refuses to overwrite a concurrently
   changed config.
5. Runs Codex strict-config diagnostics; a failure restores the exact prior bytes.
6. Reads the written file back and reports the values that future sessions will use.

Existing sessions do not grow in place. After success, tell the user to start a new
CLI thread or restart/open a new Codex Desktop thread.

### `verify`

Run after Codex upgrades, default-model changes, or on a newly configured machine.
It exits non-zero when the current base config no longer equals the model-aware
recommendation. Report the mismatch; do not call it configured.

## Report the outcome

Copy exact values from script output. Include:

- model slug;
- configured raw window;
- usable window shown to the session;
- automatic compaction threshold;
- whether the model capped the 1M request;
- config and backup paths;
- `restart_required: true` after a changed apply.

## Refuse scope expansion

This Skill does not:

- change the selected model, reasoning effort, service tier, sandbox, approvals,
  plugins, MCP servers, browser/computer-use settings, or shell aliases;
- edit profile-specific config files or override per-command `-c` flags;
- claim the current running thread was expanded;
- force 1M when the selected model declares a smaller maximum;
- fall back to stale or guessed model metadata.

Read [references/context_window_contract.md](references/context_window_contract.md)
when diagnosing model caps, the 95% usable-window display, or compaction semantics.
