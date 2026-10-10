# Reconcile a declared opportunity set

Use this only when a project-backed comparison already has a JSON projection of
its current-analysis decisions. Keep that entry authoritative; this helper reads
two files without updating them. A standalone source Profile requires no adoption
table. Coverage and state meaning are defined in
[Landscape](landscape_synthesis.md#account-for-material-opportunities).

Freeze the input independently before authoring decisions. Preserve its original
request keys, selected mechanisms and locators; never derive it from the decision
table. The v1 documents use the following required fields; extra provenance fields
are allowed. Field and relationship validation is implemented by
[`reconcile_opportunities.py`](../scripts/reconcile_opportunities.py).

```json
{
  "schema_version": 1,
  "scope": "our-product",
  "request_keys": ["Q1"],
  "candidates": [
    {"key":"input-transaction", "source_locator":"claim-a / source:10-20", "request_keys":["Q1"]}
  ]
}
```

Each registered key needs one decision; each request key needs a candidate
association. For an empty comparison, add `empty_explanation` with a nonblank
`reason` and a nonempty `evidence` reference list. An explicit `standalone-profile`
scope permits empty request, candidate and decision lists without that explanation.

```json
{
  "schema_version": 1,
  "decisions": [{
    "key":"input-transaction", "state":"adopted", "reason":"retain narrow mechanism",
    "owner":"execution owner", "business_delta":"fewer preparations; benefit unmeasured",
    "conditions_cost":"bound field and restoration obligation", "minimum_falsifier":"field mismatch",
    "evidence":{"implemented":["code-ref"], "exercised":["result-ref"], "outcome":[]},
    "adoption_scope":"exercised"
  }]
}
```

Common string fields are required and nonblank. Evidence requires all three arrays
of nonblank references; empty arrays retain unknown layers. For `adopted`, the
declared `adoption_scope` is `implemented`, `exercised` or `outcome` and that array
must be nonempty. For `not_adopted`, add `reopening_condition`.

For `pending`, add `next_check`, `reopening_condition`, `previous_pending` (boolean),
`new_evidence` (reference list), and a nonblank `blocker` or
`authorized_next_action`. The unused alternative may be absent/null; a supplied
blank string fails. Repeated pending with no new evidence and no blocker fails;
declaring a blocker does not prove it exists or justify endlessly postponing work.

Run from any directory with absolute input paths:

```bash
uv run <skill-dir>/scripts/reconcile_opportunities.py \
  --input <project-root>/frozen-opportunity-input.json \
  --decisions <project-root>/current-opportunity-decisions.json
```

Exit 0 reconciles the declared structure; 1 reports relationship/field violations;
2 reports unreadable or malformed documents. Inspect the JSON counts, missing/extra
keys and hashes, not only the exit code. Duplicate JSON members and using the same
file for both inputs fail. The output always states `semantic_checked:false`:
it cannot prove the source set is complete, references support adoption, a blocker
is real, a next action is authorized, or the increment improves this business.
Check those against the independently bound sources and the original user result.
