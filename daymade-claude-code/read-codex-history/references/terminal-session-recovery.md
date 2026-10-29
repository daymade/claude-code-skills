# Locate a session after its terminal disappears

Use this recipe for a missing Codex terminal after a reboot, a remote-client
disconnect, or a headless terminal closing. ToDesk names the connection client;
it does not establish that the terminal belonged to Ghostty.

## Bind the affected surface

Confirm the execution host, actual working directory, approximate last use and
whether the request is to identify records or reopen a terminal. Resolve “this
directory” from the current environment; do not replace a home directory with
the filesystem root. Ask only for facts the host cannot reveal. While an answer
is pending, inspect the known directory's index rather than assuming an emulator.

Use Ghostty snapshots only after establishing that Ghostty hosted the affected
terminal. Treat an estimated count as a recollection, not a filter or an identity
test: a snapshot with a similar count can describe unrelated work.

## Query the existing index, then verify original records

Run the maintained inventory with the known directory and date interval:

```text
python3 <skill-dir>/scripts/list_local_history.py \
  --source codex --index-only --cwd "<workspace>" --include-archived \
  --from-date <YYYY-MM-DD> --to-date <YYYY-MM-DD> --limit 30 --format json
```

Use created/updated overlap so an older session resumed during the interval is
included. Check `recent_rows` against `total`, exclusions and warnings; widen a
truncated listing within the same scope. Metadata timestamps order candidates;
they do not prove that a terminal was open at shutdown. Exclude the investigating
session. Keep extra plausible candidates visible rather than selecting exactly
the remembered number.

Verify each selected identity and read its original messages:

```text
python3 <skill-dir>/scripts/find_codex_session.py <full-session-id>
python3 <skill-dir>/scripts/read_codex_session.py --session <full-session-id> --full
```

Require `status: unique` and `identity_verified: true` from the lookup. Use the
exact reader's original-input and lineage evidence to identify the work. A native
host's read-thread tool can supply the original messages when its contract covers
that identity; do not require that host-specific tool on other installations.

When an earlier recovery is mentioned, first inspect the same directory's indexed
titles and verify the selected old conversation. Read its actual method and
outcome before calling it a successful precedent. Keep partial recovery partial.
Use indexed topic recall only when these bounded candidates do not locate it.

If the index, source or identity verification is unavailable, retain the precise
gap. Do not replace the maintained readers with a raw history scan or a new SQL
join. A prior-work requirement does not forbid these existing read-only probes;
report an unexpected gate denial without disguising the command to bypass it.

## Report three separate evidence questions

For each candidate, provide its task summary, full ID, last relevant time and:

| Question | Sufficient observation | Limit |
|---|---|---|
| Does the saved session exist? | Verified internal ID and readable original records | A title or filename alone is only a candidate |
| Was it one of the lost terminals? | Recorded terminal/client-to-session binding or the user's identification | Directory, recency and matching counts alone do not establish this |
| Is it running or restored? | Current identity-bound runtime evidence; after authorized reopening, reconciliation at the consuming terminal | `notLoaded`, a missing argv ID or an unheld writer lock alone does not prove all execution stopped |

State the identified records and the remaining attribution gap separately. Do not
label a candidate list as restored windows. Keep this Skill read-only; hand an
authorized reopening or continuation to its execution owner with the verified
IDs and unresolved boundaries. Reuse Ghostty recovery only for confirmed Ghostty
surfaces. Do not reopen terminals during an identification-only request.
