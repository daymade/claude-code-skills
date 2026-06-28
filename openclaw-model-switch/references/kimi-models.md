# Kimi Model Reference for OpenClaw

Reference data for configuring Kimi models in OpenClaw.

## Supported Models

### kimi-k2.7-code (Current Flagship)
- **id**: `kimi-k2.7-code`
- **Context Window**: 262,144 tokens
- **Max Output Tokens**: 32,768
- **Reasoning**: Enabled (`thinkingDefault: high` recommended)
- **Input Modalities**: text, image
- **Use Case**: Code generation, complex reasoning, long-context tasks

### k2p6 (Legacy / Previous)
- **id**: `k2p6`
- **Context Window**: 201,072 tokens
- **Max Output Tokens**: 32,768
- **Reasoning**: Enabled
- **Input Modalities**: text, image
- **Use Case**: General tasks, fallback option

## Provider Configuration (kimi-coding)

```json
{
  "baseUrl": "https://agent-gw.kimi.com/coding",
  "api": "anthropic-messages",
  "headers": {
    "User-Agent": "Desktop Kimi Claw Plugin",
    "X-Kimi-Claw-ID": "<your-claw-id>"
  }
}
```

## Configuration Snippets

### Adding a model definition

```json
{
  "id": "kimi-k2.7-code",
  "name": "kimi-k2.7-code",
  "reasoning": true,
  "input": ["text", "image"],
  "contextWindow": 262144,
  "maxTokens": 32768,
  "headers": {
    "User-Agent": "Desktop Kimi Claw Plugin",
    "X-Kimi-Claw-ID": "<your-claw-id>"
  }
}
```

### Setting default model

```json
{
  "agents": {
    "defaults": {
      "model": {
        "primary": "kimi-coding/kimi-k2.7-code"
      },
      "models": {
        "kimi-coding/kimi-k2.7-code": {}
      }
    }
  }
}
```

## Model ID Formats

OpenClaw uses `provider/model-id` format for model references:
- `kimi-coding/kimi-k2.7-code`
- `kimi-coding/k2p6`

The segment before `/` must match the provider key in `models.providers`.

## Troubleshooting

### Changes not taking effect
- Ensure gateway was restarted after config change
- Check `openclaw.json` syntax is valid JSON
- Verify model ID exactly matches provider's expected value (case-sensitive)

### Model not found errors
- Confirm the model definition exists in `models.providers.kimi-coding.models`
- Both `id` and `name` fields should match the requested model ID

### Gateway restart issues
- `openclaw gateway restart` requires CLI to be in PATH
- Alternative: restart Kimi desktop application
- On macOS: Quit Kimi app from Dock, then relaunch
