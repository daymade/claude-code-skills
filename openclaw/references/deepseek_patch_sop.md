# SOP — Add DeepSeek V4 Pro 1M to an OpenClaw instance

This document describes the canonical way to add the `deepseek-v4-pro` model to
an OpenClaw config. The actual model definition is stored in
`deepseek_model.json` next to this file and is loaded by the `add-model`
subcommand.

## Supported path

Use the internal gateway provider with the model id `deepseek-v4-pro`. Do **not**
create a separate `deepseek*` provider.

## Why this matters

- The model id **must not contain `[1m]`**. Use the suffixless
  `deepseek-v4-pro`. The upstream gateway maps this to the 1M context variant.
- Adding a new provider usually requires a cold restart of the OpenClaw gateway.
  Hot reload may show the model in `openclaw models list` but still reject
  `/model` commands.

## Model definition source

`add-model` can copy `deepseek-v4-pro` from a source config via `--from`, or it
can load the canonical definition from `references/deepseek_model.json`:

```bash
python3 scripts/cli.py add-model gateway-provider references/deepseek_model.json \
  --config PATH --alias "DeepSeek V4 Pro"
```

## Typical workflow

1. Run `audit` on the target config.
2. Run `add-model gateway-provider deepseek-v4-pro --config PATH --from KNOWN_GOOD_PATH`
   to copy the gateway provider if it is missing and ensure the DeepSeek model
   and alias exist.
3. Run `audit` again to confirm no structural errors.
4. Run `switch gateway-provider/deepseek-v4-pro --config PATH --restart` to make
   it the default model and restart the gateway.

## What not to do

- Do not add a `deepseek*` provider pointing directly at the DeepSeek API.
- Do not write the API key into the target config unless it comes from a
  known-good source config via `copy` or `add-model --from`.
- Do not rely on hot reload after adding a brand-new provider.
