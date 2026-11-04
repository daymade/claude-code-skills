# Authorize an approved Codex hook definition

Use this procedure only for exact user command-hook definitions already covered
by the user's authorization. It does not approve new definitions, enable hooks,
change their commands, or grant macOS Keychain/TCC access. The executing agent
performs the checks; no bundled script automatically authorizes hooks.

## Bind the installed interface and target

1. Resolve the actual native executable, version, Codex home and user config on
   the target host. Inspect `codex app-server --help`. Generate that executable's
   protocol schema into a new private directory with
   `codex app-server generate-json-schema --experimental --out <schema-directory>`.
   Verify the method and parameter shapes below against that schema. This route
   was exercised with native versions 0.160.0 and 0.163.0; other versions require
   their own interface check.
2. Use the installed version's native `/hooks` interface when available. A
   read-only hook-specific API does not establish that the native configuration
   API cannot record an approved definition. If the schema provides
   `hooks/list`, `config/read` and `config/batchWrite`, the route below is an
   alternative. If neither route is available, leave trust unconfirmed; do not
   invent a trust receipt or bypass hook checks.
3. Start only a task-owned app-server using its supported local transport. For
   stdio versions supporting it, run `codex app-server --stdio`, send JSONL
   `initialize` with `clientInfo` and `capabilities.experimentalApi: true`, wait
   for its matching result, then send the `initialized` notification. A transport
   timeout is not a trust decision; inspect the startup/network boundary before
   retrying. Do not restart an existing shared daemon.

## Read, compare and write the approved hashes

Call `hooks/list` with `{}`. Require an error-free parse for the selected source.
Bind each approved entry by its native `key`, `sourcePath`, `source`, command,
`enabled` state and `currentHash`. This procedure covers enabled `source: user`
command hooks at the approved user source file; other sources or handler types
remain outside this recipe. A matching name or another host's hash is insufficient.

Call `config/read` with `{"includeLayers": true}`. Select the single user layer
whose `name.type` is `user` and `name.file` is the exact target user config; retain
its `version`. Capture the parsed config and hook-definition fingerprint before
writing. Missing or ambiguous fields, changed commands or unapproved definitions
stop the affected grant.

Construct only the approved trust-hash edits. Form each `keyPath` as
`"hooks.state." + json.dumps(hook["key"]) + ".trusted_hash"`; quoting the native
key is necessary because it can contain paths, dots and colons. Use the same
entry's `currentHash` as its value. The native `config/batchWrite` body is:

```json
{
  "edits": [{
    "keyPath": "hooks.state.\"<exact-native-key>\".trusted_hash",
    "mergeStrategy": "replace",
    "value": "<that-entry-currentHash>"
  }],
  "filePath": "<exact-user-config-file>",
  "expectedVersion": "<version-from-the-matching-user-layer>",
  "reloadUserConfig": true
}
```

Require the native success response. A version conflict requires a new read and
comparison, not an unconditional overwrite. If the response is lost, inspect the
actual config before deciding whether any write remains necessary. Keep unrelated
trust entries, enablement, auth, profiles and hook definitions unchanged. Compare
the parsed before/after config and require that only the authorized `trusted_hash`
leaves changed; require the definition fingerprint to remain unchanged.

## Verify the consumer and finish

Start a fresh native process with the same executable, Codex home, configuration
and hook source, then call `hooks/list` again. Require every selected enabled hook
to report trusted and the selected source to have no parse errors. Report other
unapproved pending entries separately; a successful config write is not readback.
Close only task-owned processes and temporary transports.

If a temporary verified egress was needed, record that boundary: it can establish
persisted trust under that route, but cannot prove the ordinary startup path or a
model task now works. Native hook trust does not establish lower command latency,
successful hook execution, or freedom from OS password prompts.
