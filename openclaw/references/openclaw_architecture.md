# OpenClaw (龙虾) Config Architecture

OpenClaw stores its runtime configuration in a single JSON file, usually named
`openclaw.json`. This reference describes the parts of that file that the
`openclaw` skill touches.

## File locations

The skill looks for a config in this order when `--config` is not given:

1. `~/workspace/.force/openclaw/openclaw.json`
2. `~/.kimi_openclaw/openclaw.json`
3. `~/.openclaw/openclaw.json`

## Lobster nickname registry

You can register human nicknames for configs in `lobsters.json` at one of the
locations above. Example:

```json
{
  "lobster-a": "/path/to/lobster-a/openclaw.json",
  "lobster-b": "/path/to/lobster-b/openclaw.json"
}
```

Once registered, the nicknames can be used anywhere a config path is expected:
`--config`, `--from`, `--to`, and `diff` arguments.

## Top-level structure

```json
{
  "models": {
    "providers": {
      "provider-name": {
        "baseUrl": "https://...",
        "apiKey": "...",
        "api": "anthropic-messages",
        "models": [
          { "id": "model-id", "name": "...", ... }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": "provider-name/model-id",
      "models": {
        "provider-name/model-id": { "alias": "Display Name" }
      }
    }
  },
  "plugins": {
    "allow": ["plugin-a", "plugin-b"],
    "entries": {
      "plugin-a": { "enabled": true, ... }
    },
    "installs": {
      "plugin-a": { ... }
    }
  }
}
```

## Key concepts

- **Provider** — a gateway or upstream API endpoint. Each provider has a
  `baseUrl`, an `api` type, and a list of `models`.
- **Model** — a concrete model id exposed through a provider. The id must match
  what the gateway expects.
- **Alias** — a user-facing entry under `agents.defaults.models`. Aliases let
  users switch models with commands like `/model provider-name/model-id`.
- **Default model** — the model reference stored in `agents.defaults.model`.
  This is the model the lobster uses unless told otherwise.
- **Plugins** — OpenClaw extensions. The skill checks that `allow`, `entries`,
  and `installs` are consistent.

## Model reference format

Most commands use the form `provider-name/model-id`. Examples:

- `gateway-provider/deepseek-v4-pro`
- `gateway-provider/model-a`

## Internal names

In user conversations, "虾" or "龙虾" refers to an OpenClaw instance.
Examples include "甲虾" and "乙虾". These are just human nicknames for
separate config files or deployments.
