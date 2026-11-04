# Queue domain admission and metadata repair

Before appending rows to a reviewed file, inspect its existing queue domains and
use the owning project's explicit domain. A new/unclassified file can still use
`general`; once that exact file has a non-general domain, enqueue refuses an
omitted, null or blank domain. An intentional additional domain requires a
nonempty `domain_reason` on that item. It is recorded in the enqueue audit and
does not alter old rows. Existing multi-domain files can continue using any of
their recorded non-general domains. Preflight covers the complete incoming batch;
a domain refusal leaves that enqueue call without partial additions.

Use the existing `--enqueue-review` schema and `--domain` behavior documented in
[script parameters](script_parameters.md#review-queue-item-schema). Inspect the
returned row IDs and domains after enqueue. A domain controls dictionary scope;
do not use a domain change to make a disputed correction acceptable.

## Repair an omitted classification

For pending, unlinked rows whose only error is their domain, use
`scripts/review_domain.py`. Do not issue direct SQLite updates. Create an exact
private plan; this synthetic example repairs metadata only:

```json
{
  "ids": [42, 43],
  "file": "/abs/transcript.md",
  "from_domain": "general",
  "to_domain": "project-a",
  "reason": "Owning source manifest binds this transcript to project-a",
  "by": "operator"
}
```

```bash
# Preview; no row/domain/audit write.
python3 scripts/review_domain.py --plan /abs/runtime/domain-repair.json
# After reviewing those exact IDs and old/new values:
python3 scripts/review_domain.py --plan /abs/runtime/domain-repair.json --apply
```

The default database is the configured transcript-fixer store. `--db` selects an
explicit existing store for an isolated test or an already verified project
binding; it does not create a database. The JSON plan accepts only the shown keys.

Application uses one transaction and compares every ID's exact file, old domain,
pending status and absence of occurrence-family links before writing any row.
Missing, moved, decided or linked rows refuse the whole batch. It updates only
the domain and appends `review_domain_repair` audit events with old/new values,
reason and actor; transcript text, anchors, suggestions, candidates, actions,
evidence and verdicts remain intact. Linked families require their existing
[occurrence-group workflow](review_queue_dashboard.md#one-occurrence-multiple-candidates),
not a partial family retag through this command. Read the exact rows and audit
events back through the queue after applying.
