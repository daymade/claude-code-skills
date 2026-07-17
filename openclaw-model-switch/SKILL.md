---
name: openclaw-model-switch
description: >-
  Switch or repair the model configuration of an OpenClaw instance (e.g. Kimi k2p6 → k3):
  change the default model, add model definitions, and fix model-config failures — 401
  "Invalid token", "No available channel / model not found", thinking-level rejections
  ("Thinking level X is not supported"), and config edits that don't take effect.
  Use whenever the user wants to switch/upgrade/rollback the OpenClaw model (切换模型/换模型/
  升级模型), or says the OpenClaw/龙虾 bot's model is misconfigured (模型配的错了),
  or the bot falls back / errors on LLM calls.
---

# OpenClaw Model Switch

Switch or repair an OpenClaw instance's model configuration by safely editing `openclaw.json`.

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

Confirm which one the gateway actually reads: `openclaw gateway status` prints
`Config (service): <path>`. If several exist, treat them as mirrors: **edit all of them
identically**, otherwise the next sync overwrites your fix.

## Step 2 — Probe the endpoint + model BEFORE touching config

Never trust a relay's model listing (`GET /v1/models` on new-api style relays is frequently
incomplete — a model can be absent from the list yet serve fine). The only authority is a
real completion probe **from the host that will run the bot**:

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

```bash
python3 scripts/switch-model.py <model-id> --restart
# target a specific provider instead of the guessed one:
python3 scripts/switch-model.py k3 --provider kimi-relay --restart
# explicit config path (skips discovery):
python3 scripts/switch-model.py k3 --config ~/.openclaw/openclaw.json --restart
```

The script: discovers and backs up every candidate config to `<config-dir>/config-backups/`,
adds the model definition if known, sets `agents.defaults.model.primary`, syncs mirror
files, and restarts the gateway with `--restart`.

## Step 4 — Verify end-to-end (mandatory)

A restarted gateway proves nothing. Run one real agent turn and read the result metadata:

```bash
openclaw agent --local --json --agent main --session-id verify-$(date +%s) -m "ping"
```

Success looks like: `"result": "success"`, `"fallbackUsed": false`, and the gateway log shows
`agent model: <provider>/<model> (thinking=...)`. `"result": "success"` with
`fallbackUsed: true` means your target failed and a fallback saved the turn — the config is
still wrong.

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
- After changing anything, redo the Step-4 verification — and if it fails, restore the newest backup before trying something else

## Resources

- **scripts/switch-model.py** — model switcher with config discovery, backup, mirror sync, and restart
- **references/kimi-models.md** — known model specs (k3, k2p6, kimi-k2.7-code) and config snippets
- **references/troubleshooting-model-config.md** — the trap catalog: env key hijack, plugin binary thinking, canonicalModelId, relay availability, config discovery. Read on any error.
