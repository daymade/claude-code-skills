# Credential storage across profiles

Profiles isolate configuration. Whether they isolate *credentials* is a separate
switch, and the two are controlled by different environment variables. Getting
this wrong costs one browser authorization per profile for every OAuth-backed
MCP server you add.

## Two credential layers, different files

| What | Where | Isolated by |
|---|---|---|
| Provider routing token (`ANTHROPIC_AUTH_TOKEN` and friends) | `~/.claude/settings/<name>.json`, loaded per profile | the settings file you pass |
| Claude account OAuth + **every MCP server's OAuth token** | macOS Keychain (or `.credentials.json` where Keychain is unavailable) | `CLAUDE_SECURESTORAGE_CONFIG_DIR`, falling back to `CLAUDE_CONFIG_DIR` |

Only the second layer is discussed here. It is the one that decides whether
authorizing an MCP server once makes it usable everywhere.

## The Keychain entry name

The service name is computed, not fixed:

```js
function serviceName(suffix = "") {
  const e = process.env.CLAUDE_SECURESTORAGE_CONFIG_DIR;
  const useBareName = e !== undefined ? !e : !process.env.CLAUDE_CONFIG_DIR;
  const dir = e !== undefined ? e.normalize("NFC") : resolveConfigDir();
  const hash = useBareName ? "" : `-${sha256(dir).hex.substring(0, 8)}`;
  return `Claude Code-credentials${hash}`;
}
```

Three consequences:

- With neither variable set (the default profile), the name is the bare
  `Claude Code-credentials`.
- With `CLAUDE_CONFIG_DIR` set and `CLAUDE_SECURESTORAGE_CONFIG_DIR` unset —
  the out-of-the-box state for every third-party profile — the name carries
  `-sha256(<config dir absolute path>)[:8]`. Each profile therefore addresses a
  different entry, and an MCP server authorized in one is unauthorized in the
  rest.
- `CLAUDE_SECURESTORAGE_CONFIG_DIR` overrides the path the hash is taken from,
  **and an empty string suppresses the hash entirely** (`!""` is true), which
  resolves to the same bare name the default profile uses.

## Sharing one entry across every profile

```bash
export CLAUDE_SECURESTORAGE_CONFIG_DIR=""
```

Set it before the profile launcher is sourced. `CLAUDE_CONFIG_DIR` keeps doing
its job, so configs stay isolated while all profiles read and write one
credential store. Authorize an MCP server once and every profile is connected —
no copying, and no divergent snapshots to refresh when a token rotates.

Measured 2026-09-18 on a 14-profile machine: one browser authorization on the
default profile, after which `claude mcp list` reported `✔ Connected` for that
server from profiles that had never been authorized.

**Variant, if the shared store should not be the account's own entry:** point
the variable at a dedicated path (`export CLAUDE_SECURESTORAGE_CONFIG_DIR=
"$HOME/.claude-shared-creds"`). All profiles then share one hashed entry that is
distinct from the default profile's. The default profile has to adopt the same
value and log in once more, which is the cost of keeping the account token out
of the shared store.

## What sharing also shares

The entry holds `claudeAiOauth` (the Claude account) alongside `mcpOAuth` (the
per-server tokens). Sharing is all-or-nothing:

- Third-party profiles route through `ANTHROPIC_BASE_URL` + an auth token and
  never read `claudeAiOauth`, so day-to-day there is no interaction.
- `claude logout` in **any** profile clears the shared entry, logging the
  default profile out too. Before sharing, this was contained to one profile.

Use the dedicated-path variant above if that trade is not worth it.

## Verifying which entry a profile actually asks for

Do not infer this from documentation or from a config file — intercept the call.
Claude Code shells out to `security` by name, so a shim earlier on `PATH`
captures the exact service it requests:

```bash
mkdir -p /tmp/probe/bin
cat > /tmp/probe/bin/security <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "$PROBE_LOG"
exec /usr/bin/security "$@"
EOF
chmod +x /tmp/probe/bin/security

PROBE_LOG=/tmp/probe/out.log \
PATH=/tmp/probe/bin:$PATH \
CLAUDE_CONFIG_DIR=$HOME/.claude-profiles/<name> \
  claude mcp list >/dev/null 2>&1

grep -o '\-s Claude Code-credentials[^ ]*' /tmp/probe/out.log | sort -u
```

Without the sharing variable this prints a hashed name; with it, the bare one.
The same shim answers any "does this actually reach the store I think it does"
question, including after a Claude Code upgrade.

## Reading a token without printing it

`mcpOAuth` keys are `<server name>|<hash of the server URL>`. A key existing
proves an authorization was *started*, not that it completed — an abandoned flow
leaves the full discovery metadata (`issuer`, `redirectUri`, `serverUrl`) behind
with `accessToken` set to the empty string. Check the length, not the presence:

```bash
security find-generic-password -s "Claude Code-credentials" -w \
  | jq -r '.mcpOAuth | to_entries[] | "\(.key): \(.value.accessToken | length) chars"'
```

## Stability

`CLAUDE_SECURESTORAGE_CONFIG_DIR` is absent from the published documentation,
which states that MCP tokens are "stored per endpoint, not shared across
profiles". The variable is read by the shipped binary and the behavior above is
measured, but it is not a documented contract and an upgrade may change it.

The failure is visible rather than silent: a previously working server reports
`Needs authentication` again. Re-run the probe above — a service name that has
regained its hash suffix means the variable stopped being honored.
