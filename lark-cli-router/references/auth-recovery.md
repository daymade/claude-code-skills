# Resume an authorized user login

Use this branch only after the current embedded `lark-shared` identity/permission
guide establishes that an existing, task-authorized user profile needs login.
Keep bot identity, missing application scope, resource permission and
`needs_refresh` on their existing branches. A `needs_refresh` token normally
renews on the next authorized user API read; do not start login for that state.

Read the installed CLI version's identity guide and `auth login --help` first.
The helper requires a POSIX host with Python 3.9+ and `fcntl`. On other hosts,
retain the official split flow and use a supported host background executor when
available; do not run this helper or claim its background behavior was verified there.
The helper requires `auth login --no-wait --json`, `--device-code`, and
`auth status --json --verify`. Unsupported flags or changed JSON require the
version-matched guide; do not substitute guessed commands or credential edits.

## Start and deliver the link

Bind the explicit profile through [source account binding](source-account-binding.md).
The helper reads its existing appId/openId before issuing a code and retains that
binding for completion. A missing binding stops the flow; establish it through
the existing profile/account owner rather than using another account's values.

Resolve `<router-dir>` to this installed Skill directory. Run once with the
already-authorized scope/domain selectors and excludes:

```bash
python3 "<router-dir>/scripts/lark_device_flow.py" start \
  --profile "<authorized-profile>" --owner "<current-agent-session>" \
  --scope "<authorized-scope-list>" --authorization-confirmed
```

Use repeatable `--domain` and `--exclude`, or `--recommend`, only when those exact
selections are already authorized. `--authorization-confirmed` records the
caller's authorization check; it does not obtain consent or permit extra scopes.
Never omit the selector and fall back to the CLI's all-domain default.

`start` issues `--no-wait --json`, privately stores the code, starts a session-owned
background polling worker and returns the original `verification_url`, deadline,
flow ID and PID immediately. Show that URL unchanged in the same turn's final
message and return control. Follow the loaded guide's QR display requirement too.
Tell the user to authorize before the displayed deadline; no reply is needed for
the worker to save credentials. Do not run another blocking poll in the foreground.
Starting the identical active flow returns its existing link; a different active
selection for that profile is a conflict, not permission to invalidate its code.

## Observe or continue

```bash
python3 "<router-dir>/scripts/lark_device_flow.py" status --flow-id "<flow-id>"
python3 "<router-dir>/scripts/lark_device_flow.py" continue \
  --flow-id "<flow-id>" --owner "<current-agent-session>"
```

State defaults to `~/.local/state/lark-cli-router/device-flows/`; an explicit
`--state-dir` must remain outside the update-owned Skill bundle. The directory is
private, and state/lock files use mode 0600. Retain the flow ID with the task;
do not paste state contents, device codes or credentials into chat or logs.

`status` exposes deadline, PID and outcome without raw CLI output or tokens. An
inherited lock covers both the worker and its polling child. If the worker is
lost while its child is still polling, continuation leaves that existing attempt
running. Once no poll is active, `continue` verifies current auth state first;
it reuses an unexpired code only when recovery is still necessary. It never
creates a new grant. The helper is a local background process, with no service
or launchd registration; reboot, host child cleanup or lost network can interrupt it.

`expired` requires a fresh link. Use explicit `retry --flow-id "<flow-id>"
--owner "<current-agent-session>" --authorization-confirmed` only within the
same authorization; it retains the original selectors and excludes. Never reuse
an expired URL/code. `denied` stops; do not retry a refusal automatically.

## Verify the account, then the business result

`credentials_saved` records the CLI's explicit flag or its documented
`authorization_complete` event after credential/profile storage. It remains
`unknown` when a lost worker leaves only a later auth observation. Independently,
the helper runs `auth status --json --verify` and matches both appId and openId
before reporting `auth_verified`. `wrong_identity` stops all business actions and
new helper attempts that would adopt the other account. Resolve the selected
profile through its account owner and official CLI. An explicit `retry` can then
proceed only if the profile again matches the flow's original appId/openId. Do not
edit raw credentials or silently adopt the newly logged-in account.

Read `poll_exit_code`, `missing_scopes` and the verified status together. A
nonzero exit can coexist with saved credentials and missing scopes; it does not
justify restarting the flow. `refresh_token_issued: false` warns that another
login may be needed later. A missing flag stays `unknown`: `offline_access`,
access-token expiry and refresh-expiry timestamps do not prove issuance.

Every helper result leaves `business_read` required. Return to the selected
version-matched domain guide and perform its narrowest authorized target read
with the same explicit `--profile` and `--as user`. Only that result establishes
usable access to the requested resource. Keep unrelated scope gaps separate;
permission denial stops that target/profile/identity route.
