# Reducing fixed startup context from MCP tool schemas

Use this procedure when `/context` shows substantial fixed cost before the first
task, especially from MCP tool schemas. Do not use it for `CLAUDE.md` restructuring
or context-window size configuration; those have separate owners. The commands are
macOS/Linux shell examples.

## Measure one comparable baseline

1. Record total tokens and the category breakdown, not only the largest category.

   ```bash
   claude --print '/context'
   ```

   Interactive `/context` and `--print` can expose different built-in tool sets.
   Compare before/after results only when the invocation mode, project, profile, and
   model are unchanged. Treat a reduction in one category accompanied by growth in
   another as an unproven optimization, not a saving.

2. Identify the active configuration before reading or editing any file.

   ```bash
   printf 'CLAUDE_CONFIG_DIR=%s\n' "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
   claude mcp list
   ```

   Read `settings.json` and `.claude.json` from that actual profile layout, using
   the main-versus-third-party paths in `SKILL.md`. Do not assume `~/.claude` is the
   active profile, and do not infer the registry from a different profile's file.

3. Check provider compatibility before considering MCP tool search or deferred
   loading. Inspect only the relevant key, never the whole provider file:

   ```bash
   jq -r 'paths(scalars) as $p | select($p[-1] == "ENABLE_TOOL_SEARCH") | "\($p|map(tostring)|join(".")) = \(getpath($p))"' \
     "$HOME/.claude/settings/<name>.json"
   ```

   No output means the key is absent from that file, not that the feature is safe to
   enable. If it is deliberately `false` for a third-party provider, preserve that
   boundary instead of forcing the feature. Confirm current CLI support separately
   before relying on deferred loading.

## Test a reversible reduction

1. Start with specialized, high-cost, low-frequency servers. Preserve frequently
   used servers and cheaper alternatives; do not disable the whole registry merely
   because a total is high.

2. Deny a candidate only through a one-process settings overlay. Replace `<server>`
   with the exact name shown by `claude mcp list`:

   ```bash
   claude --settings '{"deniedMcpServers":[{"serverName":"<server>"}]}' mcp list
   claude --settings '{"deniedMcpServers":[{"serverName":"<server>"}]}' --print '/context'
   ```

   The first command checks which servers still connect. The second measures the
   actual reduction. Neither edits the persistent configuration.

3. Inspect MCP configuration without dumping secrets. Do not run unfiltered
   `claude mcp get <server>`: stdio `Environment` and remote headers can contain
   credentials. Use `claude mcp list` and the field-limited inspection contract in
   `credential-storage.md` instead.

4. For a single known settings key, use current CLI help and targeted field reads.
   Do not load a full settings schema or a general configuration Skill merely to
   make one edit.

## Persist only the minimal deny entry

Merge the following into the active profile's `settings.json`, preserving every
existing key and any existing `deniedMcpServers` entries:

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
claude mcp list
jq -e '.deniedMcpServers | type == "array" and length > 0' \
  "$HOME/.claude-profiles/<name>/settings.json"
```

Accept only when:

- the total and MCP schema cost decreased against the same-mode baseline;
- the intended servers are absent while required servers still connect;
- the deny entry survives a fresh SessionStart convergence;
- unrelated model, plugin, Skill, and permission settings remain unchanged.

Already injected tool definitions do not leave the current session retroactively.
Make the acceptance claim from a new process, and keep any unexamined provider or
host behavior explicitly unknown.
