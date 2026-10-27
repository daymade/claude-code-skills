# Thread identity and JSON contracts

Use `scripts/find_codex_session.py <UUID-prefix>` for identity-only lookup. Supply
8–36 canonical UUID characters, including hyphens in their normal positions;
uppercase hex is accepted. Pass `--codex-home` only for an explicitly selected
store. Default output is JSON; use `--format markdown` for a human-readable list.

| Exit | Status | Action |
|---|---|---|
| 0 | `unique` | Return the ID only when the match has `identity_verified: true` |
| 1 | `not_found` | Report no matching ID in the selected state index; do not claim global absence |
| 1 | `ambiguous` | Show candidates; obtain a longer prefix rather than select one |
| 2 | `unavailable` / `identity_unverified` | Report the evidence gap; do not treat it as no match |
| 2 | Argument error | Correct the UUID syntax; argparse writes the error to stderr |

Read `schema`, `status`, `index`, `match_count`, `matches`, `truncated` and
`warnings` as required top-level fields. `match_count: null` means unknown, not
zero. The candidate list is capped at 20; `match_count` remains the full count.
A unique match carries `session_id`, `title`, `cwd`, `archived`,
`identity_verified` and verified `rollouts`. Optional titles can be null. Do not
infer conversation content or fork lineage from identity verification alone.

Keep the inventory CLI's existing contract separate. Its JSON path is
`providers.codex.conversations`, not a top-level `sessions` array:

```json
{"providers":{"codex":{"conversations":[{"session_id":"11111111-2222-4333-8444-555555555555"}]}}}
```

When consuming saved inventory JSON, validate required structure before filtering.
An empty valid list is distinct from missing, null or wrongly typed fields. Run
this strict extraction unchanged; it raises on schema errors instead of silently
substituting an empty list:

```python
def codex_inventory_rows(payload):
    if not isinstance(payload, dict):
        raise ValueError("Inventory must be an object")
    providers = payload["providers"]
    if not isinstance(providers, dict):
        raise ValueError("providers must be an object")
    codex = providers["codex"]
    if not isinstance(codex, dict):
        raise ValueError("providers.codex must be an object")
    rows = codex["conversations"]
    if not isinstance(rows, list):
        raise ValueError("providers.codex.conversations must be a list")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Conversation must be an object")
        session_id = row["session_id"]
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a nonblank string")
    return rows
```

Do not dump a full inventory to discover this shape or use `.get(..., [])` for
required fields. For a known prefix, use the identity command instead of exporting
all inventory rows. Retain the ordinary inventory and writer-lock workflow when
the user actually asks for recent sessions or lock evidence.
