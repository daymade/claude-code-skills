---
name: openclaw-model-switch
description: >-
  Switches or repairs an OpenClaw instance's model config: changes the default model, adds model
  definitions, and fixes 401 "Invalid token", "No available channel / model not found", "Thinking
  level X is not supported", or a config edit that doesn't take effect. Use for 切换模型/换模型/升级模型 or
  模型配的错了. Not for plain config audits (use openclaw).
---

# OpenClaw Model Switch

Switch or repair the model used by the running OpenClaw instance. Prefer its validated native
configuration commands; retain the bundled file tools for offline and older-version work.

**Diagnose before you edit.** Model failures on OpenClaw are usually NOT the model id —
they are key routing (env hijack), provider-plugin restrictions, or endpoint/model mismatch.
Changing the model id without checking these first is how a 5-minute fix becomes a 2-hour
debugging session. The full trap catalog with discovery commands lives in
[references/troubleshooting-model-config.md](references/troubleshooting-model-config.md) — read it
the moment anything errors.

## Step 1 — Find the real config file(s)

Do NOT assume a hardcoded path. Candidate locations (check all, edit all that exist):

1. `~/.openclaw/openclaw.json` — the gateway's live config on most installs
2. `~/.kimi/kimi-claw/openclaw.json` — Kimi Claw mirror, kept in sync on some installs
3. `~/.kimi_openclaw/openclaw.json` — legacy desktop path

Confirm which one the gateway actually reads with `openclaw gateway status` (or its JSON
config paths). Select that installation's profile/config context before issuing commands.
If several files exist, verify which are maintained mirrors and keep those in sync;
existence alone does not prove they belong to the same instance. Reconcile an Ansible or
other deployment source too when it owns the default, so the next deployment preserves it.

## Step 2 — Probe the endpoint + model BEFORE touching config

Never trust a relay's model listing (`GET /v1/models` on new-api style relays is frequently
incomplete — a model can be absent from the list yet serve fine). The only authority is a
real completion probe **from the host that will run the bot**:

Match the Gateway's effective credential and proxy route. An SSH login shell can inherit a
dead proxy that the Gateway does not use; record that difference before interpreting a failed
probe. Do not print keys or dump the process's full environment. Use the exact model variant
requested by the user and verify its input modes, context/output limits and supported thinking
settings from the provider's current documentation; do not infer them from the family name.

```bash
curl -sS -o /tmp/probe.json -w "HTTP %{http_code}\n" \
  -X POST "<baseUrl>/v1/messages" \
  -H "Authorization: Bearer <apiKey>" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"<model-id>","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}'
```

Expected: `HTTP 200` and a `content` array in the body. `401 Invalid token` with a token you
just verified works elsewhere → the wire key is being hijacked (see trap #1 in the
troubleshooting reference). `503 No available channel` → the model is not served for this
token/group **from this network** (trap #3) — pick a served model or fix the relay, don't
blind-switch.

## Step 3 — Switch the model

Read `openclaw config set --help` on the selected installation. On versions supporting batch
writes, prepare a private JSON batch containing the model definition and default assignment:

```json
[
  {"path":"models.providers.example.models","value":[{"id":"target-model","name":"Target model"}]},
  {"path":"agents.defaults.model.primary","value":"example/target-model"}
]
```

Replace `example` with the existing provider id and `target-model` with the verified served
model. Fill the definition's reasoning, input and token limits from the verified model spec;
include `agents.defaults.thinkingDefault` only when the target requires a compatible change.
Preserve credentials, headers, plugins and unrelated model entries. Back up the active config
privately before applying the batch; do not commit either credentials or the live config.

```bash
openclaw config set --batch-file ./model-batch.json --merge --dry-run
openclaw config set --batch-file ./model-batch.json --merge
```

Use `--merge` to retain existing model definitions; use replacement only for an explicitly
authorized removal. Follow the CLI's application hint: hot reload, no change, or required
restart. The hint describes expected application, so complete Step 4 even after a hot-reload
hint. Restart only when required, after checking service ownership, in-flight work and recovery.
See [native configuration commands](https://docs.openclaw.ai/cli/config).

### Offline tools and older versions

Retain these helpers for exported/stopped configurations or a verified older CLI without the
native write interface. Back up the selected files and preserve maintained mirrors. A live
older-version repair must respect the same service and in-flight-work checks; `--restart`
is an explicit option, not the default completion step. This helper has no dry-run mode;
inspect a private exported copy first when the proposed file edits need a preview.
The legacy helper only supplies definitions for its known-model table and rewrites same-provider
entries in `agents.defaults.models`. For other targets, complete the verified definition and
restore any existing allowlist parameters in the offline candidate before adopting it. Use
explicit `--config` when discovery would include unverified mirrors; inspect the complete diff.

```bash
python3 scripts/switch-model.py <model-id>
# target a specific provider instead of the guessed one:
python3 scripts/switch-model.py k3 --provider kimi-relay
# explicit config path (skips discovery):
python3 scripts/switch-model.py k3 --config ~/.openclaw/openclaw.json
```

The script: discovers and backs up every candidate config to `<config-dir>/config-backups/`,
adds the model definition if known, sets `agents.defaults.model.primary`, syncs mirror
files, and restarts the gateway with `--restart`.

## Step 4 — Verify end-to-end (mandatory)

A local/isolated turn is a provider precheck. For the live switch, run a new session through
the Gateway without `--local` and without a `--model` override, then read the result metadata:

```bash
openclaw agent --json --agent main --session-id verify-$(date +%s) -m "Reply with a short verification marker."
```

Require a successful command, a visible reply and the requested model in the actual execution.
For 2026.11.1, inspect `result.meta.agentMeta.terminalReceipt`: `requested.model`,
`effective.model` and `effective.responseModel` must match the intended variant, and `rerouted`
must be false. Also require `result.meta.executionTrace.fallbackUsed=false`. A successful
reply rescued by fallback does not validate the requested model. On older schemas, use the
equivalent execution metadata and Gateway logs; missing identity evidence remains unverified.

Report the tested boundary precisely. A Gateway turn does not test channel ingress or delivery.
If delivery is part of the request, use an authorized target and inspect its send receipt;
claim an inbound channel round trip only after observing a new message on that channel.

## Common failures → read the troubleshooting reference

| Symptom | Most likely trap |
|---|---|
| `LLM error new_api_error: Invalid token`, but the token works in curl | Trap #1 — env `KIMI_API_KEY` hijacks the provider's wire key |
| `Thinking level "max" is not supported ... Use one of: off, on` | Trap #2 — kimi-provider plugin hardcodes binary thinking; bypass with a custom provider |
| `Thinking level ... Use one of: off, minimal, low, medium, high` | Trap #2 variant — anthropic-messages base profile; unlock via `params.canonicalModelId` |
| `503 No available channel for model X under group default` | Trap #3 — model not served for this group/network; listing ≠ availability |
| Edit saved + gateway restarted, nothing changed | Trap #5 — edited the wrong file / mirror not synced |

## Safety rules

- **Always backup** before editing (the script does this; manual edits: copy to `config-backups/` first)
- **Preserve** existing `apiKey`, `headers`, plugin configs, and `env` blocks — retype only the fields you mean to change
- **Validate JSON** after manual edits: `python3 -m json.tool openclaw.json > /dev/null`
- **Do not** commit config files containing API keys to version control
- If verification fails, preserve its result and reconcile or restore the owned config through
  the matching native interface. Restore an offline file backup only to its verified stopped
  owner; do not overwrite a running managed store or newer concurrent changes.

## Resources

- **scripts/switch-model.py** — model switcher with config discovery, backup, mirror sync, and restart
- **references/kimi-models.md** — known model specs (k3, k2p6, kimi-k2.7-code) and config snippets
- **references/troubleshooting-model-config.md** — the trap catalog: env key hijack, plugin binary thinking, canonicalModelId, relay availability, config discovery. Read on any error.
