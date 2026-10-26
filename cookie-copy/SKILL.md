---
name: cookie-copy
description: >-
  Copies selected-site cookies between local profiles of the same macOS Chrome.
  Use for cookie copy, 复制 Cookie, 搬登录态 or reusing an existing ChatGPT session
  in an isolated profile. Supports Google and ChatGPT/OpenAI site selections,
  destination backups and restore, and expected-account verification for ChatGPT.
---

# Cookie Copy

Copy only an authorized source login state into an explicitly selected destination.
Keep backups and browser profiles outside the Skill and Git.

## Select the supported job

- Use the same macOS machine, OS user and Google Chrome installation. Do not use
  this workflow for cross-machine or cross-browser encrypted-cookie conversion.
- Select `--site chatgpt` for `chatgpt.com` and `openai.com`, or `--site google`
  for `google.com`. The CLI defaults to Google. Do not substitute another site.
- Copy encrypted rows without decrypting them or reading Keychain secrets. Keep
  source Chrome running if needed; require the destination Chrome to be stopped.
- Preserve the existing Google merge behavior. Replace the ChatGPT/OpenAI set
  together, including every session-token chunk, so stale chunks do not survive.
- Keep quota queries and reset decisions with `tibo-reset-codex`; login verification
  here does not call a quota endpoint or prove a downstream business operation.

## Prepare and resume

1. Fix the expected account, source database and task-owned isolated destination.
   Use Python 3.10+, Node.js 22+ and installed Google Chrome. Resolve missing tools
   through their existing installation owner; do not install Playwright or another
   browser for this workflow. Respect host restrictions on external browsers.
2. For ChatGPT, verify an existing destination first. If the expected identity is
   already authenticated, return it to the caller without copying again.
3. Initialize only a nonexistent destination with the command below. It refuses
   an existing root. If initialization was interrupted, inspect that exact root
   before resuming; do not overwrite it or silently choose a new account/directory.
4. Locate a different source profile with `--source-cookie-db` when the default
   daily Chrome `Default/Cookies` does not contain the authorized session. Do not
   retrieve credentials from conversation history. If no valid session exists,
   return to normal login with the caller's existing authorization boundary.

Run these commands from this Skill directory, one at a time; inspect each exit:

```bash
: "${MIGRATION_PROFILE:?set the isolated Chrome directory}"
: "${EXPECTED_EMAIL:?set the expected account email}"
node scripts/verify-chatgpt-profile.mjs --profile-dir "$MIGRATION_PROFILE" --initialize
python3 scripts/copy-cookies.py --site chatgpt --destination "$MIGRATION_PROFILE" --yes
node scripts/verify-chatgpt-profile.mjs --profile-dir "$MIGRATION_PROFILE" --expected-email "$EXPECTED_EMAIL"
```

Run initialization only when required. Use `--yes` only for an already authorized
write. For Google, use the copy command with `--site google` and an initialized,
stopped destination; verify the expected signed-in account through an authenticated
Google account view. An account-chooser memory is not a live session.

## Verify and recover

Treat copy exit 0 as a database transfer result. For ChatGPT, require the reopened
browser's email to match the expected account and `status=verified` with
`login_verified=true`. The verifier uses the current system HTTPS proxy or explicit
`--proxy`; `--headless` is optional. Treat a challenge as unconfirmed, not proof of
logout. Return 2 for unconfirmed and 1 for a tool error. `initialized` proves only
directory preparation. Report a downstream application's result separately.

Use the exact backup printed by the copier to restore a stopped destination:

```bash
: "${COOKIE_BACKUP:?set the exact backup path printed by the copier}"
python3 scripts/copy-cookies.py --destination "$MIGRATION_PROFILE" --restore-backup "$COOKIE_BACKUP" --yes
```

Check that this target still belongs to the task and contains no later human login
or new work before restoring. Restore backs up the current target first. Verify
the expected prior website state afterward; an existing backup is not login proof.

Keep the source read-only. Use one committed SQLite snapshot, including WAL; release
the source read transaction before requesting human approval. Require exact cookie
schema equality. Back up the complete destination with mode 0600, then write one
transaction; roll back failed writes. Preserve unrelated sites. Stop on an active
target or unresolved browser lock, and never terminate another session's browser.
The verifier closes only its own Chrome child. Yield on actual user takeover,
security prompts or host denial. Do not retry inputs or change channels around them.

Do not migrate history, bookmarks, extensions or password stores. Do not log cookie
values, session tokens or backup contents. Keep the exact missing prerequisite or
unconfirmed identity visible when handing the target back to its caller.
