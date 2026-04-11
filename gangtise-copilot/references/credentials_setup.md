# Gangtise Copilot — Credentials Setup Reference

Deep-dive documentation for `scripts/configure_auth.sh`. Read this to understand the credential file format, where it's stored, how liveness checks work, and how to rotate credentials without breaking any installed skill.

## Credential shapes

Every Gangtise skill's `scripts/utils.py` looks for `scripts/.authorization` and accepts one of two shapes:

### Shape A — accessKey + secretAccessKey (recommended)

```json
{
  "accessKey": "YOUR_ACCESS_KEY_HERE",
  "secretAccessKey": "YOUR_SECRET_ACCESS_KEY_HERE"
}
```

The skill calls `https://open.gangtise.com/application/auth/oauth/open/loginV2` with this payload, gets back a Bearer token (TTL: 10800 seconds / 3 hours), and uses that token for subsequent API calls. The token is refreshed automatically when it expires.

**Use this shape unless you have a specific reason to use Shape B.** It's the simplest to set up and it has no manual rotation step.

### Shape B — long-term token (advanced)

```json
{
  "long-term-token": "Bearer YOUR_LONG_TERM_TOKEN_HERE"
}
```

If your organization issues pre-generated long-lived tokens through a separate process (e.g., an SSO integration that mints Gangtise Bearer tokens), store them in this shape. The skill will use the token verbatim and skip the OAuth dance.

**Limitation**: `configure_auth.sh --verify-only` cannot re-verify long-term tokens because it doesn't know which endpoint to probe for arbitrary scope. Shape B users should run their own liveness checks via the tool that issued the token.

## Storage location (XDG standard)

The wrapper stores **one shared credential file** at:

```
~/.config/gangtise/authorization.json
```

This location follows the XDG Base Directory specification (`$XDG_CONFIG_HOME/gangtise/` defaulting to `~/.config/gangtise/`). It is respected on macOS, Linux, and WSL. Windows users should set `%LOCALAPPDATA%` equivalently or pass `--access-key` / `--secret-key` flags directly (the file path logic uses `$XDG_CONFIG_HOME` when set).

### Why a shared file and not per-skill files?

Each Gangtise skill (19 of them) has its own `scripts/` subdirectory, and each one looks for `.authorization` in that subdirectory. The naive approach would be to write 19 independent credential files, but that has three problems:

1. **Rotation is painful.** Changing your credentials means editing 19 files.
2. **Drift is easy.** If even one file gets out of sync during rotation, one skill will fail while the others work, and debugging it is miserable.
3. **Security surface is larger.** 19 files means 19 places a leak can happen.

The wrapper solves this by writing a single file to the XDG location and then creating **symlinks** from each skill's `scripts/.authorization` to the shared file:

```
~/.local/share/gangtise-copilot/skills/
├── gangtise-data-client/
│   └── scripts/
│       └── .authorization → ~/.config/gangtise/authorization.json
├── gangtise-kb-client/
│   └── scripts/
│       └── .authorization → ~/.config/gangtise/authorization.json
└── ... (17 more)
```

Rotate credentials = edit one file. All 19 skills pick up the change instantly.

## Permission mode

`configure_auth.sh` writes the credential file with mode `600` (owner read+write, no group, no other). The parent directory `~/.config/gangtise/` is created with mode `700`.

If you copy the file manually or modify it with a tool that doesn't preserve mode, fix it with:

```bash
chmod 700 ~/.config/gangtise
chmod 600 ~/.config/gangtise/authorization.json
```

`diagnose.sh` will warn you if the mode drifts from 600.

## Input precedence (how `configure_auth.sh` gets the credentials)

The configurator accepts credentials from three sources, in this precedence order:

1. **Flag arguments** (highest): `--access-key KEY --secret-key KEY`
2. **Environment variables**: `GANGTISE_ACCESS_KEY` / `GANGTISE_SECRET_ACCESS_KEY`
3. **Interactive prompt** (lowest): if neither of the above is set, the script asks you to type each value. The secretAccessKey prompt uses `stty -echo` to hide the input.

This lets you automate bootstrap in CI (flags or env vars) while still having a clean interactive flow for first-time local setup.

## Liveness verification

After writing the file, `configure_auth.sh` performs a **live authentication call** to verify the credentials actually work. This is done by POST-ing the credential payload to:

```
https://open.gangtise.com/application/auth/oauth/open/loginV2
```

**Critical detail**: Gangtise returns HTTP 200 for **both success and failure** — the server responds with a JSON body containing a `code` field that is `"000000"` on success and something else on failure (often a validation error code). A liveness check that only looks at HTTP status will pass for an invalid credential and produce a broken install.

The configurator matches on `"code":"000000"` in the response body, not on HTTP status, and extracts the `userName` + `uid` from a successful response to echo back to the user as confirmation.

This is a **scope-level** verification — it proves that the accessKey + secretAccessKey can mint an OAuth token. It does NOT prove that the resulting token has `rag` scope (which is what most Gangtise skills actually need). That second-level check is performed by `diagnose.sh`, which calls the RAG search endpoint after obtaining a token.

## Rotation procedure

```bash
# 1. Edit the shared credential file:
$EDITOR ~/.config/gangtise/authorization.json

# 2. Re-verify the new credentials against the live server:
bash scripts/configure_auth.sh --verify-only

# 3. If verification passes, every installed skill is already picking up
#    the new values via the symlink — nothing else to do.
```

If verification fails, the old credential file is left in place and you can revert the edit.

## What to do when credentials are rejected

`configure_auth.sh` will print the server's response when authentication fails. The most common error shapes are:

| Server response contains | Meaning | Fix |
|---|---|---|
| `"code":"999991"` or similar non-zero code | accessKey or secretAccessKey is wrong | Re-check the values; watch for trailing whitespace |
| HTTP 5xx | Gangtise server is down | Wait and retry |
| Network error / timeout | Local network or proxy issue | Check your connectivity; add the Gangtise host to your NO_PROXY list if you have a local HTTP proxy |
| `"code":"000000"` but subsequent skill calls fail | Account doesn't have the scope the skill needs | Contact your Gangtise account administrator to add the `rag` / `data` / `file` scope |

## NO_PROXY configuration (macOS / Linux with a local HTTP proxy)

If you run a local HTTP proxy (Shadowrocket, Clash, etc.) that intercepts `*.com` traffic, Gangtise API calls may fail because the proxy terminates TLS incorrectly. Add the Gangtise host to your NO_PROXY list:

```bash
export NO_PROXY="open.gangtise.com,$NO_PROXY"
export no_proxy="open.gangtise.com,$no_proxy"
```

The wrapper's scripts do not automatically set NO_PROXY — doing so would be overreach. But if you hit persistent network errors during the liveness check on a machine with a local proxy, this is almost always the fix.

## Security considerations

- **Never commit `authorization.json` to version control.** The example template at `config-template/authorization.json.example` uses placeholder values and is safe to commit; the real file in `~/.config/gangtise/` must never leave your machine.
- **Rotate immediately if you suspect a leak.** Gangtise's admin portal has a "regenerate key" option — do that, then re-run `configure_auth.sh`.
- **The mode-600 check exists for a reason.** If you see a warning that the file has wrong permissions (e.g., mode 644 after copying from another machine), fix it immediately. Shared credentials in user home directories are a common target for unprivileged escalation.
- **Don't paste your credentials into a chat, issue tracker, or log file.** If you need to share a repro, substitute placeholder values first.
