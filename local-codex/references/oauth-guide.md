# OAuth Authentication Guide for Local Codex

This skill uses **ChatGPT Pro OAuth** (not API keys) for authentication. This means:

- Usage counts against your **ChatGPT Pro $200/month subscription** (flat rate)
- **No per-token API charges** — this is the key benefit
- Requires the Codex desktop app or CLI to be logged in via `codex login`

## How Authentication Works

1. The Codex desktop app or CLI runs `codex login` and completes browser OAuth
2. Tokens are cached in `~/.codex/auth.json`
3. Both the desktop app and CLI share this auth cache
4. Codex automatically refreshes tokens when they expire (single-use refresh tokens)

## Important Constraints

### Do NOT use API Key mode
- Do NOT set `OPENAI_API_KEY` environment variable
- Do NOT pass `-c api_key=...` to codex exec
- Do NOT create `.codex/config.toml` with an API key
- Any of these would switch to **pay-per-use API billing** instead of flat-rate ChatGPT Pro

### Auth.json is shared
- The desktop app and CLI share `~/.codex/auth.json`
- If you `codex logout` from either, both lose auth
- Codex auto-refreshes tokens — don't copy `auth.json` elsewhere (copies become stale)

### Headless / Automation notes
- For automation on a machine with a browser: use `codex login` normally
- For headless servers: copy `auth.json` from a logged-in machine, or use device code flow (`codex login --device-auth`)
- For CI/CD: OpenAI recommends API keys, but for ChatGPT Pro subscription access, use the cached auth pattern

## Verification

```bash
# Check auth status
codex exec --skip-git-repo-check "echo auth-test"

# If this works, OAuth is active
# If it asks you to login, run: codex login
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Not authenticated" | Run `codex login` in terminal, complete browser flow |
| Token expired | Codex auto-refreshes on next run; if fails, run `codex login` again |
| Desktop app logged in but CLI not | They share auth; try `codex logout` then `codex login` |
| `auth.json` missing | Run `codex login` to generate it |
