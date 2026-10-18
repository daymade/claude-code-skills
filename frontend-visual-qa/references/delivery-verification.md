---
name: delivery-verification
description: Compare selected deployed HTTP resources with a frozen release when freshness or deployment is part of a UI acceptance claim.
---

# Verify the selected delivery

The agent preparing acceptance owns this check. Use the project's selected,
already-published artifact as the expected source. Prepare its hashes and stable
component facts before reading the running target; copying the running values
into the expected manifest can certify the old deployment.

Include the changed embedded component's own assets or version facts. Matching
the parent HTML/JS is insufficient when a reader, iframe or independent bundle
is served separately. Select the complete relevant resource set through the
project's release owner; this probe cannot discover or authenticate that set.

## Reuse a build from another source ref

When the release owner reuses a compiled build, record its build ref separately
from the selected published artifact ref in the task's provenance evidence.
Keep the HTTP manifest's `artifact_ref` bound to the selected delivery; matching
HTTP bytes does not establish which source produced them.

The release owner must establish that the production inputs are equivalent:
source, build configuration, dependency lock, generated inputs and relevant
environment. A test-file suffix alone is insufficient: imports, globs or build
plugins may consume that file. If equivalence is unproven, rebuild the selected
artifact or keep source provenance unverified. Then perform the normal resource
readback and affected rendered journey; this reference does not run a build or
grant deployment permission.

| Synthetic provenance case | Disposition |
|---|---|
| Build A and published B differ only in an extra test; the release owner proves it is excluded from all production inputs | Reuse is supportable; retain both refs and the equivalence evidence |
| Only a `.test` file changed, but a production glob consumes it or its participation is unknown | Reuse is unsupported by that filename; rebuild or retain the unresolved provenance |

## Manifest

Use a private task file outside the Skill package. In this synthetic example,
replace the commit and expected values from the selected artifact.

```json
{
  "schema_version": 1,
  "artifact_ref": "0123456789abcdef0123456789abcdef01234567",
  "base_url": "http://127.0.0.1:9000/",
  "resources": [
    {"path": "/assets/app.js", "sha256": "<64 lowercase hex characters>"},
    {"path": "/api/component/status", "json_fields": {"available": true, "version": "release-2"}}
  ]
}
```

Each resource uses exactly one of `sha256` or `json_fields`. Paths are absolute
within the given origin and omit queries/fragments. JSON fields are literal
top-level keys with finite scalar values. Missing keys differ from explicit
null; empty field sets and zero-resource manifests are invalid. Use stable
release facts, not observation timestamps or changing task counts.

Run from the resolved Skill directory:

```bash
uv run --no-project python scripts/verify_delivery.py --manifest <private-manifest.json>
```

Read the JSON status and exit code together:

| Exit | Status | Meaning |
|---|---|---|
| 0 | `matched` | Every supplied byte digest and JSON field matched |
| 1 | `mismatched` | At least one observed resource or required field differed; unknown observations may also be listed |
| 2 | `unprovable` / `invalid` | Observation incomplete or input invalid; never a successful delivery claim |

The report fingerprints target/resource paths and field values rather than
printing response bodies. Match fingerprints to the private manifest when
investigating a failure. The timeout applies per blocking HTTP operation,
not to the entire run; `--max-bytes` bounds each response body.

## Completion and recovery

### A deployment changes during acceptance

Synthetic example: the frozen expectation names release A, but a concurrent
authorized rollout makes the target serve B. Preserve A's expected manifest,
the loaded page's identity and the mismatch/partial observations; do not rewrite
them into a pass or roll the other publisher back. Resolve B through the release
owner and independently freeze its published artifact and build inputs before
creating a separately named B expectation. Reload the canonical target, verify
the affected resources, then rerun the affected rendered journey. Unchanged
checks with unchanged inputs remain reusable. If B cannot be established or
the target keeps changing, retain partial status and the precise unresolved
identity; live values copied into a new expectation do not resolve it.

The command only issues GETs, keeps ordinary proxy/TLS behavior, refuses
cross-origin redirects, and does not deploy, restart, sign in or change accounts.
Encoded responses and login-dependent resources require the existing same-state
browser or product-specific readback; an unsupported probe must not narrow the
Skill's existing browser/native coverage.

Run after the authorized rollout is settled. A match is data-plane identity
evidence, not an atomic cross-resource snapshot, source provenance, pixel review
or business acceptance. Continue the canonical journey and inspect its actual
screenshots. If the deployment is authorized and still pending, continue through
the project's owning procedure; if occupied or unauthorized, report the exact
remaining result and recovery condition without claiming overall completion.

For an expansion or transition, capture after the expected content renders and
inspect that content in the image. DOM `open=true`, a screenshot filename or a
completed click cannot prove visible input. Discard a pre-transition or stale
shot as acceptance evidence and give its replacement a distinct path.
