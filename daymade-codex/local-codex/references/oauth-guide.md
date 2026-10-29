# OAuth Authentication Guide for Local Codex

Use **ChatGPT OAuth** through the supported Codex login flow. Keep this route separate from API-key billing, the selected account's allowance, and its extra Credit policy. Do not promise a fixed plan price or no extra Credit consumption.

## How Authentication Works

1. Resolve the actual CLI entry, `CODEX_HOME` and configured credential store.
2. Choose the supported login branch for that owner: a verified existing native owner below, or a fresh store for an independent grant. The default file store is `~/.codex/auth.json`.
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
- Obtain independent grants for distinct cross-machine or cross-purpose auth roots. In inspected upstream 0.160/0.163 login paths, ordinary browser/device login calls `clear_existing_auth_before_login` → `logout_with_revoke` before OAuth. Do not seed an independent login attempt with old credentials: it can revoke the grant still used elsewhere. This version-specific source order does not describe every login route; the verified 0.165 existing-owner branch below has a different lifecycle. Source order establishes a mechanism, not a captured production revoke request or its success.
- Preserve an explicitly authorized **TRANSFER** of a verified login as a separate single-owner recovery case. Confirm which source consumers will stop using the grant before the target takes ownership; the transfer does not authorize concurrent copying, refreshing or re-login against that grant. Do not repeatedly reinstall rejected credentials.
- Back up credential bytes for local recovery, but do not treat that backup as a way to reverse server-side revocation. Never use destructive logout as an account diagnostic.

### Bind refresh ownership before native queries
- Treat even a nominally read-only quota query as potentially refreshing credentials, including native workspace 401 recovery. File equality before/after a query and access-token expiry gating cannot enforce no server-side refresh.
- Before initializing a native client or quota collector, bind an authorized refresh-owning source. Reuse the project's deployed provider/query owner when present; use independently obtained grants for separate query and execution roots. If ownership is unknown, stop that native query rather than testing it against a copied grant.
- Keep cached identity, authentication, quota, process adoption and billing as separate facts. If the user requires no old-account Credit consumption, arrange already authorized fresh-account execution or handoff before long work and verify its actual account. Replacing the default file does not switch a running TUI.

### Check existing sessions separately
- Before any account, quota, authentication, error, or process claim about a particular session, require observer proof that binds the target session ID (SID), its cwd, and exactly one runtime identity to the same session. A runtime-scoped account or state response alone proves only what that runtime reported, not which session owns it. Zero, multiple, or incomplete matches mean `unknown`; never select or fall back by recency, account health or capability, quota availability, or a healthy runtime. When Minions' public session-bound diagnostic is available, it owns this mechanical gate; do not substitute an agent-selected fallback.
- A first-hand user `/status` report that contradicts the agent's attribution is a stopping contradiction. Stop the session-attributed claim and reconcile the user's direct observation against the SID+cwd+unique-runtime evidence; never repeat, override, or subordinate the user's report to the agent inference. Keep the attribution `unknown` until the conflict is resolved.
- Long-lived processes can retain stale in-memory authentication. Verify the affected build and process; a changed login file and a successful new process do not establish whether an existing session adopted the account. Keep untested sessions `not_checked` rather than declaring that every session switched or must restart.
- A token-refresh error establishes an authentication failure for that request, not that signing in on another machine always revokes every login. Group runtime errors by process before attributing repeated messages to independent failures.
- If an existing process is confirmed stale while a new process works, first distinguish a [shared native owner](#existing-native-owner-recovery) from an independent TUI. Preserve its conversation and coordinate an authorized recovery. For independent terminals managed by `ghostty-use`, use that owner's existing-session snapshot/restore workflow and verified session IDs. Otherwise use bare `codex resume` (interactive picker) in the same directory after the owner releases the process. A rollout/session id for `codex resume <id>` does **not** come from the logs DB (its `thread_id` is usually NULL or logs-only); verify it in `state_*.sqlite` `threads` using cwd and creation time. Those fields locate resume candidates but do not satisfy the attribution gate above. Do not kill terminals, stop other sessions or restart daemons for a login check; preserve active work and drafts. Re-login only when the target's current credentials also fail.
- To locate candidate token-refresh errors, query the runtime log. The command's mtime ordering selects only a log store, not a session; returned `process_uuid` values are candidate error locations, not account or session proof (measured 2026-10-03):

```bash
AUTH_ROOT="${CODEX_HOME:-$HOME/.codex}"
AUTH_LOG_DB=$(ls -t "$AUTH_ROOT"/logs_*.sqlite | head -1)
sqlite3 "$AUTH_LOG_DB" "
SELECT process_uuid, COUNT(*), datetime(MIN(ts),'unixepoch','localtime') first_seen
FROM logs WHERE feedback_log_body LIKE '%could not be refreshed%'
GROUP BY process_uuid ORDER BY 2 DESC;"
# process_uuid is pid:<pid>:<uuid> — investigate those processes; this is not permission to stop them
```

### Quota-driven continuation

When switching to an already authorized account to continue included usage,
the executing agent uses the existing refresh-owning provider to obtain fresh
native account and rate-limit observations for the exact execution root and
ordinary CLI route. Bind the expected account across the observation; a returned
`accountId` must match it. Under the inspected [native response contract](https://github.com/openai/codex/blob/83086188ae0614bd882818ff1aa23f3194962012/codex-rs/app-server-protocol/schema/json/v2/GetAccountRateLimitsResponse.json),
`ordinaryUsageAllowed` is boolean or null. Require strict `true`, attributed to
that account, for this positive included-usage check; strings or integers are not
permission. Missing/null remain unknown and do not erase a still-fresh denial.
This check does not globally disable a project's existing legacy-admission policy.

Check the selected model/service tier and its applicable standard quota windows
as separate inputs. Exhausted windows or an active spend-control refusal still
prevent this continuation when permission is true. Neither window percentages,
OAuth nor permission true guarantees that extra Credit is disabled. Do not change
billing, redeem a reset or select paid fallback to make the check pass.

After readiness, continue the authorized unfinished business task with a bounded
useful action. Reuse that action's terminal result as access evidence instead of
adding repeated no-op model turns. Keep the original task, working tree and
permissions; account adoption by a new CLI process does not prove adoption by
any already-running TUI. The provider supplies observations; this choice and the
business-result check remain the executing agent's responsibility.

### Headless / Automation notes
- For local automation or a remote host, follow the workflow below: retain a valid authorized login, perform an explicit single-owner transfer, or obtain a fresh independent browser/device grant.
- Keep CI/CD authentication under its owning deployment policy. Do not silently substitute API-key billing for the requested ChatGPT access.

## Remote account switch and expired-login recovery

Bind the approved target host, target user/home, expected account, and authorization before writing. Resolve the current project's already-approved account, target and recovery restrictions from its authoritative entry. Prefer its deployed provider when that owner already implements login, protected installation and request reconciliation; do not create another OAuth client/helper or bypass its locks. A recipe here does not authorize an unapproved target or a fallback forbidden by the current user direction. Keep machine addresses, project entry locations and real accounts in the owner's configuration.

For an already-running native owner, first [compare the live account and saved login](#existing-native-owner-recovery). Use [same-owner OAuth adoption](#existing-native-owner-oauth-adoption) when new authorization is needed and the owner's browser-login capability is verified. The fresh-store steps below remain the route for independent grants and old or unverified login implementations; they are not a requirement to restart every existing process.

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
7. **Verify the attempt before installation.** Require the CLI's successful terminal exit, then use the existing provider's bounded native account observation to verify the attempt's expected identity and server access through the same entry, home and store without exposing credentials. If this observation cannot establish access, use the separately authorized model-request check below; do not silently treat cached identity as a substitute. Browser success alone, a lost CLI receipt or a failed token exchange cannot pass this step. Keep unknown attempts bound to their original handle and reconcile before retrying.
8. **Install through the bound owner and read back.** Use the provider's existing protected installation, or coordinate exclusive access to the exact target file store, recheck target identity and unchanged pre-install state, and atomically install only the verified current auth with mode `0600`. Preserve target config/history/Hooks; do not replace the directory. Independently confirm target identity, permissions and installation before target validation. Hand refresh ownership from the attempt to the confirmed target; do not keep querying both stores. On timeout or unknown write receipt, inspect/query the same operation before retry; do not overwrite or start another login to diagnose it.
9. **Verify target access and report its scope.** Read the installed target through its refresh-owning provider and ordinary entry, then confirm the expected identity remains selected. For quota-driven continuation apply the check above and verify the first useful business action on that target; do not require another no-op when equivalent fresh access evidence already exists. Report identity, authentication, quota, existing-process adoption and Credit policy separately. Finish the browser controller's task and read task-owned probes to terminal state; preserve other users' sessions. Arrange an authorized execution handoff before long work if the current TUI has not adopted the required account.

## Existing native owner recovery

Bind the actual executable/build, PID/birth, `CODEX_HOME`, credential store and
control endpoint before choosing a write. Compare the saved login's expected
account with the account reported by that same live owner. Cached identity locates
the saved login; it does not prove server access, remaining quota or session adoption.
Minions-managed account binding remains with Account Manager.

| Observed state | Next action |
|---|---|
| The live owner already uses the expected account and authorized work succeeds | Keep the login and continue the task; do not restart or log in again. |
| An already authorized expected login is saved, but the shared daemon still reports the previous account | Consider the saved-login adoption below, with explicit authority for its process-wide effect. |
| The store and live owner agree, but authentication fails | Use the existing refresh-owning provider's supported recovery; do not infer that another account must be adopted. |
| No usable expected login is available | Choose the verified [same-owner OAuth](#existing-native-owner-oauth-adoption) or [independent-grant/TRANSFER](#remote-account-switch-and-expired-login-recovery) route. |

### Adopt a saved login in a shared daemon

1. Verify the bound build's `app-server daemon restart --help` and its session
   persistence/recovery behavior. Preserve affected SIDs, cwd, current work and
   pending input, plus the daemon PID/birth, executable fingerprint and private
   auth-file digest. Bind each claimed session to this owner; the executing TUI
   can belong to a different process. A terminal window is not that binding.
2. Obtain current authorization for restarting this exact shared daemon and the
   possible interruption of its affected tasks. Coordinate active writers and
   retain their recovery paths first. Without that authority, keep this branch
   read-only. Do not restart merely to test this recipe or bypass a refusal.
3. Where that build supports the verified lifecycle, run its native command
   through the bound entry and the same home/store/network context:

   ```bash
   codex app-server daemon restart
   ```

   Do not log out, copy credentials, start OAuth, replace the selected binary or
   change the home as part of saved-login adoption. This command is an adoption
   route, not evidence that `account/read` with `refreshToken:true` hot-reloads an
   externally changed store. Verify that API's behavior separately before using it.
4. Read back the new PID/birth and actual account through the same owner, then
   apply the [quota-driven continuation checks](#quota-driven-continuation).
   Verify saved SIDs and their individual runtime states; an unloaded child is
   not evidence that its recorded conversation was deleted. When unchanged auth
   or binary bytes are part of the claim, compare the frozen digests. A changed
   input or lost restart receipt needs reconciliation, not another restart.
5. [Continue only authorized stopped sessions](#continue-the-bound-original-sessions)
   and verify useful work under their original IDs. Do not claim all local TUIs,
   uninterrupted requests, automatic Account Manager integration or Credit
   isolation from one daemon's account readback. Build-specific success does not
   establish the same lifecycle for stock, older or other builds.

### Continue the bound original sessions

Freeze only the original session set covered by the user's continuation request.
Immediately before submission, recheck the same SID and cwd, its captured latest
failed turn and still-authorized recoverable cause, and an idle runtime. Skip a
changed turn, already running, completed, paused-by-user or still-blocked work.
Separate the current turn from
its Goal; use the existing Goal recovery owner without resetting its objective,
budget or accumulated use. Account adoption alone authorizes no new task turn.

Use the bound owner's supported submission interface and its current schema.
Retain one stable `clientUserMessageId`, the exact authorized text, submission
handle and returned turn ID per SID. If the user requested only “继续”, send only
that text once. A `queue/start` not-found response can race with consumption;
first read back that same message ID, rather than submitting it again.

For a build exposing the inspected native queue contract, read
`thread/queue/list` with the exact `threadId`. Submit only when its queue is
explicitly empty and complete; a nonempty queue, `nextCursor`, incomplete or
unknown read stops this write without deleting or changing existing submissions.
Then call `thread/queue/add` with
that `threadId`, the stable `clientUserMessageId`, and
`input: [{"type":"text","text":"继续","text_elements":[]}]` for that literal request.
Verify the returned submission's client ID and input before calling
`thread/queue/start` with the same `threadId` and `queuedSubmissionId` from its
`id`. Retain each result; do not infer a missing submission's fate from an empty
queue or replace a failed/unknown attempt with a new client ID.

Verify the matching original SID/turn, user-message `clientId` and exact body,
then observe subsequent useful execution. In the inspected item-history schema,
`thread/items/list` returns `data[]` entries whose `item` contains the message or
tool and whose `turnId` identifies its turn; do not test wrapper fields as if
they were the item. Keep missing, ambiguous or malformed reads unknown and do
not replay them. Enqueue success, an active status, and tool execution are separate
from the original task's finished business result.

## Existing native owner OAuth adoption

The inspected official **0.165.0** app-server supports browser OAuth through the existing owner's `account/login/start` with `{"type":"chatgpt"}`. Its [account processor](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/app-server/src/request_processors/account_processor.rs) starts this flow without pre-clearing the current auth; the [callback server](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/login/src/server.rs) exchanges and saves credentials before reporting callback success. The processor reloads auth on successful callback completion. This does not establish the behavior of older builds, device login, standalone `codex login`, or externally managed authentication.

1. **Bind the live owner and permission.** Verify the actual executable/build, process birth, home/store and supported account API through the owner's existing official control connection. For a session claim, also apply the SID+cwd+unique-runtime gate above. Obtain authorization for the account change's process-wide effect on every thread sharing this owner. A read-only Source or endpoint registration grants no account-write capability. Minions-managed adoption stays with Account Manager; unmanaged/legacy recovery retains its existing owner.
2. **Keep one original login attempt.** Before sending `account/login/start`, inspect the actual listener and its ownership at the bound callback host/port and reuse any existing callback coordination or lease; if a listener exists or its ownership is unknown, coordinate the original request first, never call start as a probe or clear the port automatically, because the inspected server may send `/cancel` before fallback. Any fallback belongs to that original request: verify it without reopening login. Subscribe to `account/login/completed` before sending the supported start request; retain its `loginId` and private `authUrl`. Complete that URL through the authorized browser and verify the intended account before consent. Do not log out, copy auth, replace the home, launch another owner or change API-key/external-auth policy to make the flow succeed. Missing receipt or connection loss means reconcile this attempt before starting another.
3. **Verify adoption and continuation separately.** Require a successful completion event for that login ID, then read account → rate limits → account through the same owner and confirm its process/birth and expected account remain stable. Match the returned quota `accountId`; apply the strict ordinary-use permission and window checks above. Continue the original authorized work with a bounded useful action in the same session; account readback alone does not prove execution adoption.
4. **Do not reinterpret earlier requests.** The inspected [model client](https://github.com/openai/codex/blob/rust-v0.165.0/codex-rs/core/src/client.rs) resolves current auth for later requests, rejects owner changes during setup and resets cached WebSocket state when ownership changes. A request already sent is not retrospectively moved to the new account; an in-flight turn can abort. Verify subsequent business progress rather than promising uninterrupted turns, every window switched, or zero extra Credit.
5. **Reconcile cancellation and failure.** Cancel only the bound attempt through its supported owner operation. Cancellation stops the login attempt; it does not restore credentials already saved by a racing callback. A failed completion can follow persistence or reload trouble. Read the same owner's actual account before deciding recovery; never restore a backup or start another login merely because the event was unsuccessful.

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

Prefer the existing provider's native observation for account/access inspection;
it does not require a model turn. Use the following model-request check only when
authorized and necessary to establish execution access, or replace its no-op with
the first bounded useful action from the original task and inspect that result.

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
