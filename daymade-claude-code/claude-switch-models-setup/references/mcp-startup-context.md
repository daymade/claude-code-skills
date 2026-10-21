# Reducing fixed startup context from MCP tool schemas

Use this procedure when `/context` shows substantial fixed cost before the first
task, especially from MCP tool schemas. Do not use it for `CLAUDE.md` restructuring
or context-window size configuration; those have separate owners. The commands are
macOS/Linux shell examples and require the public `sed`, `jq`, and `rg` CLIs.

## Measure one comparable baseline

1. Record total tokens and the category breakdown, not only the largest category.

   ```bash
   claude --print '/context'
   ```

   Interactive `/context` and `--print` can expose different built-in tool sets.
   Compare before/after results only when the invocation mode, project, profile, and
   model are unchanged. Treat a reduction in one category accompanied by growth in
   another as an unproven optimization, not a saving.

2. Identify the active configuration before reading or editing any file, then bind
   its paths for every later step.

   ```bash
   CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
   printf 'CLAUDE_CONFIG_DIR=%s\n' "$CONFIG_DIR"
   claude mcp list 2>&1 | sed -n -E 's/^([^:]+):.* - (✔ Connected|✘ Failed to connect)( — .*|$)/\1: \2/p'
   ```

   The `sed` filter emits only each server name and its exact health status; it
   strips endpoint URLs, stdio arguments and transport error details. Empty output
   means names and health are unverified, not that the registry is empty.

   Set the profile-specific paths once:

   - default profile: `ACTIVE_SETTINGS="$HOME/.claude/settings.json"`,
     `ACTIVE_STATE="$HOME/.claude.json"`, and no third-party provider overlay;
   - third-party profile: `ACTIVE_SETTINGS="$CONFIG_DIR/settings.json"`,
     `ACTIVE_STATE="$CONFIG_DIR/.claude.json"`, and
     `PROVIDER_SETTINGS="$HOME/.claude/settings/<name>.json"`.

   Use `ACTIVE_SETTINGS` for the edit and validation below, `ACTIVE_STATE` for
   structured registry keys, and `PROVIDER_SETTINGS` only for the third-party
   provider compatibility check. Do not assume `~/.claude` is the active profile,
   and do not infer the registry from a different profile's file.

3. Check provider compatibility before considering MCP tool search or deferred
   loading. Inspect only the relevant key, never the whole settings file:

   ```bash
   # Default profile:
   jq -r 'paths as $p | select($p[-1] == "ENABLE_TOOL_SEARCH") | "\($p|map(tostring)|join(".")) = \(getpath($p))"' \
     "$ACTIVE_SETTINGS"

   # Third-party profile:
   jq -r 'paths as $p | select($p[-1] == "ENABLE_TOOL_SEARCH") | "\($p|map(tostring)|join(".")) = \(getpath($p))"' \
     "$PROVIDER_SETTINGS"
   ```

   For a third-party profile, repeat the same field read against `ACTIVE_SETTINGS`
   when that layer can also carry the key. No output means the key is absent from
   that file, not that the feature is safe to enable. If it is deliberately
   `false` for a third-party provider, preserve that boundary instead of forcing
   the feature. Confirm current CLI support separately before relying on deferred
   loading.

## Test a reversible reduction

1. Start with specialized, high-cost, low-frequency servers. Preserve frequently
   used servers and cheaper alternatives; do not disable the whole registry merely
   because a total is high.

2. Deny a candidate only through a one-process settings overlay. Replace `<server>`
   with the exact name shown by the filtered list above:

   ```bash
   claude --settings '{"deniedMcpServers":[{"serverName":"<server>"}]}' mcp list 2>&1 \
     | sed -n -E 's/^([^:]+):.* - (✔ Connected|✘ Failed to connect)( — .*|$)/\1: \2/p'
   claude --settings '{"deniedMcpServers":[{"serverName":"<server>"}]}' --print '/context'
   ```

   The first command checks which server names and health statuses remain without
   printing endpoint URLs, stdio arguments or transport error details. The second
   measures the actual reduction. Neither edits the persistent configuration.

3. Inspect MCP configuration without dumping secrets. Do not run unfiltered
   `claude mcp get <server>` or `claude mcp list`: stdio `Environment` and
   arguments, remote headers, endpoint URLs and transport error details can contain
   credentials. Use the field-limited/redacting inspection contract in
   `credential-storage.md` instead.

4. For a single known settings key, use current CLI help and targeted field reads.
   Do not load a full settings schema or a general configuration Skill merely to
   make one edit.

## Persist only the minimal deny entry

Merge the following into `$ACTIVE_SETTINGS`, preserving every existing key and any
existing `deniedMcpServers` entries:

```json
"deniedMcpServers": [
  {
    "serverName": "<server>"
  }
]
```

Keep the MCP registry and credentials intact. Do not use `claude mcp remove` for
context reduction. The profile converger preserves profile-only top-level keys;
when the default profile owns the same key, apply its whole-key convergence rules
instead of assuming a profile-only override survives.

Treat this as a hard deny across configuration sources, not as a per-session toggle.
To use the server again, remove only its deny entry and start a new session.

## Accept in a fresh process

Run all three checks after the edit, without the temporary `--settings` overlay:

```bash
claude --print '/context'
claude mcp list 2>&1 | sed -n -E 's/^([^:]+):.* - (✔ Connected|✘ Failed to connect)( — .*|$)/\1: \2/p'
jq -e '.deniedMcpServers | type == "array" and length > 0' \
  "$ACTIVE_SETTINGS"
```

Accept only when:

- the total and MCP schema cost decreased against the same-mode baseline;
- the intended servers are absent while required servers still connect;
- the deny entry survives a fresh SessionStart convergence;
- unrelated model, plugin, Skill, and permission settings remain unchanged.

Already injected tool definitions do not leave the current session retroactively.
Make the acceptance claim from a new process, and keep any unexamined provider or
host behavior explicitly unknown.
