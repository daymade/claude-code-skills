---
name: local-codex
description: >-
  Launches and manages the local OpenAI Codex CLI as a non-interactive coding sub-agent via ChatGPT
  OAuth, never API keys. Use to delegate coding tasks to Codex, run codex exec, generate or
  refactor code, or get a Codex code review; phrases like 'codex', 'run codex', 'codex exec',
  'delegate to codex'.
---

# Local Codex

Delegate coding tasks to the local OpenAI Codex CLI agent using the authorized ChatGPT account's OAuth access.

## When to Use

- User wants to generate, refactor, or review code via Codex
- User wants to run `codex exec` for non-interactive tasks
- User wants to use Codex's GPT-5.5 agent capabilities
- User mentions "codex", "run codex", "delegate to codex"

## Authentication (ChatGPT OAuth)

**CRITICAL**: Use ChatGPT OAuth through the selected credential store. **Do NOT set `OPENAI_API_KEY` or pass API keys** for this workflow. Keep the authentication route separate from the account's allowance and extra Credit policy; OAuth does not guarantee that long work cannot consume extra Credit.

- Resolve the actual `CODEX_HOME` and store; the desktop app and CLI can share credentials.
- Before login, account switching or token recovery, read [the OAuth guide](references/oauth-guide.md) and follow its [recovery recipe](references/oauth-guide.md#remote-account-switch-and-expired-login-recovery). Use fresh empty stores for independent grants, retain explicitly authorized single-owner transfers, and verify actual access and existing-process adoption separately.
- Before a native quota query, read [refresh ownership](references/oauth-guide.md#bind-refresh-ownership-before-native-queries); a nominally read-only query can refresh credentials.
- For quota-driven continuation on another authorized account, use [the included-usage check](references/oauth-guide.md#quota-driven-continuation) before substantial execution; cached login or a new default file is not that check.

## Codex CLI Path

The skill auto-detects Codex CLI in this order:
1. `CODEX_BIN` env var, if set — explicit override. A non-executable path fails loudly
   instead of silently falling through to a different build (that would make whatever
   the wrapper measured unattributable).
2. `which codex` — the executable first on the wrapper process's PATH, including
   npm global installs under nvm (`~/.nvm/versions/node/*/bin/codex`). This lookup
   does not execute an interactive shell's alias or function.
3. `/Applications/ChatGPT.app/Contents/Resources/codex` — the copy bundled inside
   ChatGPT.app, fallback only. Its version tracks the Desktop app and can diverge from
   the npm build, so it is deliberately last.

If a bad `CODEX_BIN` was set, the wrapper exits 1 with
`{"error": "CODEX_BIN not executable", "path": <value>}` — the offending value is in
the error itself, and `searched_paths` is not emitted for this case (no other search
step ran). If neither PATH nor the app bundle has a codex, the wrapper exits 1 with
the actual search order in `searched_paths`.

Whichever binary wins, attribute behaviour to it by versioning **the binary that
ran**. An unrelated shell's `codex --version` may resolve another entry, which is
the wrong build to quote when the fallback picked the app-bundled one. Use the
`codex_path` field from the wrapper's status output:

```
"<codex_path from status output>" --version
```

Before using this wrapper, resolve the user's ordinary CLI entry. When that entry
is a shell function or launcher supplying network/auth context, use it through
its owning shell instead of silently substituting the discovered binary. On macOS
zsh, inspect with `/bin/zsh -lic 'command -v codex; codex --version'`, then run
`codex` inside that same shell mode. Put the finite timeout around the shell
process: `gtimeout … codex` resolves an executable and cannot call a shell function.
The bundled Python wrapper does not reproduce shell initialization or support
every native flag; use native CLI invocation when those capabilities are required.

## Usage Patterns

### 1. Basic exec (single task)

```bash
python3 scripts/codex_wrapper.py exec "<prompt>" [<workdir>] [<model>] [<sandbox>] [<timeout>]
```

Example:
```bash
python3 scripts/codex_wrapper.py exec \
  "Write a Python function to calculate fibonacci" \
  /tmp \
  gpt-5.5 \
  workspace-write \
  300
```

### 2. Code review

```bash
python3 scripts/codex_wrapper.py review [<workdir>] [<model>] [uncommitted:true] [<timeout>]
```

Example:
```bash
python3 scripts/codex_wrapper.py review \
  /path/to/repo \
  gpt-5.5 \
  true \
  300
```

### 3. Inspect cached login

```bash
python3 scripts/codex_wrapper.py status
```

Interpret this result using [cached login inspection](references/oauth-guide.md#cached-login-inspection).
For an authorized real access check, follow that guide's Verification route.

## Parameters and results

The command arguments, defaults and JSON fields are defined by `main()`,
`exec_codex()`, `review_codex()` and `check_auth_status()` in
[`scripts/codex_wrapper.py`](scripts/codex_wrapper.py). Use those definitions
rather than a second parameter or output-field table.

## Safety Notes

- `sandbox=read-only` for analysis/review tasks (no file writes)
- `sandbox=workspace-write` for code generation (writes to working dir)
- `sandbox=danger-full-access` only when explicitly needed (full system access)
- Always use `--skip-git-repo-check` when running outside git repos
- Use `--ephemeral` for one-off tasks (no session persistence)

## Session Management

For multi-step tasks, Codex supports session resume:
```bash
# First step
codex exec --json "Step 1..."
# Later, use the session ID reported by that first invocation:
codex exec resume "${CODEX_SESSION_ID:?Set the session ID from the first invocation}" "Step 2..."
```

The wrapper currently runs single-shot exec. For multi-step workflows, use raw `codex exec` commands.
An ephemeral invocation does not persist a session for later resume.
Use `--last` only after confirming that the most recent recorded session is the intended target.

## Limitations

- Remote login can use device authorization with a browser on another machine; follow the OAuth guide instead of requiring a desktop app on the remote host.
- Inspect the selected binary's `doctor --help` before using its diagnostics; when supported, use the full report for endpoint/remedy details rather than `--summary`. Interpret the failed check, not only the aggregate exit code, and read the emitted JSON schema instead of assuming an older build's keys.
- Shell environment inheritance follows the selected build's `shell_environment_policy`; inspect the effective configuration. Keep credentials out of prompts.
- Large file operations may need increased timeout
