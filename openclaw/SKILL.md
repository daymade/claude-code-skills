---
name: openclaw
description: >-
  Manage OpenClaw (龙虾) instance configurations. Use whenever the user wants
  to audit, diff, copy, add-model, list, or switch models in an openclaw.json
  file, or when they mention lobsters, 虾, 甲虾, 乙虾, DeepSeek patch,
  default model, model aliases, or OpenClaw config validation.
argument-hint: '[audit|diff|copy|add-model|list|switch] [options]'
---

# openclaw

A unified skill for managing OpenClaw (龙虾) instance configs.

## Subcommands

```bash
python3 scripts/cli.py [audit|diff|copy|add-model|list|switch] [options]
```

Each subcommand can also be run directly, e.g. `python3 scripts/audit.py ...`.

`diff` is an alias for `compare`.

## Shared behavior

- **Default config discovery**: when `--config` / `--to` is omitted, the skill
  searches these locations in order:
  1. `~/workspace/.force/openclaw/openclaw.json`
  2. `~/.kimi_openclaw/openclaw.json`
  3. `~/.openclaw/openclaw.json`
- **Lobster nicknames**: `--config`, `--from`, and `--to` can be either a file
  path or a nickname registered in `lobsters.json` (see below). You can also use
  `--from-lobster` and `--to-lobster` for explicit nickname arguments.
- **Backups**: every write operation copies the config to
  `config-backups/<stem>-<utc-timestamp>.json` before saving. The skill keeps
  the 20 most recent backups.
- **Dry run**: write subcommands (`copy`, `add-model`, `switch`) support
  `--dry-run` to preview changes.
- **Restart**: write subcommands support `--restart` to restart the OpenClaw
  gateway after saving.
- **Automatic audit**: `copy`, `add-model`, and `switch` run an audit before and
  after the change by default. Use `--no-audit` to skip it.

## Lobster nickname registry

Create a JSON file at one of these locations:

- `~/workspace/.force/openclaw/lobsters.json`
- `~/.kimi_openclaw/lobsters.json`
- `~/.openclaw/lobsters.json`

Example:

```json
{
  "甲虾": "/path/to/甲虾/openclaw.json",
  "乙虾": "/path/to/乙虾/openclaw.json"
}
```

Then use:

```bash
python3 scripts/cli.py copy gateway-provider --from 甲虾 --to 乙虾 --alias
python3 scripts/cli.py switch gateway-provider/deepseek-v4-pro --config 乙虾 --restart
```

---

## `audit` — validate a config

```bash
python3 scripts/cli.py audit [--config PATH|NICKNAME] [--json]
```

Checks providers, models, default model, aliases, and plugin consistency.

Use when:

- "帮我查一下这只虾的配置"
- "audit 一下 openclaw.json"
- Before applying a patch or copying a provider

---

## `diff` — semantic diff of two configs

```bash
python3 scripts/cli.py diff LEFT.json RIGHT.json [--json] [--include-cost]
```

Reports added/removed/changed providers, models, default model, aliases, and
plugins. Skips cost fields by default; use `--include-cost` to diff them.

Use when:

- "为什么甲虾能用 DeepSeek，乙虾不行？"
- "这两份龙虾配置哪里不一样？"

---

## `copy` — copy a provider between configs

```bash
python3 scripts/cli.py copy \
  --from SOURCE|NICKNAME [--to TARGET|NICKNAME] \
  provider-name [--model ID]... [--alias] [--restart] [--dry-run] [--no-audit]
```

Copies an entire provider from one config to another. If the target already has
that provider, it merges models and updates `baseUrl` / `api` without deleting
target-only models. `--alias` also copies aliases pointing to that provider.

Use when:

- "把甲虾的 gateway provider 复制到乙虾"
- "把这个模型配置同步过去"

---

## `add-model` — add a model to a provider

```bash
python3 scripts/cli.py add-model provider model-id|model-json \
  [--config PATH|NICKNAME] [--from SOURCE|NICKNAME] [--alias NAME] \
  [--restart] [--dry-run] [--no-audit]
```

Adds a model definition and alias to a provider. If the provider is missing, it
can be copied from `--from` first.

Ways to specify the model:

- Pass a model id and `--from SOURCE` containing that model in the same provider.
- Pass a path to a JSON file with the model definition.

Use when:

- "给这只虾加上 DeepSeek"
- "把甲虾的 DeepSeek 配置复制到乙虾"

The canonical DeepSeek model definition lives in
`references/deepseek_model.json`.

### Critical pitfalls

- **Do not create a separate `deepseek` provider.** The supported path is the
  gateway provider with model id `deepseek-v4-pro`.
- **Model id must not contain `[1m]`.** Use the suffixless `deepseek-v4-pro`;
  the upstream gateway maps it to the 1M context variant.
- **Cold restart required.** New providers are not reliably picked up by hot
  reload.

---

## `list` — list providers, models, aliases, and default

```bash
python3 scripts/cli.py list [--config PATH|NICKNAME] [--json] [--validate]
```

Human-readable output by default; `--json` for piping to `jq`. Add `--validate`
to check that the default model and aliases resolve.

Use when:

- "这只虾有哪些模型？"
- "列出甲虾可用的模型"
- "看看默认模型是什么"

---

## `switch` — change the default model

```bash
python3 scripts/cli.py switch provider/model-id \
  [--config PATH|NICKNAME] [--restart] [--dry-run] [--no-audit]
```

This is the only subcommand that changes `agents.defaults.model`. It verifies
that the provider and model exist, backs up the config, and updates the default.
If the target is already the default, it exits without making another backup.

Use when:

- "把默认模型切成 DeepSeek"
- "切回原来的模型"

---

## Typical workflows

### Enable DeepSeek on a lobster

```bash
python3 scripts/cli.py audit --config 乙虾
python3 scripts/cli.py add-model gateway-provider deepseek-v4-pro \
  --config 乙虾 --from 甲虾 --alias "DeepSeek V4 Pro"
python3 scripts/cli.py switch gateway-provider/deepseek-v4-pro --config 乙虾 --restart
```

### Clone a working config to a new lobster

```bash
python3 scripts/cli.py copy gateway-provider --from 甲虾 --to 乙虾 --alias --restart
python3 scripts/cli.py audit --config 乙虾
```

### Diff two lobsters

```bash
python3 scripts/cli.py diff 甲虾 乙虾
```

## References

- `references/openclaw_architecture.md` — config schema and terminology
- `references/deepseek_patch_sop.md` — DeepSeek patch SOP (sanitized)
- `references/deepseek_model.json` — canonical DeepSeek model definition loaded
  by `add-model`
- `references/lobster_registry.example.json` — example lobster nickname registry
