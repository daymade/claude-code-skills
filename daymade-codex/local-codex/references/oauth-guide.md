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

### Bind the credential store before changing it
- Resolve the actual `CODEX_HOME`, credential-store configuration, and CLI entry on the target. The examples below assume the file-backed default `~/.codex/auth.json`; use Codex's supported login flow for another store instead of exporting a keychain.
- The desktop app and CLI can share the same store. A logout can affect both; do not log out merely to inspect an account.
- Treat copying a cache as an explicitly authorized transfer of a verified login, not as an account archive. Copies can become stale, and refresh tokens can rotate. Do not concurrently refresh copied credentials or repeatedly reinstall an old copy after authentication fails.

### Check existing sessions separately
- Long-lived processes can retain stale in-memory authentication. Verify the affected build and process; a changed login file and a successful new process do not establish whether an existing session adopted the account. Keep untested sessions `not_checked` rather than declaring that every session switched or must restart.
- A token-refresh error establishes an authentication failure for that request, not that signing in on another machine always revokes every login. Group runtime errors by process before attributing repeated messages to independent failures.
- If an existing process is confirmed stale while a new process works, preserve its conversation and coordinate an authorized restart/resume. Do not terminate other sessions or services to complete a login check. Use bare `codex resume` (interactive picker) in the same directory after the owner releases the process. A rollout/session id for `codex resume <id>` does **not** come from the logs DB (its `thread_id` is usually NULL or logs-only); verify it in `state_*.sqlite` `threads` using cwd and creation time. Re-login only when the target's current credentials also fail.
- To find which processes are affected, query the runtime log (pick the `logs_*.sqlite` with the latest mtime, as the command below does; measured 2026-10-03):

```bash
DB=$(ls -t ~/.codex/logs_*.sqlite | head -1)
sqlite3 "$DB" "
SELECT process_uuid, COUNT(*), datetime(MIN(ts),'unixepoch','localtime') first_seen
FROM logs WHERE feedback_log_body LIKE '%could not be refreshed%'
GROUP BY process_uuid ORDER BY 2 DESC;"
# process_uuid is pid:<pid>:<uuid> — investigate those processes; this is not permission to stop them
```

### Headless / Automation notes
- For automation on a machine with a browser: use `codex login` normally
- For a remote host, follow the account-switch workflow below: reuse an authorized valid cache, or use `codex login --device-auth` with a browser on another machine.
- For CI/CD: OpenAI recommends API keys, but for ChatGPT Pro subscription access, use the cached auth pattern

## Remote account switch and expired-login recovery

Bind the approved target host, target user/home, expected account, and authorization before writing. Keep machine addresses and real account values in the owner's configuration, not this guide.

1. **Resolve the entry the user actually runs.** Inspect the target through its login shell, including wrappers and process-scoped network configuration. On macOS, an approved SSH alias can run `/bin/zsh -lic 'command -v codex; codex --version'`. Do not assume a Homebrew path or call a native package binary when the normal entry supplies its network environment. Use the existing remote/network owner if the authenticated command plane fails.
2. **Separate identity, validity, and quota.** Cached email/plan metadata and `codex login status` locate a login; neither proves its refresh token works or that quota remains. If the target already has the expected account and a fresh request succeeds, keep that valid login and finish without replacing it or requesting another authorization. Distinguish an authentication rejection such as `invalid_refresh_token`, a quota rejection, and a transport failure. Stop repeating the same invalid credential. Stop only task-owned probes when their terminal authentication failure is already established.
3. **Preserve the previous login before mutation.** For a file-backed store, create an exact private backup in a directory with mode `0700`, keep the file `0600`, and independently verify its bytes. Preserve the target's config, history and sessions. Never print tokens, put them in command arguments, or copy a whole home directory.
4. **Reuse only an authorized, verified source login.** Confirm its account and current authenticated behavior; a readable old cache alone is insufficient. Transfer it privately, check identity and transfer integrity, then atomically install it with mode `0600`. If verification refreshes the source, use the resulting current credentials rather than the earlier bytes. On failure or timeout, inspect the target before retrying; do not launch a dependent validation until installation is confirmed. If the credentials are rejected, continue with device authorization when that recovery is authorized; do not cycle through unrelated accounts.
5. **Run device authorization on the target when needed.** Keep `codex login --device-auth` running through the same resolved CLI entry and retain its process handle, displayed URL, current code, and expiry. The login request authorizes completing that named account flow; it does not authorize another account, changed device policy, or broader privileges.
6. **Complete the browser half with the existing controller.** Use an available, authorized browser automation owner (`ego-browser` when installed). Otherwise use an existing approved controller or hand off the same authorization page for the human-only step; do not install a browser or extract cookies as an implicit prerequisite. Open the URL emitted by the target CLI, confirm the expected email before continuing, and enter only the code from that still-running CLI. Inspect the current visible form, including separately rendered code-character inputs. Wait for visible input or completion state, not merely the presence of a hidden input. Treat MFA, disabled device authorization, an expired code, or a different account as an explicit recovery condition; do not retry the old code or approve a different account. For expiry, first confirm/cancel the task-owned old attempt, then obtain a new code.
7. **Confirm the target received the login.** Browser success alone is insufficient. Read the CLI to its successful terminal exit, then independently read the target store's account identity, freshness and permissions without exposing credential values. A lost CLI receipt or failed token exchange remains unresolved even if the browser shows success.
8. **Verify usable subscription access and report its scope.** Run the no-op below through the same ordinary entry and home, confirm the expected account remains selected, and require exit `0`, the `OK` response, and `turn.completed`. Keep existing-process adoption separate. Finish the browser controller's task and read task-owned probes to terminal state; preserve other users' sessions.

## Verification

```bash
# Run on the intended target through its normal CLI entry and credential home.
codex exec --skip-git-repo-check --ephemeral --sandbox read-only --json \
  'Reply only OK. Do not use tools.'
```

Use a bounded task-owned process and inspect its actual terminal result. Do not retry a known authentication rejection until credentials change. A successful request proves access at that time, not a full remaining quota or adoption by already-running sessions. See [OpenAI authentication documentation](https://developers.openai.com/codex/auth/) for the supported login/cache mechanisms.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Not authenticated" or missing cache | Use the authorized local or remote login branch for the selected store |
| Expired access token with a valid refresh token | Let Codex refresh through the actual target entry; verify the resulting account and request |
| `invalid_refresh_token` or another terminal refresh rejection | Stop repeating that cache; use authorized device-code recovery on a remote host |
| Desktop app logged in but CLI not | Compare home, store and executable first; do not blindly log out a shared store |
| Quota rejection | Report the selected account's quota condition; switch only to the account the user authorized |
| Only existing sessions fail while a fresh process works | Investigate those processes and coordinate any necessary restart/resume; do not infer global revocation or stop other sessions |
