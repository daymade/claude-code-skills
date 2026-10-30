# Codex context-window contract

## Configuration authority

Codex reads `model_context_window` and `model_auto_compact_token_limit` from the
base `$CODEX_HOME/config.toml`. Both fields are part of Codex's public config schema
and app-server config contract:

- <https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json>
- <https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/config.rs>

Choose the operation, prerequisites and verification through the
[execution workflow](../SKILL.md#route-the-request).

## Model-aware calculations

The bundled [policy implementation](../scripts/codex_context_window.py) owns the
requested ceiling and expansion preset in its constants and `build_report`.
Use its runtime report for the selected model's limits and usable window; do not
persist another policy table or infer current capacity from the Skill name.

## Why a 1M request can display less

Codex clamps a configured context override to `max_context_window`:

<https://github.com/openai/codex/blob/main/codex-rs/models-manager/src/model_info.rs>

It then applies `effective_context_window_percent` before reporting/using the
session's usable hard limit. The reserved headroom covers system instructions,
tool overhead, and output:

<https://github.com/openai/codex/blob/main/codex-rs/core/src/session/turn_context.rs>

The Skill name does not promise the same usable capacity for every model.

## Auto-compaction behavior

Codex's runtime capping behavior is defined in its model contract:

<https://github.com/openai/codex/blob/main/codex-rs/protocol/src/openai_models.rs>

Context-window enforcement is defined separately:

<https://github.com/openai/codex/blob/main/codex-rs/core/src/session/context_window.rs>

A saved base-config threshold alone does not prove the resolved runtime value.

## Client and session boundaries

Writing the base config covers clients that consume the same Codex core config,
including CLI and Desktop. A shell alias only affects CLI launches, so this Skill
does not use aliases.

Profile config and per-command `-c` overrides can supersede the base values. The
Skill deliberately leaves those separate scopes untouched and reports only the base
config it verified.

Configuration is read when a session starts. Applying the Skill never changes the
context window of the thread that is already running.

## Verification evidence

For local-setting changes, exercise field-only readback, unrelated-byte preservation,
rollback/idempotency and the local config-load command. Do not require live catalog
access for those jobs. For expansion changes, exercise the documented expansion
commands against the current Codex binary and re-read the live catalog.
If the upstream fields or commands drift, update the implementation and this
reference together; do not add a compatibility fallback that guesses the old shape.
