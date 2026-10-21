# OAuth Authentication Guide for Local Codex

Use **ChatGPT OAuth** through the supported Codex login flow. Keep this route separate from API-key billing, the selected account's allowance, and its extra Credit policy. Do not promise a fixed plan price or no extra Credit consumption.

## How Authentication Works

1. Resolve the actual CLI entry, `CODEX_HOME` and configured credential store.
2. Complete supported browser or device authorization in the fresh store described below; the default file store is `~/.codex/auth.json`.
3. Treat the desktop app and CLI as possible consumers of the same store. Separate directories do not create independent server-side grants.
4. Let only an authorized refresh owner use native authentication; token refresh can rotate credentials.

## Important Constraints

### Do NOT use API Key mode
- Do NOT set `OPENAI_API_KEY` environment variable
- Do NOT pass `-c api_key=...` to codex exec
- Do NOT create `.codex/config.toml` with an API key
- Keep API-key credentials out of this ChatGPT OAuth workflow; do not infer the account's extra Credit policy from the authentication route.

### Bind the credential store before changing it
- Resolve the actual `CODEX_HOME`, credential-store configuration, and CLI entry on the target. The examples below assume the file-backed default `~/.codex/auth.json`; use Codex's supported login flow for another store instead of exporting a keychain.
- The desktop app and CLI can share the same store. A logout can affect both; do not log out merely to inspect an account.
- Obtain independent grants for distinct cross-machine or cross-purpose auth roots. In inspected upstream 0.160/0.163 login paths, ordinary browser/device login calls `clear_existing_auth_before_login` → `logout_with_revoke` before OAuth. Do not seed a new login attempt with old credentials: it can revoke the grant still used elsewhere. Source order establishes this mechanism, not a captured production revoke request or its success.
- Preserve an explicitly authorized **TRANSFER** of a verified login as a separate single-owner recovery case. Confirm which source consumers will stop using the grant before the target takes ownership; the transfer does not authorize concurrent copying, refreshing or re-login against that grant. Do not repeatedly reinstall rejected credentials.
- Back up credential bytes for local recovery, but do not treat that backup as a way to reverse server-side revocation. Never use destructive logout as an account diagnostic.

### Bind refresh ownership before native queries
- Treat even a nominally read-only quota query as potentially refreshing credentials, including native workspace 401 recovery. File equality before/after a query and access-token expiry gating cannot enforce no server-side refresh.
- Before initializing a native client or quota collector, bind an authorized refresh-owning source. Reuse the project's deployed provider/query owner when present; use independently obtained grants for separate query and execution roots. If ownership is unknown, stop that native query rather than testing it against a copied grant.
- Keep cached identity, authentication, quota, process adoption and billing as separate facts. If the user requires no old-account Credit consumption, arrange already authorized fresh-account execution or handoff before long work and verify its actual account. Replacing the default file does not switch a running TUI.

### Check existing sessions separately
- Long-lived processes can retain stale in-memory authentication. Verify the affected build and process; a changed login file and a successful new process do not establish whether an existing session adopted the account. Keep untested sessions `not_checked` rather than declaring that every session switched or must restart.
- A token-refresh error establishes an authentication failure for that request, not that signing in on another machine always revokes every login. Group runtime errors by process before attributing repeated messages to independent failures.
- If an existing process is confirmed stale while a new process works, preserve its conversation and coordinate an authorized resume. For terminals managed by `ghostty-use`, use that owner's existing-session snapshot/restore workflow and verified session IDs. Otherwise use bare `codex resume` (interactive picker) in the same directory after the owner releases the process. A rollout/session id for `codex resume <id>` does **not** come from the logs DB (its `thread_id` is usually NULL or logs-only); verify it in `state_*.sqlite` `threads` using cwd and creation time. Do not kill terminals, stop other sessions or restart daemons for a login check; preserve active work and drafts. Re-login only when the target's current credentials also fail.
- To find which processes are affected, query the runtime log (pick the `logs_*.sqlite` with the latest mtime, as the command below does; measured 2026-10-03):

```bash
AUTH_ROOT="${CODEX_HOME:-$HOME/.codex}"
AUTH_LOG_DB=$(ls -t "$AUTH_ROOT"/logs_*.sqlite | head -1)
sqlite3 "$AUTH_LOG_DB" "
SELECT process_uuid, COUNT(*), datetime(MIN(ts),'unixepoch','localtime') first_seen
FROM logs WHERE feedback_log_body LIKE '%could not be refreshed%'
GROUP BY process_uuid ORDER BY 2 DESC;"
# process_uuid is pid:<pid>:<uuid> — investigate those processes; this is not permission to stop them
```

### Headless / Automation notes
- For local automation or a remote host, follow the workflow below: retain a valid authorized login, perform an explicit single-owner transfer, or obtain a fresh independent browser/device grant.
- Keep CI/CD authentication under its owning deployment policy. Do not silently substitute API-key billing for the requested ChatGPT access.

## Remote account switch and expired-login recovery

Bind the approved target host, target user/home, expected account, and authorization before writing. Resolve the current project's already-approved account, target and recovery restrictions from its authoritative entry. Prefer its deployed provider when that owner already implements login, protected installation and request reconciliation; do not create another OAuth client/helper or bypass its locks. A recipe here does not authorize an unapproved target or a fallback forbidden by the current user direction. Keep machine addresses, project entry locations and real accounts in the owner's configuration.

1. **Resolve the entry the user actually runs.** Inspect the target through its login shell, including wrappers and process-scoped network configuration. On macOS, an approved SSH alias can run `/bin/zsh -lic 'command -v codex; codex --version'`. Do not assume a Homebrew path or call a native package binary when the normal entry supplies its network environment. Use the existing remote/network owner if the authenticated command plane fails.
2. **Separate identity, validity, and quota.** Cached email/plan metadata and `codex login status` locate a login; neither proves its refresh token works or that quota remains. Bind refresh ownership before native initialization. If the target already has the expected account and a fresh authorized request succeeds, keep that valid login and finish without replacing it or requesting another authorization. Distinguish authentication rejection such as `invalid_refresh_token`, quota rejection and transport failure. Stop repeating invalid credentials; stop only task-owned probes whose terminal authentication failure is established.
3. **Preserve the target before mutation.** For a file-backed store, create an exact private backup in a directory with mode `0700`, keep the file `0600`, and independently verify its bytes. Preserve target config, history, sessions and Hooks. Never print tokens, put them in command arguments, or copy a whole home directory. A backup cannot undo server-side revocation.
4. **Choose independent login or explicit TRANSFER.** For distinct roots, obtain a fresh grant in step 5. Only for an authorized single-owner transfer, verify the source account and actual access, release its consumers without logout/re-login, transfer privately, and check identity and integrity. If verification refreshed the source, transfer the resulting current credentials. Continue at step 8; do not run login on the transferred grant. If rejected, use a fresh empty attempt for authorized recovery rather than recycling the cache.
5. **Start login in a fresh EMPTY auth store.** Create a task-owned `0700` attempt directory with no old auth; preserve only necessary CLI entry/network settings and applicable workspace restrictions. For file-backed login, bind both `CODEX_HOME` and `cli_auth_credentials_store="file"` explicitly so a new directory cannot silently select a shared keyring. Use the same resolved wrapper/network context and verify it honors that attempt binding. Run supported `codex login` or `codex login --device-auth` there, not over the live target. Retain the task-owned process/provider request handle, URL, current code and expiry. The request authorizes only the named account and scope; do not change device policy or privileges.

   For a verified empty file-store attempt, use the resolved entry in place of `codex`:

   ```bash
   CODEX_HOME="${AUTH_ATTEMPT_HOME:?Set the verified empty attempt directory}" \
     codex -c 'cli_auth_credentials_store="file"' login --device-auth
   # For supported browser login, omit --device-auth; retain both store bindings.
   ```

   For another store, require owner-verified isolation and supported installation; do not assume a new home isolates a keyring or export one.

6. **Complete the browser half with the existing controller.** Use an available, authorized browser automation owner (`ego-browser` when installed). Otherwise use an existing approved controller or hand off the same authorization page for the human-only step; do not install a browser or extract cookies as an implicit prerequisite. Open the URL emitted by the attempt CLI, confirm the expected email before continuing, and enter only the code from that still-running CLI. Inspect the current visible form, including separately rendered code-character inputs. Wait for visible input or completion state, not merely the presence of a hidden input. Treat MFA, disabled device authorization, an expired code, or a different account as an explicit recovery condition; do not retry the old code or approve a different account. For expiry, first confirm/cancel the task-owned old attempt, then obtain a new code.
7. **Verify the attempt before installation.** Require the CLI's successful terminal exit, then independently read the attempt store's expected account identity, freshness and permissions without exposing credentials. Run the bounded authorized no-op below through the same entry, attempt home and store; require exit `0`, `OK` and `turn.completed`. Browser success alone, a lost CLI receipt or a failed token exchange cannot pass this step. Keep unknown attempts bound to their original handle and reconcile before retrying.
8. **Install through the bound owner and read back.** Use the provider's existing protected installation, or coordinate exclusive access to the exact target file store, recheck target identity and unchanged pre-install state, and atomically install only the verified current auth with mode `0600`. Preserve target config/history/Hooks; do not replace the directory. Independently confirm target identity, permissions and installation before target validation. Hand refresh ownership from the attempt to the confirmed target; do not keep querying both stores. On timeout or unknown write receipt, inspect/query the same operation before retry; do not overwrite or start another login to diagnose it.
9. **Verify target access and report its scope.** Run the no-op through the target's ordinary entry with its bound home/store, then confirm the expected identity remains selected. Report identity, authentication, quota, existing-process adoption and Credit policy separately. Finish the browser controller's task and read task-owned probes to terminal state; preserve other users' sessions. Arrange an authorized execution handoff before long work if the current TUI has not adopted the required account.

## Cached login inspection

The wrapper's `status` runs supported `codex login status`, without an `exec`
prompt. `login_present` describes the CLI's cached-login report; `auth_mode`
distinguishes ChatGPT from another reported mode or unknown output. Unrecognized
output and command failures remain unknown. Raw CLI text is not returned because
other modes can include a credential fragment.

`authenticated` is null and `authentication`, `quota` and `billing` remain
`not_checked`. This is a deliberate change from the former model-request status
check: callers must not interpret cached login as valid server access. Require
the selected ChatGPT mode before this OAuth workflow; use the separately authorized
Verification route when real access must be established.

## Verification

For a build supporting `--no-daemon`, bind the check to an independent process as
below. Confirm that option in the selected ordinary entry's `--help`; if unavailable,
resolve its process/auth isolation before using the result as target-store evidence.

```bash
# Set AUTH_CHECK_HOME to the verified attempt or target file-store root.
# Use the resolved normal CLI entry and its required network context.
CODEX_HOME="${AUTH_CHECK_HOME:?Set the verified attempt or target root}" \
  codex --no-daemon -c 'cli_auth_credentials_store="file"' \
  exec --skip-git-repo-check --ephemeral --sandbox read-only --json \
  'Reply only OK. Do not use tools.'
```

Bind an authorized refresh owner before this probe; it is a real request and can use allowance or Credit under that account's policy. For a non-file store, retain the owner's supported store binding rather than applying this file-store example. Use a bounded task-owned process and inspect its actual terminal result. Do not retry a known authentication rejection until credentials change. Success proves access at that time, not full remaining quota or adoption by already-running sessions. See [OpenAI authentication documentation](https://developers.openai.com/codex/auth/) for supported login/cache mechanisms.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Not authenticated" or missing cache | Use the authorized local or remote login branch for the selected store |
| Expired access token with a valid refresh token | Bind authorized refresh ownership, then let Codex refresh through the actual target entry; verify the resulting account and request |
| `invalid_refresh_token` or another terminal refresh rejection | Stop repeating that cache; enter the [recovery workflow](#remote-account-switch-and-expired-login-recovery) for a fresh independent login or an explicitly authorized single-owner transfer |
| Desktop app logged in but CLI not | Compare home, store and executable first; do not blindly log out a shared store |
| Quota rejection | Report the selected account's quota condition; switch only to the account the user authorized |
| Only existing sessions fail while a fresh process works | Investigate those processes and coordinate any necessary restart/resume; do not infer global revocation or stop other sessions |
