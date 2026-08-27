# Codex context-window contract

## Contents

- Configuration authority
- Model-aware calculations
- Why a 1M request can display less
- Auto-compaction behavior
- Client and session boundaries
- Verification evidence

## Configuration authority

Codex reads `model_context_window` and `model_auto_compact_token_limit` from the
base `$CODEX_HOME/config.toml`. Both fields are part of Codex's public config schema
and app-server config contract:

- <https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json>
- <https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/config.rs>

The script calls `codex doctor --json` to resolve the selected model and
`codex debug models` to retrieve the current catalog. The live catalog wins over
documentation and remembered limits.

## Model-aware calculations

The policy requests at most 1,000,000 raw tokens:

1. Read the selected model's `max_context_window`.
2. Use the smaller of that maximum and 1,000,000.
3. Multiply by the model's `effective_context_window_percent` to report the usable
   session window.
4. Set auto-compaction to 60% of the configured raw window.

The fixed 60% ratio is the user-approved operating policy. The attainable raw and
usable windows remain model facts and are discovered at runtime.

## Why a 1M request can display less

Codex clamps a configured context override to `max_context_window`:

<https://github.com/openai/codex/blob/main/codex-rs/models-manager/src/model_info.rs>

It then applies `effective_context_window_percent` before reporting/using the
session's usable hard limit. The reserved headroom covers system instructions,
tool overhead, and output:

<https://github.com/openai/codex/blob/main/codex-rs/core/src/session/turn_context.rs>

Therefore the Skill name describes the requested ceiling, not a promise that every
model exposes exactly one million usable tokens.

## Auto-compaction behavior

Codex normally caps an explicit auto-compaction threshold at 90% of the resolved raw
window. This Skill's 60% value remains below that guard:

<https://github.com/openai/codex/blob/main/codex-rs/protocol/src/openai_models.rs>

The full usable context window remains a hard cap independently of the compaction
threshold:

<https://github.com/openai/codex/blob/main/codex-rs/core/src/session/context_window.rs>

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

Last source-grounding pass: 2026-08-27 with `codex-cli 0.150.1`.

The release gate must exercise every documented command against the current Codex
binary, run deterministic rollback/idempotency tests, and re-read the live catalog.
If the upstream fields or commands drift, update the implementation and this
reference together; do not add a compatibility fallback that guesses the old shape.
