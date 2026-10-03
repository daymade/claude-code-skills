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

### Long-lived sessions keep a stale in-memory token
- A running Codex TUI reads `auth.json` once at startup and keeps the refresh token in memory; replacing `auth.json` does not reach already-running processes
- When the same account signs in elsewhere (web login, another machine, an account switch), the server revokes the old refresh token. Only the long-lived processes then start failing every ~30–70 s with `Failed to refresh token: ... you have since logged out or signed in to another account`. The error count is `processes × retry frequency` — hundreds of log lines can be one root cause
- Fix: quit the affected processes — they read the fresh `auth.json` at launch. To reopen the same conversation afterwards, run bare `codex resume` (interactive picker) in the same directory. The pid from the query below tells you *which process* to restart; a rollout/session id for `codex resume <id>` does **not** come from the logs DB (its `thread_id` is usually NULL or logs-only). When you need the exact id, match the process's cwd and start time against `state_*.sqlite` table `threads` (`cwd`, `created_at`). A global re-login is needed only if the current `auth.json` itself was revoked — i.e. new sessions fail too
- To find which processes are affected, query the runtime log (pick the `logs_*.sqlite` with the latest mtime, as the command below does; measured 2026-10-03):

```bash
DB=$(ls -t ~/.codex/logs_*.sqlite | head -1)
sqlite3 "$DB" "
SELECT process_uuid, COUNT(*), datetime(MIN(ts),'unixepoch','localtime') first_seen
FROM logs WHERE feedback_log_body LIKE '%could not be refreshed%'
GROUP BY process_uuid ORDER BY 2 DESC;"
# process_uuid is pid:<pid>:<uuid> — these pids are what to quit
```

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
| Only some long-running TUI sessions spam "Failed to refresh token … signed in to another account" after an account switch, while new sessions work | Those processes hold the revoked token in memory — quit and `codex resume` them (see "Long-lived sessions keep a stale in-memory token" above); do not re-login globally unless new sessions fail too |
