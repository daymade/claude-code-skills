---
name: codex-1m-context-window-setup
description: >-
  Configures and verifies an expanded, model-aware context window for OpenAI Codex CLI and Desktop.
  Use to inspect local context settings, lower or set the auto-compaction threshold, expand
  ~258K context to 500K or 1M, or repair model_context_window/model_auto_compact_token_limit.
  Not for changing the selected model or other Codex settings.
argument-hint: "[show|set-compact --tokens N|doctor|apply|verify]"
---

# Codex 1m Context Window Setup

Inspect local settings or change only automatic compaction. For full context
expansion, read Codex's current model catalog, cap the request at the model's
declared maximum, and apply the bundled expansion preset.

## Route the request

| User intent | Action |
|---|---|
| Read the current base-config window or compaction threshold | Run `show`; no Codex process or model catalog needed |
| Lower/set only automatic compaction | Run `show`, then `set-compact --tokens N` |
| Explain 258K, diagnose model limits, or preview full expansion | Run `doctor` |
| Configure/fix/raise the context window | Run `apply` |
| Confirm a prior setup is still correct after an update or model switch | Run `verify` |

Honor a user-specified threshold exactly. If the user only asks for a small
reduction, choose and state a modest reversible reduction from the observed value.
For expansion, derive attainable values from the live catalog instead of asking
the user for model limits. Running `apply` selects the full expansion preset and
replaces a custom threshold; do it only when full setup is requested.

For local reads/edits, start with the bundled commands. Do not dump config.toml,
load unrelated machine manuals, or run network/model diagnostics. Consult official
OpenAI documentation when parameter semantics or compatibility are unresolved;
it cannot establish this machine's current value. Respect host output restrictions;
if numeric output is denied, use its supported field-condition probe and keep an
unread value unknown. Do not reconstruct denied values through repeated comparisons.

## Prerequisites

Use Python 3.11+ for the script's `tomllib` dependency and uv for the documented
launcher. `show` needs no Codex executable. `set-compact` requires a Codex CLI
supporting `features list`; full expansion additionally requires `doctor --json`,
`debug models` and strict-config diagnostics. Missing expansion support does not
prevent a local read. Do not substitute another config root or guessed model data
when a required command is unavailable.

## Run the workflow

Run the bundled [configuration script](scripts/codex_context_window.py).

When this Skill loads, the host exposes its installed path. Resolve it explicitly:

- In Codex, take the directory containing `SKILL.md` from this Skill's `file:`
  entry in the current **Available skills** catalog.
- In Claude Code, use the **Base directory for this skill** shown by the Skill
  load result.

Do not search a home directory for another copy. If the host did not expose an
installed path, stop with `installed Skill path not exposed` rather than guessing.

On macOS/Linux, set that exact directory:

```bash
SKILL_DIR="/absolute/path/from-the-loaded-skill-metadata"
```

On Windows PowerShell, use the same exposed directory with forward slashes:

```powershell
$SkillDir = "C:/absolute/path/from-the-loaded-skill-metadata"
```

Execute only the branch selected under **Route the request**. In the commands
below, PowerShell users substitute `$SkillDir` for `$SKILL_DIR`.

### `show` and `set-compact`

Use the same resolved script path on either platform:

```bash
uv run --no-project python "$SKILL_DIR/scripts/codex_context_window.py" show --json
uv run --no-project python "$SKILL_DIR/scripts/codex_context_window.py" set-compact --tokens 400000 --json
uv run --no-project python "$SKILL_DIR/scripts/codex_context_window.py" show --json
```

Choose `--tokens` from the current request, not this example. `show` emits only
the numeric settings, the config path and evidence status; a missing value is null,
not a guessed default.
It does not inspect profile or command-line overrides.

`set-compact` preserves the context-window setting, profiles, comments and existing
formatting; inserting a missing key may add a separating newline. It rejects
nonpositive/out-of-range tokens and thresholds
above an explicitly configured window. When the window is absent, leave it absent;
model-derived runtime caps remain unverified. Before a changed write, back up the
original and check for concurrent edits. Write atomically, run the local
`codex features list` configuration-load check with captured output, and read back
the target. Restore the original on validation failure unless a concurrent edit
makes that unsafe. A no-op creates no backup. Do not echo diagnostic bodies that
may contain unrelated configuration. Use `show` afterward as independent readback.

### `doctor`

Run first for full expansion or model-cap diagnosis:

```bash
uv run --no-project python "$SKILL_DIR/scripts/codex_context_window.py" doctor --json
```

It is read-only and reports:

- selected model resolved by Codex;
- catalog default, model maximum, and usable percentage;
- recommended raw window, usable window, and preset compaction point;
- current base-config values and whether `apply` is needed;
- exact `$CODEX_HOME/config.toml` target.

If Codex cannot return a live model catalog, stop the expansion path. Do not
substitute remembered model limits, API marketing numbers, or a bundled default.
Local `show`/`set-compact` remain independent of catalog availability.

### `apply`

Run only after `doctor` succeeds:

```bash
uv run --no-project python "$SKILL_DIR/scripts/codex_context_window.py" apply --json
```

The script:

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
expansion preset. A deliberate custom threshold can differ from that preset; this
is not proof that the saved threshold is invalid. Use `show` for its current base value.

```bash
uv run --no-project python "$SKILL_DIR/scripts/codex_context_window.py" verify --json
```

## Report the outcome

For a threshold-only change, report previous → saved tokens, backup path when
changed, local configuration-load result and independent readback. Keep
`session_adoption: unverified` until the actual consumer supplies evidence. Ask
the user to start a new CLI thread or restart/open a new Desktop thread that reads
this base config; do not claim the running thread changed. Profile and `-c`
overrides can still supersede it.

For expansion, copy exact values from script output. Include:

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
when diagnosing model caps, usable-window display, or compaction semantics.
