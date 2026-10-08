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
