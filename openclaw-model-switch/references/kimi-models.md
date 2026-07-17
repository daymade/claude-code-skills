# Kimi Model Reference for OpenClaw

Reference data for configuring Kimi models in OpenClaw.

**Availability caveat:** never decide "model X exists on endpoint Y" from a
`GET /v1/models` listing — on new-api style relays it is frequently incomplete.
Probe with a real completion call from the target host instead (see SKILL.md Step 2).

## Supported Models

### k3 (Current Flagship)
- **id**: `k3`
- **Context Window**: 1,048,576 tokens
- **Max Output Tokens**: 32,768
- **Reasoning**: Enabled
- **Input Modalities**: text, image
- **Note**: extended-context variants (e.g. `[1m]` suffixed ids) may exist on a relay
  but be group/network restricted — probe before relying on them.

### kimi-k2.7-code
- **id**: `kimi-k2.7-code`
- **Context Window**: 262,144 tokens
- **Max Output Tokens**: 32,768
- **Reasoning**: Enabled (`thinkingDefault: high` recommended)
- **Input Modalities**: text, image
- **Use Case**: Code generation, complex reasoning, long-context tasks

### k2p6 (Legacy / Fallback)
- **id**: `k2p6`
- **Context Window**: 201,072 tokens
- **Max Output Tokens**: 32,768
- **Reasoning**: Enabled
- **Input Modalities**: text, image
- **Use Case**: General tasks, fallback option

## Provider Configuration (official Kimi endpoint)

```json
{
  "baseUrl": "https://agent-gw.kimi.com/coding",
  "api": "anthropic-messages",
  "headers": {
    "User-Agent": "Kimi Claw Plugin",
    "X-Kimi-Claw-ID": "<your-claw-id>"
  }
}
```

Custom/relay endpoints work the same way — set `baseUrl` to the relay root and use the
relay's token. Beware: for providers the built-in secrets registry maps (e.g.
`kimi-coding` ← env `KIMI_API_KEY`), a non-empty env var beats `provider.apiKey` on the
wire. See [troubleshooting-model-config.md](troubleshooting-model-config.md) Trap 1.

## Configuration Snippets

### Adding a model definition

```json
{
  "id": "k3",
  "name": "k3",
  "reasoning": true,
  "input": ["text", "image"],
  "contextWindow": 1048576,
  "maxTokens": 32768
}
```

Optional field for unlocking extended thinking levels on anthropic-messages providers:

```json
"params": { "canonicalModelId": "claude-opus-4-7" }
```

This makes the anthropic-messages thinking profile include xhigh/adaptive/max; the wire
payload for those levels becomes `thinking:{type:"adaptive"}` +
`output_config:{effort:"<level>"}` — probe that exact payload before enabling
(see troubleshooting Trap 2, variant B).

### Setting default model

```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "kimi-coding/k3"
      },
      "models": {
        "kimi-coding/k3": {}
      }
    }
  }
}
```

## Model ID Formats

OpenClaw uses `provider/model-id` format for model references:
- `kimi-coding/k3`
- `kimi-coding/k2p6`

The segment before `/` must match the provider key in `models.providers`.

## Troubleshooting

The full trap catalog (env key hijack, plugin binary thinking, relay availability,
config discovery) is in [troubleshooting-model-config.md](troubleshooting-model-config.md).

### Changes not taking effect
- Ensure gateway was restarted after config change (and a NEW pid exists)
- Check `openclaw.json` syntax is valid JSON
- Verify you edited the file the gateway actually reads (`openclaw gateway status`)

### Model not found errors
- Confirm the model definition exists in `models.providers.<provider>.models`
- Both `id` and `name` fields should match the requested model ID (case-sensitive)
- Confirm the endpoint actually serves the model — POST probe, not `/v1/models`

### Gateway restart issues
- `openclaw gateway restart` requires CLI to be in PATH
- Alternative: restart the systemd user service / desktop app
